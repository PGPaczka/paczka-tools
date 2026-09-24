"""B9: strona przeglądu jednego przedmiotu — jedna decyzja człowieka, na piśmie.

Kontrakt:

- wejście — artefakty wcześniejszych etapów z katalogu przedmiotu: ``plan.jsonl`` (B7),
  ``validation.jsonl`` (B8), ``unresolved.jsonl`` (B3), ``relations.jsonl`` (B6)
  i ``manifest_slice.jsonl`` (B1); głowy tekstu czytamy z ``work/extracted_text``;
- wyjście — ``review.html`` obok planu: samowystarczalna strona (miniatury wbudowane
  jako ``data:``), którą można otworzyć, przesłać i skomentować bez dostępu do repo;
- materiałów nie zmienia. Ze źródeł **czyta** wyłącznie obrazy, żeby zrobić miniatury,
  i tylko przez ``config.resolve_within_sources`` (containment ścieżek).

Po co ta strona: człowiek jest bramką raz na przedmiot, nie raz na plik. Ma zobaczyć
to, czego nie rozstrzygnie żadna heurystyka — czy plan gdzieś się nie wykłada (B8),
które pozycje są niepewne, czego nikt nie rozstrzygnął i **która wersja materiału jest
kanoniczna** (diff tekstu albo dwie miniatury obok siebie). Reszta planu jest
policzona w nagłówku i nie wymaga czytania linia po linii.

Strona niczego nie zatwierdza. Zgoda na `apply` jest osobną, jawną decyzją użytkownika.
"""

from __future__ import annotations

import base64
import difflib
import html
import os
from pathlib import Path
from typing import Any, Optional

import typer

from orglib import config, folder_links, preview
from orglib.jsonl import read_jsonl
from orglib.plan_build import META_KEY
from orglib.review import Item, Review, build_review, is_image, is_text, pair_for_diff

app = typer.Typer(add_completion=False, help=__doc__)

REPORT_NAME = "review.html"

#: Rozmiar miniatury (dłuższy bok) i jakość JPEG — ma się mieścić w mailu, nie w galerii.
#: Same wartości i liczenie żyją w ``orglib.preview`` — raport i studio mają
#: dzielić jeden cache w ``work/thumbnails``, a nie liczyć go dwa razy po swojemu.
THUMBNAIL_SIZE = preview.THUMBNAIL_SIZE
THUMBNAIL_QUALITY = preview.THUMBNAIL_QUALITY

_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0 auto; max-width: 78rem;
       padding: 1.5rem 1rem 4rem; line-height: 1.5; }
h1 { margin-bottom: .2rem; } h2 { margin-top: 2.2rem; border-bottom: 1px solid #8884; padding-bottom: .2rem; }
.sub { color: #777; margin-top: 0; }
.cards { display: flex; flex-wrap: wrap; gap: .6rem; margin: 1rem 0; }
.card { border: 1px solid #8884; border-radius: .5rem; padding: .5rem .8rem; min-width: 7rem; }
.card b { display: block; font-size: 1.5rem; line-height: 1.2; }
.card span { color: #777; font-size: .85rem; }
.bad b { color: #c0392b; } .warn b { color: #b8860b; } .ok b { color: #227d51; }
table { border-collapse: collapse; width: 100%; font-size: .88rem; }
th, td { border: 1px solid #8883; padding: .3rem .45rem; text-align: left; vertical-align: top; }
th { background: #8881; }
td.num { text-align: right; white-space: nowrap; }
code, .path { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .85em; word-break: break-all; }
.cluster { border: 1px solid #8884; border-radius: .5rem; padding: .8rem; margin: 1rem 0; }
.cluster h3 { margin: 0 0 .4rem; font-size: 1rem; }
.pair { display: flex; gap: 1rem; flex-wrap: wrap; }
.pair figure { margin: 0; max-width: 20rem; }
.pair img { max-width: 100%; border: 1px solid #8884; border-radius: .3rem; }
figcaption { font-size: .8rem; color: #777; }
.tag { display: inline-block; border-radius: .25rem; padding: 0 .35rem; font-size: .8rem;
       border: 1px solid #8886; margin-right: .3rem; }
.note { color: #777; font-size: .9rem; }
table.diff { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .8rem; }
.diff_header { background: #8882; color: #777; }
td.diff_header { text-align: right; }
.diff_next { background: #8881; }
.diff_add { background: #b6f0c4; color: #062; }
.diff_chg { background: #ffe9a8; color: #640; }
.diff_sub { background: #ffc6c6; color: #900; }
@media (prefers-color-scheme: dark) {
  .diff_add { background: #17491f; color: #b6f0c4; }
  .diff_chg { background: #4a3c10; color: #ffe9a8; }
  .diff_sub { background: #4d1616; color: #ffc6c6; }
}
footer { margin-top: 3rem; color: #777; font-size: .9rem; }
"""


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _text_head(sha: str, paths: config.Paths, limit: int) -> list[str]:
    """Głowa tekstu z etapu extract — wyłącznie z ``work``, nigdy ze źródeł."""
    path = paths.work_extracted_text / f"{sha}.txt"
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return content.splitlines()[:limit]


def _thumbnail(item: Item, paths: config.Paths) -> str | None:
    """Miniatura obrazu jako ``data:`` URI; ``None``, gdy się nie da (i to jest w porządku).

    Plik miniatury zostaje w ``work/thumbnails``, więc kolejny przebieg jej nie liczy
    od nowa — ta sama zasada „praca raz na treść”, co w etapie extract.
    """
    package, _, relative = item.source_path.partition("/")
    source = config.resolve_within_sources(paths.sources, package, relative)
    cache = preview.thumbnail(paths, item.sha256, source)
    if cache is None:
        return None
    try:
        payload = base64.b64encode(cache.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/jpeg;base64,{payload}"


def _card(value: Any, label: str, css: str = "") -> str:
    return f'<div class="card {css}"><b>{_escape(value)}</b><span>{_escape(label)}</span></div>'


def _items_table(items: list[Item], *, with_confidence: bool = True) -> str:
    head = "<tr><th>plik źródłowy</th><th>cel</th><th>kategoria</th>"
    head += "<th>pewność</th><th>uzasadnienie</th></tr>" if with_confidence else "<th>uzasadnienie</th></tr>"
    rows = []
    for item in items:
        cells = [
            f'<span class="path">{_escape(item.source_path or "—")}</span>',
            f'<span class="path">{_escape(item.target_rel)}</span>',
            _escape(item.category),
        ]
        if with_confidence:
            cells.append(f'<span class="num">{item.confidence:.2f}</span>')
        cells.append(f"{_escape(item.reason)} <span class='tag'>{_escape(item.method)}</span>")
        rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return f"<table>{head}{''.join(rows)}</table>"


def _findings_table(findings: list[dict[str, Any]]) -> str:
    rows = [
        "<tr><td>{code}</td><td>{message}</td><td><span class='path'>{target}</span></td></tr>".format(
            code=_escape(f.get("code")),
            message=_escape(f.get("message")),
            target=_escape(f.get("target_rel") or "—"),
        )
        for f in findings
    ]
    return f"<table><tr><th>kod</th><th>opis</th><th>cel</th></tr>{''.join(rows)}</table>"


def _cluster_html(
    review: Review, paths: config.Paths, *, max_clusters: int, diff_lines: int
) -> str:
    parts: list[str] = []
    shown = 0
    for cluster in review.clusters:
        if shown >= max_clusters:
            break
        pair = pair_for_diff(cluster, review.items)
        if pair is None:
            continue
        left, right = pair
        shown += 1
        kind = "starsza kontra nowsza wersja" if cluster.has_older_version() else "bliskie duplikaty"
        header = (
            f"<h3>{_escape(kind)} · {cluster.size} treści · "
            f"najmocniejsza relacja {cluster.strength:.2f}</h3>"
        )
        body = ""
        if is_image(left) and is_image(right):
            figures = []
            for item in (left, right):
                source = _thumbnail(item, paths)
                image = (
                    f'<img src="{source}" alt="{_escape(item.filename)}">' if source
                    else "<p class='note'>(nie udało się zrobić miniatury)</p>"
                )
                figures.append(
                    f"<figure>{image}<figcaption>{_escape(item.source_path)}</figcaption></figure>"
                )
            body = f'<div class="pair">{"".join(figures)}</div>'
        elif is_text(left) and is_text(right):
            left_lines = _text_head(left.sha256, paths, diff_lines)
            right_lines = _text_head(right.sha256, paths, diff_lines)
            if left_lines or right_lines:
                body = difflib.HtmlDiff(wrapcolumn=76).make_table(
                    left_lines, right_lines,
                    fromdesc=_escape(left.filename), todesc=_escape(right.filename),
                    context=True, numlines=2,
                )
            else:
                body = "<p class='note'>(brak wyekstrahowanego tekstu — uruchom `just extract`)</p>"
        else:
            body = "<p class='note'>(różne rodzaje treści — porównaj ręcznie)</p>"
        members = "".join(
            f"<li><span class='path'>{_escape(review.items[sha].source_path)}</span> → "
            f"<span class='path'>{_escape(review.items[sha].target_rel)}</span></li>"
            for sha in cluster.members
            if sha in review.items
        )
        parts.append(
            f'<div class="cluster">{header}{body}<details><summary>wszystkie treści w klastrze'
            f"</summary><ul>{members}</ul></details></div>"
        )
    if not parts:
        return "<p class='note'>Brak klastrów do obejrzenia.</p>"
    if len(review.clusters) > shown:
        parts.append(
            f"<p class='note'>Pokazano {shown} z {len(review.clusters)} klastrów "
            f"(największe i najpewniejsze). Reszta jest w relations.jsonl.</p>"
        )
    return "".join(parts)


def render(review: Review, paths: config.Paths, *, max_clusters: int, diff_lines: int,
           max_rows: int, plan_path: Path) -> str:
    meta = review.meta
    counts = review.counts
    verdict = (
        "<span class='tag' style='border-color:#c0392b'>plan odrzucony przez walidację</span>"
        if counts["bledy"] else
        "<span class='tag' style='border-color:#227d51'>walidacja bez błędów</span>"
    )
    cards = "".join([
        _card(counts["pozycje"], "pozycji planu"),
        _card(counts["do_kopiowania"], "do skopiowania"),
        _card(counts["pomijane"], "pomijanych"),
        _card(counts["media"], "poza paczkę (media)"),
        _card(counts["needs_review"], "do obejrzenia", "warn" if counts["needs_review"] else "ok"),
        _card(counts["unresolved"], "nierozstrzygniętych", "warn" if counts["unresolved"] else "ok"),
        _card(counts["klastry"], "klastrów podobieństwa"),
        _card(counts["bledy"], "błędów walidacji", "bad" if counts["bledy"] else "ok"),
    ])
    unresolved_rows = "".join(
        "<tr><td><span class='path'>{path}</span></td><td>{kind}</td><td>{why}</td></tr>".format(
            path=_escape(row.get("source_path") or row.get("sha256")),
            kind=_escape(row.get("content_kind") or "—"),
            why=_escape(", ".join(row.get("classify_reasons") or row.get("review_reasons") or [])),
        )
        for row in review.unresolved[:max_rows]
    )
    media_rows = "".join(
        f"<tr><td><span class='path'>{_escape(item.source_path)}</span></td>"
        f"<td><span class='path'>{_escape(item.target_rel)}</span></td>"
        f"<td class='num'>{item.size_bytes / 1_048_576:.1f} MB</td></tr>"
        for item in review.media
    )
    tree_rows = "".join(f"<li><span class='path'>{_escape(folder)}</span></li>" for folder in review.tree)
    links_rows = "".join(
        f"<tr><td class='path'>{_escape(str(link.get('folder_a') or ''))}</td>"
        f"<td class='path'>{_escape(str(link.get('folder_b') or ''))}</td>"
        f"<td>{'ten sam materiał' if link.get('kind') == 'duplicate' else 'powiązane'}</td>"
        f"<td>{_escape(str(link.get('note') or ''))}</td></tr>"
        for link in review.folder_links
    )
    return f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review: {_escape(meta.get("subject_key"))} SEM{_escape(meta.get("semester"))}</title>
<style>{_CSS}</style></head><body>
<h1>{_escape(meta.get("subject_key"))} · semestr {_escape(meta.get("semester"))}</h1>
<p class="sub">{_escape(meta.get("target_dir"))} · plan_hash <code>{_escape(str(meta.get("plan_hash"))[:16])}…</code>
 · zbudowany {_escape(meta.get("created_at"))} · {verdict}</p>
<div class="cards">{cards}</div>

<h2>1. Ustalenia walidacji</h2>
{_findings_table(review.errors) if review.errors else "<p class='note'>Brak błędów.</p>"}
{"<h3>Ostrzeżenia</h3>" + _findings_table(review.warnings[:max_rows]) if review.warnings else ""}

<h2>2. Pozycje do obejrzenia ({counts['needs_review']})</h2>
<p class="note">Reguły coś wybrały, ale poniżej progu automatu. Od najmniej pewnych.</p>
{_items_table(review.needs_review[:max_rows]) if review.needs_review else "<p class='note'>Brak.</p>"}

<h2>3. Nierozstrzygnięte ({counts['unresolved']})</h2>
<p class="note">Ani reguły, ani model nie wiedzą. Do decyzji albo do <code>just subject-ai-resolve</code>.</p>
{f"<table><tr><th>plik</th><th>rodzaj</th><th>powód</th></tr>{unresolved_rows}</table>" if unresolved_rows else "<p class='note'>Brak.</p>"}

<h2>4. Podobne treści ({counts['klastry']} klastrów)</h2>
<p class="note">Tu rozstrzygasz, która wersja jest kanoniczna. Nic nie jest kasowane —
starsza wersja zostaje w paczce jako relacja, a <code>outdated/</code> to zawsze Twoja decyzja.</p>
{_cluster_html(review, paths, max_clusters=max_clusters, diff_lines=diff_lines)}

<h2>5. Poza paczkę ({counts['media']})</h2>
{f"<table><tr><th>źródło</th><th>cel w 90_MEDIA</th><th>rozmiar</th></tr>{media_rows}</table>" if media_rows else "<p class='note'>Brak.</p>"}

<h2>6. Ręcznie powiązane katalogi ({counts.get('powiazane_katalogi', 0)})</h2>
<p class="note">Pary wskazane przez człowieka: „to jest ten sam materiał", choć automatyczny
dedup ich nie łączy (poddrzewa nie są identyczne). Powiązanie niczego nie wycina z potoku —
podpowiada przy decyzjach hurtowych.</p>
{f"<table><tr><th>katalog</th><th>katalog</th><th>rodzaj</th><th>notatka</th></tr>{links_rows}</table>" if links_rows else "<p class='note'>Brak.</p>"}

<h2>7. Drzewo po zmianie ({len(review.tree)} katalogów)</h2>
<details><summary>pokaż katalogi</summary><ul>{tree_rows}</ul></details>

<footer>
<p>Wygenerowane z <code>{_escape(plan_path)}</code>. Strona niczego nie zatwierdza:
zgoda na <code>apply</code> jest osobną, jawną decyzją. Gdy plan wymaga zmian, popraw
wejście (reguły w <code>config/syntax.yaml</code>, decyzje ręczne) i zbuduj go od nowa —
nie edytuj <code>plan.jsonl</code> ręcznie, bo <code>plan_hash</code> przestanie się zgadzać.</p>
</footer>
</body></html>
"""


@app.command()
def review(
    semester: int = typer.Option(..., "--semester", min=1, max=7),
    skrot: str = typer.Option(..., "--skrot"),
    grupa: Optional[str] = typer.Option(None, "--grupa", help="Grupa z subjects.yaml."),
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", help="Domyślnie manifest_slice.jsonl z prepare_subject.py."
    ),
    out_dir: Optional[Path] = typer.Option(
        None, "--out-dir", help="Katalog wyjściowy; domyślnie katalog planu."
    ),
    max_clusters: int = typer.Option(25, "--max-clusters", min=0, help="Ile klastrów pokazać."),
    diff_lines: int = typer.Option(120, "--diff-lines", min=10, help="Ile linii tekstu w diffie."),
    max_rows: int = typer.Option(200, "--max-rows", min=10, help="Limit wierszy w tabelach."),
) -> None:
    """Zbuduj stronę przeglądu; nie zmieniaj materiałów i nie zatwierdzaj planu."""
    from prepare_subject import default_output as manifest_default

    try:
        subjects = config.iter_subjects()
        subject = config.find_subject(semester, skrot, subjects, grupa=grupa)
        paths = config.load_paths()

        manifest_path = manifest or manifest_default(subject, subjects)
        if not manifest_path.is_file():
            raise ValueError(f"brak manifestu: {manifest_path} — najpierw `just subject-prepare`")
        base = manifest_path.parent
        plan_path = base / "plan.jsonl"
        if not plan_path.is_file():
            raise ValueError(f"brak planu: {plan_path} — najpierw `just subject-plan`")

        target_dir = out_dir if out_dir is not None else base
        output = target_dir / REPORT_NAME
        config.check_output_target(output, paths)

        lines = read_jsonl(plan_path)
        meta = next((line[META_KEY] for line in lines if META_KEY in line), {})
        plan_rows = [line for line in lines if META_KEY not in line]
        review_model = build_review(
            plan=plan_rows,
            meta=meta,
            manifest=read_jsonl(manifest_path),
            validation=read_jsonl(base / "validation.jsonl") if (base / "validation.jsonl").is_file() else [],
            unresolved=read_jsonl(base / "unresolved.jsonl") if (base / "unresolved.jsonl").is_file() else [],
            relations=read_jsonl(base / "relations.jsonl") if (base / "relations.jsonl").is_file() else [],
            # Powiązania katalogów są globalne, więc leżą w `reports/`, a nie przy przedmiocie.
            # Raport, jak reszta jego wejść, czyta JSONL — bazy tu świadomie nie otwieramy.
            folder_links=read_jsonl(folder_links.EXPORT_PATH)
            if folder_links.EXPORT_PATH.is_file() else [],
        )
        page = render(
            review_model, paths,
            max_clusters=max_clusters, diff_lines=diff_lines, max_rows=max_rows,
            plan_path=plan_path,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(page, encoding="utf-8")
    except (KeyError, ValueError, OSError) as exc:
        typer.echo(f"Błąd przygotowania przeglądu: {exc}", err=True)
        raise typer.Exit(code=1)

    counts = review_model.counts
    typer.echo(
        f"przedmiot: SEM{subject.semester}/{subject.grupa}/{subject.skrot} · "
        f"pozycje: {counts['pozycje']} · do obejrzenia: {counts['needs_review']} · "
        f"nierozstrzygnięte: {counts['unresolved']} · klastry: {counts['klastry']}"
    )
    typer.echo(
        f"walidacja: błędy {counts['bledy']}, ostrzeżenia {counts['ostrzezenia']}"
        + (" — PLAN NIE PRZECHODZI, popraw przed apply" if counts["bledy"] else "")
    )
    typer.echo(f"review: {output} ({os.path.getsize(output) / 1024:.0f} kB)")


if __name__ == "__main__":
    app()
