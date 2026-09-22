import { describe, expect, it } from 'vitest';
import { itemsUrl, previewImageUrl, subjectUrl } from './api';

describe('itemsUrl', () => {
  it('przenosi filtry do zapytania', () => {
    expect(itemsUrl({ semester: 3, skrot: 'AKO', needs_review: true })).toBe(
      '/api/items?semester=3&skrot=AKO&needs_review=true',
    );
  });

  it('pomija filtry nieustawione i puste — pusty parametr to nie brak filtru', () => {
    expect(itemsUrl({ skrot: '', category: undefined, limit: 50 })).toBe('/api/items?limit=50');
    expect(itemsUrl({})).toBe('/api/items');
  });

  it('przepuszcza false, bo to znaczące „nie” (np. classified=false)', () => {
    expect(itemsUrl({ classified: false })).toBe('/api/items?classified=false');
  });

  it('nie gubi zera w offsecie', () => {
    expect(itemsUrl({ offset: 0, limit: 10 })).toBe('/api/items?offset=0&limit=10');
  });
});

describe('subjectUrl', () => {
  it('koduje skrót i dokłada grupę, gdy rozstrzyga kolizję', () => {
    expect(subjectUrl(3, 'AKO')).toBe('/api/subjects/3/AKO');
    expect(subjectUrl(5, 'SI', 'Sieci')).toBe('/api/subjects/5/SI?grupa=Sieci');
  });
});

describe('previewImageUrl', () => {
  it('prosi o konkretną szerokość, gdy widok jej potrzebuje', () => {
    expect(previewImageUrl('c'.repeat(64), 1, 240)).toBe(
      `/api/preview/${'c'.repeat(64)}/image?page=1&width=240`,
    );
  });

  it('adresuje stronę podglądu po treści, nie po ścieżce pliku', () => {
    expect(previewImageUrl('a'.repeat(64))).toBe(`/api/preview/${'a'.repeat(64)}/image?page=1`);
    expect(previewImageUrl('b'.repeat(64), 3)).toBe(`/api/preview/${'b'.repeat(64)}/image?page=3`);
  });
});
