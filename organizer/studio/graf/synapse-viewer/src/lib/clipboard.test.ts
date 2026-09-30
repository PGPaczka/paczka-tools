import { afterEach, describe, expect, it, vi } from 'vitest'

import { COPIED_FOR_MS, copyText } from './clipboard'

function withClipboard(impl: (text: string) => Promise<void>) {
  Object.defineProperty(globalThis, 'navigator', {
    value: { clipboard: { writeText: vi.fn(impl) } },
    configurable: true,
  })
}

afterEach(() => vi.useRealTimers())

describe('kopiowanie do schowka', () => {
  it('potwierdza i samo się wycofuje', async () => {
    vi.useFakeTimers()
    withClipboard(() => Promise.resolve())
    const zmiany: boolean[] = []

    copyText('abc', (done) => zmiany.push(done))
    await vi.advanceTimersByTimeAsync(0)
    expect(zmiany).toEqual([true])

    await vi.advanceTimersByTimeAsync(COPIED_FOR_MS)
    expect(zmiany).toEqual([true, false])
  })

  it('odmowa schowka nie wywala widoku', async () => {
    // Przeglądarka potrafi odmówić zapisu (brak zgody, kontekst bez HTTPS). Kopiowanie
    // jest wygodą, nie jedyną drogą do wartości — ma zgasnąć, nie rzucić.
    withClipboard(() => Promise.reject(new Error('nope')))
    const zmiany: boolean[] = []

    copyText('abc', (done) => zmiany.push(done))
    await Promise.resolve()
    await Promise.resolve()

    expect(zmiany).toEqual([false])
  })

  it('brak schowka w ogóle jest cichy', () => {
    Object.defineProperty(globalThis, 'navigator', { value: {}, configurable: true })

    expect(() => copyText('abc', () => {})).not.toThrow()
  })

  it('odmontowanie w trakcie potwierdzenia nie zostawia timera', async () => {
    vi.useFakeTimers()
    withClipboard(() => Promise.resolve())
    const zmiany: boolean[] = []

    const cancel = copyText('abc', (done) => zmiany.push(done))
    await vi.advanceTimersByTimeAsync(0)
    cancel()
    await vi.advanceTimersByTimeAsync(COPIED_FOR_MS * 2)

    expect(zmiany).toEqual([true])
  })
})
