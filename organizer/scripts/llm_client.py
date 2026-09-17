"""CLI cienkiego klienta AI — smoke test backendów z ``config/thresholds.yaml: llm``.

Uruchamianie: ``python scripts/llm_client.py --task classify --prompt-file -``
(katalog ``scripts/`` trafia wtedy na ``sys.path``, więc ``from orglib import
...`` działa bez instalacji pakietu — patrz inne skrypty potoku).

Woła :func:`orglib.llm_client.LLMClient.complete` i drukuje wynik jako JSON na
stdout. Służy do ręcznej weryfikacji backendu (krok C8: smoke test delegacji)
i do jednorazowych zapytań spoza ``ai_resolve.py`` — nie jest częścią potoku
per-przedmiot.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Optional

import typer

from orglib.llm_client import LLMClient, LLMError, load_llm_config

app = typer.Typer(
    add_completion=False,
    help="Wywołuje LLMClient.complete() z linii poleceń (smoke test backendów AI).",
)


def _read_prompt(prompt_file: Path) -> str:
    """Czyta prompt z pliku, albo ze stdin gdy ``prompt_file`` to ``-``."""
    if str(prompt_file) == "-":
        return sys.stdin.read()
    return Path(prompt_file).read_text(encoding="utf-8")


@app.command()
def complete(
    task: str = typer.Option(
        ..., "--task", help="Nazwa zadania z thresholds.yaml: llm (np. classify, relate)."
    ),
    prompt_file: Path = typer.Option(
        ..., "--prompt-file", help="Plik z promptem, albo '-' dla stdin."
    ),
    schema: Optional[Path] = typer.Option(
        None, "--schema", help="Plik JSON Schema wymuszający sparsowanie odpowiedzi jako JSON."
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Pomiń cache decyzji (nie czytaj z niego, nie zapisuj do niego)."
    ),
    cache_key: Optional[str] = typer.Option(
        None, "--cache-key", help="Własny klucz cache zamiast domyślnego (task|backend|model|sha256(prompt))."
    ),
) -> None:
    """Woła backend przypisany do ``--task`` i drukuje :class:`LLMResult` jako JSON."""
    prompt = _read_prompt(prompt_file)
    schema_dict = json.loads(schema.read_text(encoding="utf-8")) if schema is not None else None

    cfg = load_llm_config()
    if no_cache:
        cfg = dataclasses.replace(cfg, cache=False)
    client = LLMClient(cfg)

    try:
        # json=True zawsze: zadania AI tego projektu (classify/relate) mają zawsze
        # odpowiadać JSON-em (kontrakt I/O), więc smoke test ma to od razu widzieć w 'data'.
        result = client.complete(task, prompt, schema=schema_dict, json=True, cache_key=cache_key)
    except LLMError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    typer.echo(
        json.dumps(
            {
                "text": result.text,
                "data": result.data,
                "backend": result.backend,
                "model": result.model,
                "cached": result.cached,
                "elapsed_s": result.elapsed_s,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
