import { describe, expect, it } from 'vitest';
import { collisionAt, moveTarget } from './plan';
import type { PlanTree } from './api';

const tree = {
  target_dir: 'paczka/SEM3/AKO',
  files: 2,
  homeless: [],
  folders: [
    {
      path: 'paczka/SEM3/AKO/egzamin',
      states: {},
      files: [
        { name: 'k1.pdf', path: 'paczka/SEM3/AKO/egzamin/k1.pdf', state: 'new', sha256: 'a', detail: '' },
        { name: 'k2.pdf', path: 'paczka/SEM3/AKO/egzamin/k2.pdf', state: 'ground_truth', sha256: 'b', detail: '' },
      ],
    },
  ],
} as unknown as PlanTree;

describe('moveTarget', () => {
  it('składa ścieżkę z katalogu i nazwy pliku', () => {
    expect(moveTarget('paczka/SEM3/AKO/egzamin', 'k3.pdf')).toBe('paczka/SEM3/AKO/egzamin/k3.pdf');
  });

  it('nie dubluje ukośnika', () => {
    expect(moveTarget('paczka/SEM3/AKO/egzamin/', 'k3.pdf')).toBe('paczka/SEM3/AKO/egzamin/k3.pdf');
  });

  it('bez katalogu albo bez nazwy nie ma celu', () => {
    expect(moveTarget(null, 'k3.pdf')).toBeNull();
    expect(moveTarget('paczka/SEM3/AKO', null)).toBeNull();
  });
});

describe('collisionAt', () => {
  it('znajduje plik stojący już pod tą ścieżką — także ten z paczki', () => {
    expect(collisionAt(tree, 'paczka/SEM3/AKO/egzamin/k1.pdf')?.state).toBe('new');
    expect(collisionAt(tree, 'paczka/SEM3/AKO/egzamin/k2.pdf')?.state).toBe('ground_truth');
  });

  it('wolne miejsce to brak kolizji', () => {
    expect(collisionAt(tree, 'paczka/SEM3/AKO/egzamin/k9.pdf')).toBeNull();
    expect(collisionAt(null, 'cokolwiek')).toBeNull();
  });
});
