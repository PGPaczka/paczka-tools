<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { get } from 'svelte/store'
  import { CanvasGraphRenderer } from '../../render/CanvasGraphRenderer'
  import { createSimulation } from '../../domain/graph/forceSimulation'
  import type { SimNode, SimLink } from '../../domain/graph/forceSimulation'
  import { categoryAnchors } from '../../domain/graph/categoryAnchors'
  import { hierarchyAnchors } from '../../domain/graph/hierarchyAnchors'
  import { graph, visibleNodeIds, filters } from '../../stores/graphStore'
  import { selectedId, hoveredId } from '../../stores/selectionStore'
  import { minimapPositions, minimapViewport } from '../../stores/minimapStore'
  import { settings } from '../../stores/settingsStore'
  import { fitTrigger } from '../../stores/graphControlsStore'

  let canvas: HTMLCanvasElement

  let positions = new Map<string, { x: number; y: number }>()

  /**
   * Pozycje w postaci, w której czyta je renderer — JEDNA tablica, aktualizowana
   * w miejscu.
   *
   * Wcześniej `getPositions()` budowało ją od zera przy każdym rysowaniu ORAZ przy
   * każdym ruchu wskaźnika: dwa i pół tysiąca świeżych obiektów na klatkę. To jest
   * ten rodzaj kosztu, którego nie widać w kodzie rysującym, a który zjada tablet.
   */
  let positionList: { id: string; x: number; y: number }[] = []
  let positionIndex = new Map<string, { id: string; x: number; y: number }>()
  /** Rośnie, gdy pozycje się zmieniły — po tym renderer wie, kiedy przebudować quadtree. */
  let positionsVersion = 0

  function syncPositions(source: Map<string, { x: number; y: number }>): void {
    if (positionIndex.size !== source.size) {
      positionList = []
      positionIndex = new Map()
      for (const [id, p] of source) {
        const entry = { id, x: p.x, y: p.y }
        positionList.push(entry)
        positionIndex.set(id, entry)
      }
    } else {
      for (const entry of positionList) {
        const p = source.get(entry.id)
        if (p) { entry.x = p.x; entry.y = p.y }
      }
    }
    positionsVersion++
  }

  let renderer: CanvasGraphRenderer | null = null

  /** Podgląd kosztu rysowania: `/graf/?diag=1`. Domyślnie wyłączony. */
  const diag =
    typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('diag') === '1'
  /**
   * Podgląd pomiarów zwinięty do plakietki — żeby nie zasłaniał tego, co się mierzy.
   *
   * Na telefonie startuje zwinięty: tam trzy linijki nad panelem notatki zabierają
   * właśnie tę część ekranu, na którą się patrzy.
   */
  let diagMini = $state(typeof window !== 'undefined' && window.innerWidth <= 720)
  let stats = $state({
    fps: 0, drawMs: 0, nodesDrawn: 0, edgesDrawn: 0, labelsDrawn: 0,
    scale: 1, renderDpr: 1, deviceDpr: 1,
  })
  let sim: ReturnType<typeof createSimulation> | null = null

  // Track user drag/zoom so we don't auto-fit after they've panned
  let userHasMoved = false

  onMount(() => {
    const g = get(graph)
    if (!g || !canvas) return

    const cssW = canvas.clientWidth || 800
    const cssH = canvas.clientHeight || 600

    canvas.width = cssW * (window.devicePixelRatio || 1)
    canvas.height = cssH * (window.devicePixelRatio || 1)

    const currentSettings = get(settings)

    // Progressive fit thresholds: fire fitToNodes when alpha crosses below each value.
    // This ensures nodes never fly off-screen for more than ~0.4s during the
    // initial simulation, rather than waiting the full ~3s for onEnd.
    let fitTickCount = 0
    const FIT_ALPHAS = [0.5, 0.08]
    let fitAlphaIdx = 0

    /** Najkrótszy odstęp między rysowaniami w trakcie układania (ok. 22 kl./s). */
    const RENDER_INTERVAL_MS = 45
    /** Minimapa to drugi canvas z tymi samymi tysiącami kropek — wystarczy 5 razy na sekundę. */
    const MINIMAP_INTERVAL_MS = 200
    let lastRenderAt = 0
    let lastMinimapAt = 0

    // Nodes currently in the simulation — drag handlers pin them by reference, so this
    // has to follow the relayout rather than close over one particular run.
    let simNodes: SimNode[] = []

    // Deterministic jitter per node so the layout is stable across reloads
    const frac = (value: string): number => {
      let h = 0
      for (let i = 0; i < value.length; i++) h = ((h * 31 + value.charCodeAt(i)) >>> 0)
      return (h >>> 0) / 4294967295
    }

    /**
     * Lay out the VISIBLE subgraph, not the whole vault.
     *
     * The simulation used to place every node, so in a large filtered vault the handful
     * of visible ones ended up scattered across the full extent of thousands of hidden
     * neighbours — and fitting the viewport to them showed dust. Laying out only what is
     * on screen keeps the picture readable and the physics cheap; positions already
     * computed are reused as seeds, so toggling a filter does not reshuffle the world.
     */
    const startSimulation = (visibleIds: Set<string>): void => {
      const current = get(graph)
      if (!current) return

      const showAll = visibleIds.size === 0
      const shown = current.nodes.filter((n) => showAll || visibleIds.has(n.id))
      const shownIds = new Set(shown.map((n) => n.id))

      // Do czego ciąży węzeł: do swojego miejsca w HIERARCHII, a nie do rodzaju treści.
      // `category` pliku to `egzamin` — wspólne dla całej paczki — więc kotwiczenie po
      // nim ściągało egzaminy dziesięciu przedmiotów w jedno skupisko.
      const parentOf = new Map<string, string>()
      for (const edge of current.edges) {
        if ((edge.kind ?? 'link') === 'belongs_to') parentOf.set(edge.source, edge.target)
      }
      const hasHierarchy = parentOf.size > 0
      // Kontener to węzeł, który coś trzyma. Plik kotwiczy przy swoim rodzicu,
      // kontener — na własnej pozycji, policzonej względem RODZICA.
      const containers = new Set(parentOf.values())
      const anchorOf = (id: string, fallback: string): string => {
        if (!hasHierarchy) return fallback
        if (containers.has(id)) return id
        return parentOf.get(id) ?? id
      }

      simNodes = shown.map((n) => ({
        id: n.id,
        category: n.kind === 'real' ? n.category : 'Ghost',
        anchor: anchorOf(n.id, n.kind === 'real' ? n.category : 'Ghost'),
        level: n.kind === 'real' ? n.level : null,
      }))
      const simLinks: SimLink[] = current.edges
        .filter((e) => shownIds.has(e.source) && shownIds.has(e.target))
        .map((e) => ({ source: e.source, target: e.target }))

      // Pre-seed node positions at category anchor locations so nodes start near their
      // natural resting places, avoiding d3's tangled phyllotaxis cluster near (0,0).
      let anchorMap: Map<string, { x: number; y: number }>
      if (hasHierarchy) {
        // Waga kontenera to liczba węzłów, które pod nim wiszą — po niej dzieli się
        // łuk między rodzeństwo, żeby przedmiot z 2,5 tys. plików nie stał ramię
        // w ramię z takim, który ma dwanaście.
        const weight = new Map<string, number>()
        for (const n of simNodes) {
          let at: string | undefined = parentOf.get(n.id)
          const seen = new Set<string>([n.id])
          while (at !== undefined && !seen.has(at)) {
            weight.set(at, (weight.get(at) ?? 0) + 1)
            seen.add(at)
            at = parentOf.get(at)
          }
        }
        const anchorNodes = [...containers]
          .filter((id) => shownIds.has(id))
          .map((id) => ({
            id,
            parent: parentOf.get(id) ?? null,
            weight: weight.get(id) ?? 1,
          }))
        anchorMap = hierarchyAnchors(anchorNodes)
      } else {
        const catSet = new Set<string>()
        const catOrder: string[] = []
        for (const n of simNodes) {
          if (!catSet.has(n.anchor)) { catSet.add(n.anchor); catOrder.push(n.anchor) }
        }
        anchorMap = categoryAnchors(catOrder, cssW, cssH, 0, 0)
      }

      simNodes.forEach((n) => {
        const previous = positions.get(n.id)
        if (previous) {
          n.x = previous.x
          n.y = previous.y
        } else {
          const a = anchorMap.get(n.anchor) ?? { x: 0, y: 0 }
          const angle = frac(n.id) * Math.PI * 2
          const r = 25 + frac(n.id + '~') * 55
          n.x = a.x + Math.cos(angle) * r
          n.y = a.y + Math.sin(angle) * r
        }
        n.vx = 0
        n.vy = 0
      })

      sim?.stop()
      fitTickCount = 0
      fitAlphaIdx = 0
      userHasMoved = false

      sim = createSimulation(
        simNodes,
        simLinks,
        cssW,
        cssH,
        get(settings).repulsion,
        get(settings).linkDist,
        (newPositions: Map<string, { x: number; y: number }>, alpha: number) => {
          positions = newPositions
          syncPositions(positions)
          // Układanie trwa dziesiątki tyknięć, a oko i tak nie zobaczy różnicy między
          // sąsiednimi. Rysujemy najwyżej co RENDER_INTERVAL_MS, minimapę odświeżamy
          // jeszcze rzadziej — inaczej canvas jest zajęty w 100% i nie da się nim ruszyć.
          const now = performance.now()
          if (now - lastRenderAt >= RENDER_INTERVAL_MS || alpha <= 0.02) {
            lastRenderAt = now
            renderer?.scheduleRender()
          }
          if (now - lastMinimapAt >= MINIMAP_INTERVAL_MS || alpha <= 0.02) {
            lastMinimapAt = now
            minimapPositions.set(positions)
          }
          if (!userHasMoved) {
            fitTickCount++
            if (fitTickCount === 1) {
              renderer?.fitToNodes()
            } else if (fitAlphaIdx < FIT_ALPHAS.length && alpha < FIT_ALPHAS[fitAlphaIdx]) {
              fitAlphaIdx++
              renderer?.fitToNodes()
            }
          }
        },
        // Final fit once the simulation has converged — more accurate than fitting at an
        // arbitrary alpha threshold, and avoids an orphan drifting after the early fit.
        () => {
          // Ostatnie słowo należy do stanu końcowego: jedno pełne odrysowanie i minimapa.
          syncPositions(positions)
          minimapPositions.set(positions)
          renderer?.scheduleRender()
          if (!userHasMoved) renderer?.fitToNodes()
        },
        anchorMap,
      )
    }

    /**
     * Układanie ustępuje pierwszeństwa ręce.
     *
     * Symulacja dużego przedmiotu liczy się kilka sekund i przez ten czas zajmuje
     * canvas w całości — przesuwanie grafu w tym momencie to właśnie ten „lag".
     * Dotknięcie płótna wstrzymuje ją, puszczenie wznawia z tą samą energią, więc
     * układ dochodzi do końca, tylko nie kosztem tego, co człowiek właśnie robi.
     */
    let layoutPaused = false
    const pauseLayout = (): void => {
      if (!sim || layoutPaused || sim.getAlpha() <= 0.005) return
      layoutPaused = true
      sim.stop()
    }
    const resumeLayout = (): void => {
      if (!layoutPaused) return
      layoutPaused = false
      sim?.restart()
    }
    canvas.addEventListener('pointerdown', pauseLayout)
    window.addEventListener('pointerup', resumeLayout)
    window.addEventListener('pointercancel', resumeLayout)

    // Odczyt statystyk co pół sekundy — sam podgląd nie ma wpływać na to, co mierzy.
    const diagTimer = diag
      ? setInterval(() => {
          if (renderer) stats = renderer.getStats()
        }, 500)
      : null

    startSimulation(get(visibleNodeIds))

    renderer = new CanvasGraphRenderer()
    renderer.mount({
      canvas,
      getPositions: () => positionList,
      getPositionsVersion: () => positionsVersion,
      getGraph: () => get(graph)!,
      getSelected: () => get(selectedId),
      getHovered: () => get(hoveredId),
      getVisibleIds: () => get(visibleNodeIds),
      getVisibleEdgeKinds: () => new Set(get(filters).relationKinds),
      getCatColorOverrides: () => get(settings).catColorOverrides,
      getColorPriority: () => get(settings).colorPriority,
      getSecondaryColorEnabled: () => get(settings).secondaryColorEnabled,
      onNodeClick: (id) => {
        selectedId.set(id)
      },
      onNodeHover: (id) => hoveredId.set(id),
      onNodeDragStart: (_id, worldX, worldY) => {
        userHasMoved = true
        const node = sim && simNodes.find((n) => n.id === _id)
        if (node) { node.fx = worldX; node.fy = worldY }
        sim?.reheat(0.08)
      },
      onNodeDrag: (id, worldX, worldY) => {
        const node = simNodes.find((n) => n.id === id)
        if (node) { node.fx = worldX; node.fy = worldY }
        // Update positions map directly so the renderer shows the new position
        // immediately without waiting for the next simulation tick.
        const pos = positions.get(id)
        if (pos) { pos.x = worldX; pos.y = worldY }
        syncPositions(positions)
        // Higher alpha (0.06 vs old 0.01) keeps enough energy for adjacent nodes
        // to visibly follow the dragged node while the mouse is still moving.
        sim?.reheat(0.06)
        renderer?.scheduleRender()
      },
      onNodeDragEnd: (id) => {
        const node = simNodes.find((n) => n.id === id)
        if (node) {
          // Commit the final drag position into d3-force's own x/y before clearing the pin.
          // Without this, d3 restarts from its last-ticked x/y (which lags behind fast drags)
          // and the node snaps back toward its pre-drag position.
          if (node.fx != null) node.x = node.fx
          if (node.fy != null) node.y = node.fy
          node.vx = 0
          node.vy = 0
          node.fx = null
          node.fy = null
        }
        // Reheat enough for surrounding nodes to smoothly settle around the
        // released node. Without this the sim is at alpha ~0.01 and decays
        // in ~2 ticks, making the graph look like it stops abruptly.
        sim?.reheat(0.15)
      },
      onViewportChange: (vp) => {
        minimapViewport.set(vp)
      },
      onUserMove: () => {
        userHasMoved = true
      },
    })

    // Don't set canvas.width/height here — draw() handles resizing internally.
    // Setting it here would clear the canvas on every mouse-move pixel during
    // a panel resize, causing the graph to flash blank while dragging.
    // Guard against 0×0 (canvas hidden via display:none) to avoid corrupting
    // the viewport's stored dimensions.
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width === 0 || height === 0) return
        renderer?.scheduleRender()
      }
    })
    ro.observe(canvas)

    const onWindowMouseMove = (e: MouseEvent) => {
      renderer?.handleWindowMouseMove(e.clientX, e.clientY)
    }
    const onWindowMouseUp = () => {
      renderer?.handleWindowMouseUp()
    }
    window.addEventListener('mousemove', onWindowMouseMove)
    window.addEventListener('mouseup', onWindowMouseUp)

    // Subscribe to settings changes: update physics AND redraw (for color changes).
    // Skip the immediate fire from subscribe() — the simulation is already set up
    // with the correct initial values and an extra reheat would reset alpha mid-run.
    // Only call updatePhysics (which reheats) when the physics values actually changed;
    // colour/priority/toggle changes are purely visual and must not disturb the layout.
    let settingsInited = false
    let prevRepulsion = currentSettings.repulsion
    let prevLinkDist = currentSettings.linkDist
    const unsubSettings = settings.subscribe((s) => {
      if (!settingsInited) { settingsInited = true; return }
      if (s.repulsion !== prevRepulsion || s.linkDist !== prevLinkDist) {
        prevRepulsion = s.repulsion
        prevLinkDist = s.linkDist
        // Reset so the upcoming onEnd fires fitToNodes for the new layout
        userHasMoved = false
        sim?.updatePhysics(s.repulsion, s.linkDist)
      }
      renderer?.scheduleRender()
    })

    // Immediately redraw when selection/visibility/hover changes
    const scheduleRender = () => renderer?.scheduleRender()
    const unsubSelected  = selectedId.subscribe(scheduleRender)
    // Relayout when the visible SET changes (not merely when something re-renders).
    let lastVisibleKey = [...get(visibleNodeIds)].sort().join(',')
    let relayoutTimer: ReturnType<typeof setTimeout> | null = null
    const unsubVisible = visibleNodeIds.subscribe((ids) => {
      scheduleRender()
      const key = [...ids].sort().join(',')
      if (key === lastVisibleKey) return
      lastVisibleKey = key
      if (relayoutTimer) clearTimeout(relayoutTimer)
      // Filters are clicked in bursts; one relayout per burst.
      relayoutTimer = setTimeout(() => startSimulation(ids), 150)
    })
    const unsubHovered   = hoveredId.subscribe(scheduleRender)

    // External fit trigger (e.g. "Fit to graph" button)
    let fitInited = false
    const unsubFit = fitTrigger.subscribe(() => {
      if (!fitInited) { fitInited = true; return }
      userHasMoved = false
      renderer?.fitToNodes()
    })

    return () => {
      if (diagTimer !== null) clearInterval(diagTimer)
      canvas.removeEventListener('pointerdown', pauseLayout)
      window.removeEventListener('pointerup', resumeLayout)
      window.removeEventListener('pointercancel', resumeLayout)
      ro.disconnect()
      window.removeEventListener('mousemove', onWindowMouseMove)
      window.removeEventListener('mouseup', onWindowMouseUp)
      unsubSettings()
      unsubSelected()
      unsubVisible()
      unsubHovered()
      unsubFit()
    }
  })

  onDestroy(() => {
    renderer?.destroy()
    renderer = null
    sim?.stop()
    sim = null
  })
</script>

<canvas bind:this={canvas} style="width:100%;height:100%;display:block"></canvas>

{#if diag}
  <!-- `?diag=1` — mierzalny odczyt z URZĄDZENIA, na którym coś „laguje". Bez tego
       zostaje opis wrażenia, a wrażenie nie mówi, czy koszt jest w rysowaniu, w liczbie
       elementów, czy w gęstości pikseli telefonu. -->
  <!-- Dotknięcie chowa podgląd do plakietki: na telefonie zasłaniał panel notatki,
       a jest narzędziem pomiarowym, nie treścią (zgłoszone 2026-09-24). -->
  <button
    class="diag"
    class:mini={diagMini}
    title={diagMini ? 'Pokaż pomiary' : 'Schowaj pomiary'}
    onclick={() => (diagMini = !diagMini)}
  >
    {#if diagMini}
      {stats.fps} kl./s
    {:else}
      <b>{stats.fps} kl./s</b> · rysowanie {stats.drawMs} ms<br />
      węzłów {stats.nodesDrawn} · krawędzi {stats.edgesDrawn} · podpisów {stats.labelsDrawn}<br />
      zoom {stats.scale} · piksele {stats.renderDpr}/{stats.deviceDpr}
    {/if}
  </button>
{/if}

<style>
  .diag {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 30;
    padding: 6px 8px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: rgba(13, 17, 23, 0.86);
    color: var(--text);
    font-family: var(--font-mono, monospace);
    font-size: 11px;
    line-height: 1.45;
    text-align: left;
    cursor: pointer;
  }
  .diag.mini {
    padding: 3px 7px;
    opacity: 0.75;
  }
</style>
