import { describe, expect, it } from 'vitest';
import { basename, bytes, count, dirname, percent, stamp } from './format';

describe('count', () => {
  it('grupuje tysiące niezależnie od ICU przeglądarki', () => {
    expect(count(2570)).toBe('2 570');
    expect(count(48049)).toBe('48 049');
    expect(count(7)).toBe('7');
    expect(count(1234567)).toBe('1 234 567');
  });

  it('brak liczby to kreska, nie zero — zero i „nie wiem” to co innego', () => {
    expect(count(null)).toBe('—');
    expect(count(undefined)).toBe('—');
    expect(count(0)).toBe('0');
  });
});

describe('bytes', () => {
  it('skaluje do jednostek binarnych', () => {
    expect(bytes(512)).toBe('512 B');
    expect(bytes(26214400)).toBe('25 MiB');
    expect(bytes(1536)).toBe('1,5 KiB');
  });
});

describe('stamp', () => {
  it('przycina ISO do minut', () => {
    expect(stamp('2026-09-19T00:25:50Z')).toBe('2026-09-19 00:25');
    expect(stamp(null)).toBe('—');
  });
});

describe('percent', () => {
  it('pokazuje pewność jako procent', () => {
    expect(percent(0.95)).toBe('95%');
    expect(percent(null)).toBe('—');
  });
});

describe('ścieżki', () => {
  it('rozbija ścieżkę na nazwę i katalog', () => {
    expect(basename('SEM3/AKO/w1.pdf')).toBe('w1.pdf');
    expect(dirname('SEM3/AKO/w1.pdf')).toBe('SEM3/AKO');
    expect(dirname('w1.pdf')).toBe('');
  });
});
