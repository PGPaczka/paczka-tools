import { describe, expect, it } from 'vitest';

import { highlight } from './highlight';

describe('kolorowanie składni podglądu', () => {
  it('koloruje język, który podał backend', async () => {
    const html = await highlight('# Nagłówek\n', 'markdown');

    expect(html).toContain('hljs-section');
  });

  it('oddaje null dla zwykłego tekstu — nie ma czego kolorować', async () => {
    expect(await highlight('zwykła notatka', 'plaintext')).toBeNull();
    expect(await highlight('zwykła notatka', null)).toBeNull();
  });

  it('oddaje null dla języka, którego biblioteka nie zna', async () => {
    expect(await highlight('cokolwiek', 'nie-ma-takiego')).toBeNull();
  });

  it('escapuje treść pliku — podgląd nie wstrzykuje HTML-u', async () => {
    const html = await highlight('<script>alert(1)</script>', 'xml');

    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;');
  });

  it('nie wywraca się na urwanej składni, bo podgląd to głowa pliku', async () => {
    expect(await highlight('int main() { if (', 'cpp')).toBeTypeOf('string');
  });
});
