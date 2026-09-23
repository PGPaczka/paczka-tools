import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearPrefs, defaultPanels, loadPrefs, savePrefs } from './prefs';

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

describe('panele boczne na starcie', () => {
  it('telefon zaczyna z obydwoma zwiniętymi — pierwszy ekran ma być pracą', () => {
    expect(defaultPanels(412)).toEqual({ queueOpen: false, listOpen: false });
  });

  it('tablet zwija kolejkę, ale zostawia listę przedmiotów', () => {
    // Kolejka etapów jest powtórzona jako filtr w liście, lista nie jest powtórzona nigdzie.
    expect(defaultPanels(820)).toEqual({ queueOpen: false, listOpen: true });
  });

  it('na szerokim ekranie oba panele są otwarte', () => {
    expect(defaultPanels(1440)).toEqual({ queueOpen: true, listOpen: true });
  });
});
