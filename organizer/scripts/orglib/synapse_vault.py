"""C3: indeks organizera → vault dla `synapse`. Czysta funkcja, bez bazy i bez plików.

Kontrakt jest cudzy i wzięty z REALNEGO repo (`vendor/synapse`), nie z prototypu:
`Synapse.Generator` skanuje katalog `.md`, czyta YAML front matter przez konfigurowalne
mapowanie i buduje `graph.json` wg `schema/graph.schema.v2.json`. Rzeczy, które z tego
wynikają i których nie wolno „uprościć”:

- **`id` węzła to nazwa pliku bez rozszerzenia**, nie pole front mattera. Musi być
  unikalna w CAŁYM vaulcie — dwa pliki o tym samym rdzeniu dają ostrzeżenie
  `duplicate-id` i jeden z nich przestaje być celem linków.
- **Relacje deklarujemy w `relations:`**, bo tylko one niosą RODZAJ powiązania.
  `[[wikilink]]` w treści też tworzy krawędź, ale zawsze rodzaju `link` — dlatego
  treść notatki celowo NIE zawiera wikilinków: nawigację po relacjach robi panel
  szczegółów, a każda krawędź ma wtedy jednoznaczny rodzaj i nie dubluje się.
- **Cel relacji spoza vaulta staje się ghost node'em**, więc materiał bez decyzji
  pokazujemy jako ghost zamiast go ukrywać (decyzja użytkownika 2026-09-19).
- `status` musi być jednym z `not-started` / `in-progress` / `completed` (inaczej
  generator zapisze `null`), a `level` liczbą >= 1.

Hierarchia: `semester` → `subject` → `file`. Dziecko wskazuje rodzica relacją
`belongs_to` — jedna pozycja na notatkę, zamiast listy kilku tysięcy dzieci w jednej.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

#: Typy węzłów, których używa ten vault (pole `type`; generator nie narzuca słownika).
NODE_SEMESTER = "semester"
NODE_SUBJECT = "subject"
#: Kategoria materiału (kolokwia, laboratoria, wykład…) jako węzeł POŚREDNI między
#: przedmiotem a plikami. Bez niej przedmiot jest gwiazdą o tysiącach szprych: nie widać
#: w niej, co jest czym, a każda szprycha biegnie przez pół grafu.
NODE_CATEGORY = "category"
NODE_FILE = "file"

#: Rodzaje krawędzi. `belongs_to` to szkielet hierarchii, reszta pochodzi z etapu B6.
EDGE_BELONGS_TO = "belongs_to"
EDGE_NEAR_DUPLICATE = "near_duplicate"
EDGE_OLDER_VERSION = "older_version"
EDGE_RELATED = "related"

#: Statusy dozwolone przez `ConfigurableFrontmatterMapper.NormalizeStatus`.
STATUS_DONE = "completed"
STATUS_ACTIVE = "in-progress"
STATUS_TODO = "not-started"
STATUSES = (STATUS_TODO, STATUS_ACTIVE, STATUS_DONE)

#: Znaczenie poziomów w TYM vaulcie (decyzja użytkownika: „jak bardzo ustalony”).
LEVEL_IN_PACKAGE = 1
LEVEL_PLANNED = 2
LEVEL_NEEDS_HUMAN = 3
LEVEL_MEANING = {
    LEVEL_IN_PACKAGE: "leży już w paczce (ground truth)",
    LEVEL_PLANNED: "plan pewny — decyzja powyżej progu auto",
    LEVEL_NEEDS_HUMAN: "wymaga człowieka — review albo brak rozstrzygnięcia",
}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, limit: int = 40) -> str:
    """Slug ASCII: bez diakrytyków, tylko [a-z0-9-]. Ta sama normalizacja co w klasyfikacji."""
    folded = unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    slug = _SLUG_STRIP.sub("-", folded).strip("-")
    return slug[:limit].strip("-") or "bez-nazwy"


@dataclass(frozen=True)
class Relation:
    """Jedna pozycja `relations:` we front matterze."""

    target: str
    kind: str
    confidence: float | None = None

    def as_frontmatter(self) -> dict[str, Any]:
        row: dict[str, Any] = {"target": self.target, "kind": self.kind}
        if self.confidence is not None:
            row["confidence"] = round(float(self.confidence), 4)
        return row


@dataclass
class Note:
    """Jedna notatka vaulta. ``id`` jest jednocześnie nazwą pliku."""

    id: str
    title: str
    type: str
    category: str
    body: str
    level: int | None = None
    status: str | None = None
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    modified: str | None = None
    relations: list[Relation] = field(default_factory=list)
    #: Katalog w vaulcie (bez nazwy pliku); pusty = korzeń.
    folder: str = ""

    @property
    def path(self) -> str:
        return f"{self.folder}/{self.id}.md" if self.folder else f"{self.id}.md"

    def validate(self) -> None:
        if self.status is not None and self.status not in STATUSES:
            raise ValueError(f"{self.id}: status {self.status!r} spoza {STATUSES}")
        if self.level is not None and self.level < 1:
            raise ValueError(f"{self.id}: level {self.level} — schemat wymaga >= 1")
        if self.id != slugify(self.id, limit=len(self.id)):
            raise ValueError(f"{self.id}: id musi być slugiem (jest nazwą pliku)")


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def render_note(note: Note) -> str:
    """Notatka jako plik `.md`: YAML front matter + treść. Bez wikilinków — patrz docstring."""
    lines = ["---", f"title: {_yaml_scalar(note.title)}", f"type: {_yaml_scalar(note.type)}",
             f"category: {_yaml_scalar(note.category)}"]
    if note.level is not None:
        lines.append(f"level: {note.level}")
    if note.status is not None:
        lines.append(f"status: {_yaml_scalar(note.status)}")
    if note.tags:
        lines.append("tags: [" + ", ".join(_yaml_scalar(t) for t in note.tags) + "]")
    if note.aliases:
        lines.append("aliases: [" + ", ".join(_yaml_scalar(a) for a in note.aliases) + "]")
    if note.modified:
        lines.append(f"modified: {_yaml_scalar(note.modified)}")
    if note.relations:
        lines.append("relations:")
        for relation in note.relations:
            row = relation.as_frontmatter()
            lines.append(f"  - target: {_yaml_scalar(row['target'])}")
            lines.append(f"    kind: {_yaml_scalar(row['kind'])}")
            if "confidence" in row:
                lines.append(f"    confidence: {row['confidence']}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + note.body.strip() + "\n"


# -- identyfikatory ---------------------------------------------------------


#: Ile znaków sha256 wchodzi w id notatki. Ta liczba jest KONTRAKTEM: po niej
#: studio odnajduje treść, którą pokazuje graf (`orglib/graph_link.py`), więc
#: zmiana tutaj zmienia znaczenie wszystkich identyfikatorów w vaulcie.
ID_SHA_PREFIX = 8


def semester_id(semester: int) -> str:
    return f"sem{semester}"


def subject_id(semester: int, skrot: str, grupa: str = "", *, ambiguous: bool = False) -> str:
    parts = [f"sem{semester}", slugify(skrot, limit=16)]
    if ambiguous and grupa:
        parts.append(slugify(grupa, limit=20))
    return "-".join(parts)


def category_id(subject_note_id: str, category: str) -> str:
    """Id węzła kategorii w obrębie przedmiotu.

    Wstawka ``-kat-`` nie jest ozdobnikiem: bez niej kategoria o nazwie zbieżnej ze
    skrótem innego przedmiotu dałaby kolizję id, a kolizja w tym vaulcie oznacza
    ostrzeżenie ``duplicate-id`` i notatkę, która przestaje być celem relacji.
    """
    return f"{subject_note_id}-kat-{slugify(category, limit=20)}"


def file_id(skrot: str, sha256: str, filename: str = "") -> str:
    """Nazwa pliku notatki = id węzła. Czytelny fragment + skrót sha dla jednoznaczności."""
    name = slugify(filename, limit=28) if filename else ""
    parts = [slugify(skrot, limit=12)]
    if name and name != "bez-nazwy":
        parts.append(name)
    parts.append(sha256[:ID_SHA_PREFIX])
    return "-".join(parts)


def unassigned_id(sha256: str, filename: str = "") -> str:
    """Cel relacji spoza paczki. Zostanie ghost node'em — widocznym, nie zgubionym."""
    name = slugify(filename, limit=24) if filename else ""
    parts = ["nieprzypisane"] + ([name] if name and name != "bez-nazwy" else []) + [
        sha256[:ID_SHA_PREFIX]
    ]
    return "-".join(parts)


# -- tłumaczenie stanu potoku ----------------------------------------------


def file_level(*, in_package: bool, needs_review: bool, confidence: float, auto_apply: float) -> int:
    if in_package:
        return LEVEL_IN_PACKAGE
    if needs_review or confidence < auto_apply:
        return LEVEL_NEEDS_HUMAN
    return LEVEL_PLANNED


def file_status(action: str, *, in_package: bool) -> str:
    if in_package:
        return STATUS_DONE
    return STATUS_ACTIVE if action in ("copy", "media") else STATUS_TODO


def subject_level(*, ground_truth: int, planned: int, needs_review: int) -> int:
    if needs_review or (not ground_truth and not planned):
        return LEVEL_NEEDS_HUMAN
    return LEVEL_PLANNED if planned else LEVEL_IN_PACKAGE


def subject_status(*, ground_truth: int, planned: int, needs_review: int) -> str:
    """``completed`` = nic tu teraz nie stoi, nie „skończone na zawsze”.

    Organizer nie wie, czy paczka jest kompletna merytorycznie — wie tylko, czy coś
    czeka na decyzję. To jedyne uczciwe tłumaczenie na słownik viewera.
    """
    if planned and needs_review:
        return STATUS_ACTIVE
    if planned:
        return STATUS_DONE if ground_truth else STATUS_ACTIVE
    return STATUS_DONE if ground_truth else STATUS_TODO


def dedupe_ids(notes: Sequence[Note]) -> list[Note]:
    """Id jest nazwą pliku i celem relacji — kolizja oznacza `duplicate-id` w generatorze."""
    seen: dict[str, int] = {}
    out: list[Note] = []
    for note in notes:
        if note.id in seen:
            seen[note.id] += 1
            note.id = f"{note.id}-{seen[note.id]}"
        else:
            seen[note.id] = 1
        out.append(note)
    return out


def vault_readme(notes: Sequence[Note], generated_at: str) -> str:
    """README vaulta: co znaczą pola, skąd się wziął i czego w nim nie ma (gita)."""
    by_type: dict[str, int] = {}
    for note in notes:
        by_type[note.type] = by_type.get(note.type, 0) + 1
    rows = "\n".join(f"| `{t}` | {c} |" for t, c in sorted(by_type.items()))
    levels = "\n".join(f"- **L{level}** — {meaning}" for level, meaning in LEVEL_MEANING.items())
    return f"""# Vault paczki — generowany

Powstaje ze `scripts/synapse_export.py` (`just synapse`) z operacyjnego indeksu organizera.
**Nie edytuj notatek ręcznie** — kolejny eksport nadpisuje katalog w całości.

- Wygenerowano: {generated_at}
- Notatek: {len(notes)}

| typ węzła | ile |
|---|---:|
{rows}

## Co znaczy `level`

{levels}

## Czego tu nie ma

Vault **nie jest repozytorium gita** (decyzja użytkownika): to widok bieżącego stanu,
a nie historia zmian. Historia decyzji żyje w bazie organizera, historia materiałów
w repo paczki. Generator uruchamiany z `--no-git` nie próbuje więc czytać `git log`,
a pole `history` po prostu nie powstaje.

## Jak z tego zrobić graf

```bash
dotnet run --project vendor/synapse/Synapse.Generator/Synapse.Generator \\
  -- --vault <ten katalog> --out <viewer>/public/graph.json --no-git
```
"""
