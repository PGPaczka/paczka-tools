"""B5: klasyfikacja AI resztek jednego przedmiotu — manifest_slice.jsonl → plan.ai.jsonl.

Ten skrypt jest **jedynym** produkcyjnym punktem styku pipeline'u z modelem. Koordynator
(Claude/Codex/człowiek) go uruchamia i ocenia wynik; sam nie klasyfikuje w swojej sesji,
bo praca masowa ma iść na tani backend z ``config/thresholds.yaml: llm`` (patrz
``scripts/orglib/llm_client.py``), a nie na limit koordynatora.

Kontrakt:

- wejście — ``reports/.../manifest_slice.jsonl`` z ``prepare_subject.py`` (B1); każda linia
  opisuje jedną **treść** (sha256), nie jeden plik;
- wyjście — ``plan.ai.jsonl`` obok manifestu, jedna linia na sha256, zgodna z
  ``prompts/plan_line.schema.json``;
- AI dostaje tylko to, czego deterministyka nie rozstrzygnęła (``needs_review: true``
  w manifeście albo brak wpisu w planie deterministycznym). ``--all`` łamie tę zasadę
  świadomie i tylko na żądanie człowieka.

Skrypt jest wznawialny: sha256 już obecne w pliku wyjściowym są pomijane, więc przerwany
przebieg można dokończyć bez duplikowania decyzji ani ponownego płacenia za te same
wywołania. Nie dotyka materiałów, nie zmienia statusów w bazie, nie wykonuje ``apply``.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any, Optional, Sequence

import jsonschema
import typer

from orglib import config
from orglib.llm_client import (
    LLMClient,
    LLMError,
    LLMParseError,
    load_llm_config,
    truncate_head,
)

app = typer.Typer(add_completion=False, help=__doc__)

#: Kategorie dozwolone przez schemat planu — źródło prawdy to plik schematu.
_SCHEMA_PATH = config.ORGANIZER_ROOT / "prompts" / "plan_line.schema.json"
_PROMPT_PATH = config.ORGANIZER_ROOT / "prompts" / "classify_ambiguous.md"

#: Progi z thresholds.yaml mają pierwszeństwo; te wartości są awaryjne.
_FALLBACK_AUTO_APPLY = 0.90
_FALLBACK_REVIEW_MIN = 0.70


def load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


#: Słowa kluczowe JSON Schema, których tryb strukturalny OpenAI nie przyjmuje
#: (odrzuca całe żądanie z ``invalid_json_schema``). Walidujemy je lokalnie.
_WIRE_UNSUPPORTED = frozenset(
    {"pattern", "minimum", "maximum", "minLength", "maxLength", "format", "default"}
)


def wire_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Wariant schematu akceptowany przez tryb strukturalny modeli (``--output-schema``).

    OpenAI wymaga w trybie ścisłym, żeby ``required`` wymieniało **każdy** klucz
    z ``properties`` — pola opcjonalne (``year``, ``related_to``, ``relation``) są
    już typu ``["string", "null"]``, więc wymuszenie ich obecności nic nie kosztuje:
    model musi je podać, choćby jako ``null``. Dodatkowo usuwamy słowa kluczowe
    walidacyjne, których ten tryb nie obsługuje. Kanoniczny
    ``prompts/plan_line.schema.json`` pozostaje nietknięty i to on rozstrzyga
    poprawność odpowiedzi (:func:`normalize_decision`).
    """

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key: strip(value)
                for key, value in node.items()
                if key not in _WIRE_UNSUPPORTED
            }
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    out = strip(schema)
    properties = out.get("properties")
    if isinstance(properties, dict):
        out["required"] = list(properties)
    out["additionalProperties"] = False
    return out


def allowed_categories(subject: config.Subject) -> list[str]:
    """Kategorie z ``syntax.yaml`` dopuszczalne dla form tego przedmiotu.

    ``Subject.forms`` to litery form zajęć (``W``/``C``/``L``/``P``), a kategoria
    deklaruje w ``syntax.yaml: categories.<nazwa>.forms``, których form dotyczy.
    Kategoria bez ``forms`` (``opracowania``, ``ksiazki``, ``inne``) pasuje zawsze.
    Przedmiot bez wykładu nie może więc dostać kategorii ``wyklad``, a bez laborek —
    ``laboratoria`` (reguła 1 skilla ai-resolve).
    """
    categories = config.load_yaml("syntax").get("categories") or {}
    subject_forms = {form.upper() for form in subject.forms}
    allowed: list[str] = []
    for name, spec in categories.items():
        forms = (spec or {}).get("forms") if isinstance(spec, dict) else None
        if not forms or subject_forms & {str(f).upper() for f in forms}:
            allowed.append(str(name))
    return allowed


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: niepoprawny JSON ({exc})") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number}: linia nie jest obiektem JSON")
            rows.append(row)
    return rows


def existing_hashes(path: Path) -> set[str]:
    """sha256 już rozstrzygnięte — do wznawiania przebiegu i pomijania deterministyki."""
    if not path.is_file():
        return set()
    hashes: set[str] = set()
    for row in read_jsonl(path):
        value = row.get("source_sha256") or row.get("sha256")
        if isinstance(value, str):
            hashes.add(value)
    return hashes


def select_rows(
    manifest: Sequence[dict[str, Any]],
    *,
    resolved: set[str],
    take_all: bool,
) -> list[dict[str, Any]]:
    """Wybiera pozycje do wysłania modelowi; zachowuje kolejność manifestu.

    Deduplikacja po sha256 jest twarda: jedna treść = jedna decyzja, nawet gdy
    manifest wymienia ją w kilku liniach (reguła 6 skilla ai-resolve).
    """
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in manifest:
        sha = row.get("sha256") or row.get("source_sha256")
        if not isinstance(sha, str) or not sha:
            raise ValueError(f"pozycja manifestu bez sha256: {row!r}")
        if sha in seen or sha in resolved:
            continue
        if not take_all and not row.get("needs_review"):
            continue
        seen.add(sha)
        selected.append(row)
    return selected


def _filename(row: dict[str, Any]) -> str:
    representative = row.get("source_path") or ""
    paths = row.get("source_paths") or []
    if not representative and paths:
        representative = str(paths[0])
    return Path(str(representative)).name or "(nieznana)"


def build_prompt(
    row: dict[str, Any],
    *,
    subject: config.Subject,
    template: str,
    model_hint: str,
    text_head_limit: int,
    categories: Sequence[str],
) -> str:
    """Podstawia fakty o materiale do szablonu ``prompts/classify_ambiguous.md``.

    Świadomie używa ``str.replace``, a nie ``str.format`` — szablon zawiera przykład
    JSON-a z nawiasami klamrowymi, którego formatowanie by nie przeżyło.
    """
    filename = _filename(row)
    text_head = truncate_head(str(row.get("text_head") or ""), text_head_limit)
    source_paths = row.get("source_paths") or []
    reasons = row.get("review_reasons") or []
    replacements = {
        "{{SEMESTER}}": str(subject.semester),
        "{{SKROT}}": subject.skrot,
        "{{NAZWA}}": subject.nazwa,
        "{{TARGET_DIR}}": subject.target_dir,
        "{{ALLOWED_CATEGORIES}}": ", ".join(categories) or "inne",
        "{{SHA256}}": str(row.get("sha256") or row.get("source_sha256")),
        "{{FILENAME}}": filename,
        "{{EXTENSION}}": Path(filename).suffix.lower() or "(brak)",
        "{{CONTENT_KIND}}": str(row.get("content_kind") or "nieznany"),
        "{{SIZE_BYTES}}": str(row.get("size_bytes") or 0),
        "{{SOURCE_PATHS}}": ", ".join(str(p) for p in source_paths[:10]) or "(brak)",
        "{{REVIEW_REASONS}}": ", ".join(str(r) for r in reasons) or "(brak)",
        "{{TEXT_HEAD_LIMIT}}": str(text_head_limit),
        "{{TEXT_HEAD}}": text_head or "(brak wyekstrahowanego tekstu)",
        "{{MODEL_HINT}}": model_hint,
    }
    prompt = template
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def normalize_decision(
    decision: Any,
    *,
    row: dict[str, Any],
    subject: config.Subject,
    model: str,
    schema: dict[str, Any],
    auto_apply: float,
    review_min: float,
    categories: Sequence[str],
) -> dict[str, Any]:
    """Domyka odpowiedź modelu do kontraktu planu; podnosi ``ValueError`` gdy się nie da.

    Model bywa niedbały w rzeczach, które i tak znamy lepiej od niego (sha, method,
    model, progi review) — te pola nadpisujemy zamiast odrzucać całą odpowiedź.
    Rzeczy, których nie wolno zgadywać (kategoria spoza ``forms`` przedmiotu, brak
    ścieżki docelowej dla ``copy``) są twardym błędem pozycji.
    """
    if not isinstance(decision, dict):
        raise ValueError(f"odpowiedź nie jest obiektem JSON: {decision!r}")
    sha = str(row.get("sha256") or row.get("source_sha256"))
    out = dict(decision)

    out["schema_version"] = 1
    out["source_sha256"] = sha  # model nie może podmienić tożsamości treści
    out["method"] = "llm"
    out["model"] = model
    out.setdefault("related_to", None)
    out.setdefault("relation", None)
    # Rok bywa zwracany jako "2023/2024" albo "brak" — schemat wymaga 4 cyfr albo null.
    # To nie jest zgadywanie, tylko odrzucenie wartości, której i tak nie umiemy użyć.
    year = out.get("year")
    out["year"] = year if isinstance(year, str) and year.isdigit() and len(year) == 4 else None

    try:
        confidence = float(out.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    out["confidence"] = min(max(confidence, 0.0), 1.0)

    category = str(out.get("category") or "inne")
    allowed = set(categories)
    if category not in allowed:
        raise ValueError(
            f"kategoria {category!r} niedozwolona dla form {sorted(subject.forms)}; "
            f"dozwolone: {sorted(allowed)}"
        )
    out["category"] = category

    # Progi z thresholds.yaml są wiążące — pewność deklarowana przez model nie może
    # przepchnąć pozycji obok review (AGENTS.md: próg pewności z konfiguracji).
    if out["confidence"] < review_min:
        out["action"] = "quarantine"
    action = str(out.get("action") or "quarantine")
    if action not in {"copy", "quarantine", "skip", "media"}:
        raise ValueError(f"nieznana akcja {action!r}")
    out["action"] = action
    out["needs_review"] = bool(
        action == "quarantine" or out["confidence"] < auto_apply or out.get("needs_review")
    )

    if not str(out.get("target_rel") or "").strip():
        if action == "copy":
            raise ValueError("action=copy bez target_rel")
        out["target_rel"] = f"{subject.target_dir}/inne/{_filename(row)}"

    reason = str(out.get("reason") or "").strip() or "brak uzasadnienia od modelu"
    out["reason"] = reason[:240]

    jsonschema.validate(out, schema)
    return out


def _append_atomic(row: dict[str, Any], output: Path) -> None:
    """Dopisuje jedną decyzję i wymusza zapis na dysk — przerwany przebieg ma być wznawialny."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _check_output(output: Path, paths: config.Paths) -> None:
    resolved = Path(os.path.abspath(output))
    for protected in (paths.sources, paths.target_repo, paths.media):
        if resolved.is_relative_to(Path(os.path.abspath(protected))):
            raise ValueError(f"zapis planu w chronionym drzewie jest zabroniony: {output}")
    if output.is_symlink():
        raise ValueError(f"plik wyjściowy nie może być symlinkiem: {output}")


def _thresholds() -> tuple[float, float]:
    data = config.load_thresholds().get("confidence") or {}
    auto = float(data.get("auto_apply", _FALLBACK_AUTO_APPLY))
    review = float(data.get("review_min", _FALLBACK_REVIEW_MIN))
    return auto, review


@app.command()
def resolve(
    semester: int = typer.Option(..., "--semester", min=1, max=7),
    skrot: str = typer.Option(..., "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", help="Domyślnie manifest_slice.jsonl z prepare_subject.py."
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Domyślnie plan.ai.jsonl obok manifestu."
    ),
    task: str = typer.Option("classify", "--task", help="Zadanie z thresholds.yaml: llm."),
    limit: Optional[int] = typer.Option(None, "--limit", min=1, help="Najwyżej N pozycji."),
    take_all: bool = typer.Option(
        False, "--all", help="Wyślij też pozycje bez needs_review (drogie; tylko na żądanie)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Pokaż, co poszłoby do modelu; nie wołaj backendu."
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Pomiń cache decyzji AI."),
) -> None:
    """Rozstrzygnij resztki jednego przedmiotu; nie zmieniaj materiałów ani bazy."""
    from prepare_subject import default_output as manifest_default  # lokalnie: wspólna konwencja

    try:
        subjects = config.iter_subjects()
        subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        paths = config.load_paths()

        manifest_path = manifest or manifest_default(subject, subjects)
        if not manifest_path.is_file():
            raise ValueError(
                f"brak manifestu: {manifest_path} — najpierw `just subject-prepare`"
            )
        out_path = output or manifest_path.parent / "plan.ai.jsonl"
        _check_output(out_path, paths)

        rows = read_jsonl(manifest_path)
        resolved = existing_hashes(out_path)
        selected = select_rows(rows, resolved=resolved, take_all=take_all)
        if limit is not None:
            selected = selected[:limit]

        cfg = load_llm_config()
        if no_cache:
            cfg = dataclasses.replace(cfg, cache=False)
        task_cfg = cfg.task(task)
        model_hint = task_cfg.model or task_cfg.backend
        auto_apply, review_min = _thresholds()
        template = _PROMPT_PATH.read_text(encoding="utf-8")
        schema = load_schema()
        schema_for_backend = wire_schema(schema)
        categories = allowed_categories(subject)
    except (KeyError, ValueError, OSError) as exc:
        typer.echo(f"Błąd przygotowania: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"przedmiot: SEM{subject.semester}/{subject.grupa}/{subject.skrot} · "
        f"manifest: {len(rows)} · do rozstrzygnięcia: {len(selected)} · "
        f"już rozstrzygnięte: {len(resolved)} · backend: {task_cfg.backend}/{model_hint}"
    )
    if dry_run:
        for row in selected:
            typer.echo(f"  {row.get('sha256')}  {_filename(row)}")
        typer.echo("dry-run: nie wołano backendu")
        return
    if not selected:
        typer.echo("nic do zrobienia")
        return

    client = LLMClient(cfg)
    written = 0
    failed: list[tuple[str, str]] = []
    actions: dict[str, int] = {}
    review_count = 0

    for row in selected:
        sha = str(row.get("sha256") or row.get("source_sha256"))
        prompt = build_prompt(
            row,
            subject=subject,
            template=template,
            model_hint=model_hint,
            text_head_limit=cfg.max_text_head_bytes,
            categories=categories,
        )
        try:
            result = client.complete(task, prompt, schema=schema_for_backend)
            decision = normalize_decision(
                result.data,
                row=row,
                subject=subject,
                model=result.model or task_cfg.backend,
                schema=schema,
                auto_apply=auto_apply,
                review_min=review_min,
                categories=categories,
            )
        except (LLMError, LLMParseError, ValueError, jsonschema.ValidationError) as exc:
            failed.append((sha, str(exc)))
            continue
        _append_atomic(decision, out_path)
        written += 1
        actions[decision["action"]] = actions.get(decision["action"], 0) + 1
        review_count += bool(decision["needs_review"])

    typer.echo(f"plan AI: {out_path}")
    typer.echo(
        f"zapisano: {written} · "
        f"akcje: {', '.join(f'{k}={v}' for k, v in sorted(actions.items())) or 'brak'} · "
        f"needs_review: {review_count} · błędy: {len(failed)}"
    )
    for sha, message in failed[:10]:
        typer.echo(f"  BŁĄD {sha[:12]}… {message}", err=True)
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
