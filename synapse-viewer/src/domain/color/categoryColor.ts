/**
 * djb2 hash — same string always produces the same integer.
 */
function djb2(str: string): number {
  let h = 5381
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h) ^ str.charCodeAt(i)
  }
  return h
}

/**
 * Convert HSL (h in degrees, s/l in percent) to '#rrggbb' hex string.
 */
function hslToHex(h: number, s: number, l: number): string {
  const sl = s / 100
  const ll = l / 100
  const a = sl * Math.min(ll, 1 - ll)
  const f = (n: number): string => {
    const k = (n + h / 30) % 12
    const color = ll - a * Math.max(Math.min(k - 3, 9 - k, 1), -1)
    return Math.round(255 * color)
      .toString(16)
      .padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

/**
 * Returns a hex color for a category.
 *
 * Precedence:
 *   userOverrides > hash fallback (deterministic string→HSL)
 */
export function categoryColor(
  category: string,
  userOverrides: Record<string, string> = {},
): string {
  if (userOverrides[category]) return userOverrides[category]

  const h = djb2(category)
  const hue = (h >>> 0) % 360
  return hslToHex(hue, 65, 55)
}

/** Load per-category color overrides from localStorage. */
export function getUserOverrides(): Record<string, string> {
  try {
    const stored = localStorage.getItem('synapse:catColors')
    if (stored) return JSON.parse(stored) as Record<string, string>
  } catch {
    // localStorage may be unavailable
  }
  return {}
}

/** Persist a single category color override to localStorage. */
export function setUserOverride(category: string, color: string): void {
  const overrides = getUserOverrides()
  overrides[category] = color
  localStorage.setItem('synapse:catColors', JSON.stringify(overrides))
}
