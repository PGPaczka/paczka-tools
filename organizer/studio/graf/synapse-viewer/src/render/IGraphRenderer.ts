import type { KnowledgeGraph } from '../domain/graph/GraphModel'

export interface NodePosition {
  id: string
  x: number
  y: number
}

/** Co ostatnia klatka naprawdę kosztowała — do podglądu `?diag=1`. */
export interface RenderStats {
  /** Czas samego rysowania w ms (mediana z ostatnich klatek). */
  drawMs: number
  /** Klatki na sekundę liczone z odstępów między rysowaniami. */
  fps: number
  nodesDrawn: number
  edgesDrawn: number
  /** Ile podpisów faktycznie weszło — po odsianiu kolizji. */
  labelsDrawn: number
  /** Ile pikseli fizycznych na piksel CSS naprawdę malujemy. */
  renderDpr: number
  deviceDpr: number
  scale: number
}

export interface RendererOptions {
  canvas: HTMLCanvasElement
  getPositions: () => NodePosition[]
  /**
   * Bumped whenever the positions change. It lets the renderer cache what is derived
   * from them — the hit-testing quadtree above all, which was rebuilt over the whole
   * vault on every single mouse move.
   */
  getPositionsVersion?: () => number
  getGraph: () => KnowledgeGraph
  getSelected: () => string | null
  getHovered: () => string | null
  getVisibleIds: () => Set<string>
  /**
   * Relation kinds to draw; empty set means "all". Filtering happens at draw time, not in
   * the simulation: hiding a kind must not move the nodes, or toggling a filter would
   * rearrange the graph under the reader's hands.
   */
  getVisibleEdgeKinds?: () => Set<string>
  getCatColorOverrides: () => Record<string, string>
  getColorPriority: () => 'category' | 'status'
  getSecondaryColorEnabled: () => boolean
  onNodeClick: (id: string) => void
  onNodeHover: (id: string | null) => void
  /** Called when user starts dragging a node (after confirming movement). */
  onNodeDragStart?: (id: string, worldX: number, worldY: number) => void
  /** Called every frame while the user is dragging a node. */
  onNodeDrag?: (id: string, worldX: number, worldY: number) => void
  /** Called when user releases a dragged node. */
  onNodeDragEnd?: (id: string) => void
  /** Called at the end of every draw() — supplies the current viewport state for the minimap. */
  onViewportChange?: (state: { tx: number; ty: number; scale: number; vw: number; vh: number }) => void
  /** Called only when the user explicitly pans or zooms (not from fitToNodes). */
  onUserMove?: () => void
}

export interface IGraphRenderer {
  mount(options: RendererOptions): void
  scheduleRender(): void
  destroy(): void
  fitToNodes(): void
  /** Ostatnio zmierzone koszty rysowania. */
  getStats(): RenderStats
}
