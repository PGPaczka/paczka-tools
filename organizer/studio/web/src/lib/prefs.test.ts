import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearPrefs, loadPrefs, savePrefs } from './prefs';

describe('prefs', () => {
  beforeEach(() => localStorage.clear());

  it('wraca z tym, co zapisano', () => {
    savePrefs({ mode: 'decide', semester: 3, skrot: 'AKO', queueOpen: false });
    expect(loadPrefs()).toEqual({ mode: 'decide', semester: 3, skrot: 'AKO', queueOpen: false });
  });

  it('pusta pamięć to pusty wybór, nie wyjątek', () => {
    expect(loadPrefs()).toEqual({});
  });

  it('uszkodzony wpis nie wywraca aplikacji', () => {
    localStorage.setItem('paczka-studio:prefs:v1', '{to nie jest json');
    expect(loadPrefs()).toEqual({});
  });

  it('niedostępny localStorage też nie wywraca aplikacji', () => {
    // Tryb prywatny i zablokowane dane stron potrafią rzucić przy każdym dostępie.
    const boom = () => { throw new Error('SecurityError'); };
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(boom);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(boom);

    expect(loadPrefs()).toEqual({});
    expect(() => savePrefs({ mode: 'plan' })).not.toThrow();
    vi.restoreAllMocks();
  });

  it('czyszczenie działa', () => {
    savePrefs({ mode: 'plan' });
    clearPrefs();
    expect(loadPrefs()).toEqual({});
  });
});
