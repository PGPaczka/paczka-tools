"""C3: mapowanie indeksu organizera na model notatek `synapse`. Czysta funkcja.

`synapse` (repo użytkownika, `~/dev/synapse`) jest **prototypem designu**, nie działającą
aplikacją: jego dane siedzą w `seedNotes()` w `SynapseVariants.dc.html`. Ten moduł
przekłada to, co organizer wie o materiałach, na dokładnie ten kształt notatki, żeby
graf dało się karmić realnymi danymi, a nie atrapą o Dockerze.

Kontrakt notatki odczytany z prototypu (pola, po które sięga UI):
``id``, ``title``, ``category``, ``level``, ``status``, ``tags``, ``links``, ``path``,
``body``, ``modified``, ``activity``.

**Twarde ograniczenie prototypu:** ``level`` jest tam zaszyte jako ``[1, 2, 3]``
(``levelList=[1,2,3].map(...)`` buduje filtr, a fizyka grafu liczy ``level*2.2``).
Semestr 1-7 nie zmieści się w tym polu bez zepsucia filtrów, więc **semestr idzie do
``category`` i do tagów**, a ``level`` niesie to, co ma dokładnie trzy stopnie i jest
w tym projekcie decyzyjne: **jak bardzo materiał jest ustalony**.

Mapowanie typów z bazy (to jest właściwa odpowiedź na „dostosuj do typów, jakie tam są”):

=====================  ==========================================================
pole synapse           źródło w organizerze
=====================  ==========================================================
``id``                 slug z ``(semestr, skrót)`` albo ``(skrót, sha256[:8])``
``title``              nazwa przedmiotu albo nazwa pliku źródłowego
``category``           ``SEM{n}`` (widok przedmiotów) / kategoria z ``syntax.yaml``
                       (widok materiałów) — oba mają własny kolor w ``catColors``
``level``              1 = leży już w paczce (ground truth), 2 = plan pewny
                       (>= ``auto_apply``), 3 = wymaga człowieka (review/unresolved)
``status``             ``completed`` / ``in-progress`` / ``not-started`` — etap
                       potoku, czyli to samo słownictwo, którego używa prototyp
``tags``               ``content_kind``, akcja planu, metoda decyzji, grupa/strumień,
                       formy zajęć, rok materiału — wszystko jako płaskie etykiety
``links``              ``relations`` (near_duplicate / older_version / related) oraz
                       współdzielenie treści między przedmiotami
``path``               ``{vault}/{category-slug}/{id}.md``
``body``               markdown: decyzja, prowenancja, relacje jako ``[[wikilinki]]``
``modified``           najnowsza data modyfikacji kopii źródłowej (``files.modified_date``)
``activity``           daty modyfikacji WSZYSTKICH kopii — widać, w których paczkach
                       materiał się pojawiał
=====================  ==========================================================
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

#: Dozwolone statusy notatki — dokładnie te, których używa prototyp.
STATUSES = ("completed", "in-progress", "not-started")

#: Dozwolone poziomy. Prototyp buduje filtr z literału [1,2,3]; więcej nie przejdzie.
LEVELS = (1, 2, 3)

#: Znaczenie poziomów w naszym mapowaniu (trafia do dokumentacji i do README vaulta).
LEVEL_MEANING = {
    1: "leży już w paczce (ground truth)",
    2: "plan pewny — decyzja powyżej progu auto",
    3: "wymaga człowieka — review albo brak rozstrzygnięcia",
}

#: Kolory kategorii. Semestry dostają ciąg od chłodnych do ciepłych, żeby na grafie
#: było widać „rok studiów”; kategorie materiałów — kolory zbliżone do ich roli.
CATEGORY_COLORS: dict[str, str] = {
    "SEM1": "#58a6ff", "SEM2": "#39c5cf", "SEM3": "#3fb950", "SEM4": "#d29922",
    "SEM5": "#f0883e", "SEM6": "#f778ba", "SEM7": "#bc8cff",
    "wyklad": "#58a6ff", "egzamin": "#f778ba", "kolokwia": "#f0883e",
    "laboratoria": "#3fb950", "cwiczenia": "#39c5cf", "projekt": "#bc8cff",
    "seminarium": "#d29922", "opracowania": "#8b949e", "ksiazki": "#a5d6ff",
    "inne": "#6e7681",
}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, limit: int = 48) -> str:
    """Slug ASCII do id i ścieżek: bez diakrytyków, tylko [a-z0-9-].

    Ta sama normalizacja, co przy dopasowaniu przedmiotów (``ł`` → ``l``), żeby
    ``Architektura Komputerów`` i ``architektura-komputerow`` znaczyły to samo.
    """
    folded = unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    slug = _SLUG_STRIP.sub("-", folded).strip("-")
    return slug[:limit].strip("-") or "bez-nazwy"


@dataclass
class Note:
    """Jedna notatka w kształcie, którego oczekuje prototyp ``synapse``."""

    id: str
    title: str
    category: str
    level: int
    status: str
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    body: str = ""
    modified: str = ""
    activity: list[str] = field(default_factory=list)

    def path(self, vault: str) -> str:
        return f"{vault}/{slugify(self.category)}/{self.id}.md"

    def as_seed(self, vault: str) -> dict[str, Any]:
        """Postać przyjmowana przez ``seedNotes()`` — jeden do jednego."""
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "level": self.level,
            "status": self.status,
            "tags": list(self.tags),
            "links": list(self.links),
            "path": self.path(vault),
            "body": self.body,
            "modified": self.modified,
            "activity": list(self.activity),
        }

    def validate(self) -> None:
        """Pilnuje ograniczeń prototypu — lepiej tu niż w cudzym UI."""
        if self.level not in LEVELS:
            raise ValueError(f"{self.id}: level={self.level} poza {LEVELS} (prototyp ma filtr [1,2,3])")
        if self.status not in STATUSES:
            raise ValueError(f"{self.id}: status={self.status!r} poza {STATUSES}")
        if not self.id or self.id != slugify(self.id, limit=len(self.id)):
            raise ValueError(f"nieprawidłowe id notatki: {self.id!r}")


def _front_matter(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_front_matter(item) for item in value) + "]"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace('"', '\\"')
    return f'"{text}"'


def render_markdown(note: Note, vault: str) -> str:
    """Notatka jako plik `.md`: YAML front matter + treść z ``[[wikilinkami]]``."""
    header = "\n".join(
        f"{key}: {_front_matter(value)}"
        for key, value in (
            ("id", note.id), ("title", note.title), ("category", note.category),
            ("level", note.level), ("status", note.status), ("tags", note.tags),
            ("links", note.links), ("path", note.path(vault)),
            ("modified", note.modified), ("activity", note.activity),
        )
    )
    return f"---\n{header}\n---\n\n# {note.title}\n\n{note.body.strip()}\n"


def status_for_subject(*, ground_truth: int, planned: int, needs_review: int) -> str:
    """Etap przedmiotu w słowniku prototypu.

    ``completed`` dostaje przedmiot, który ma materiały w paczce i nie ma planu
    czekającego na człowieka — czyli nie „wszystko zrobione na zawsze”, tylko
    „nic tu teraz nie stoi”. To jedyne uczciwe tłumaczenie, bo organizer nie wie,
    czy paczka jest kompletna merytorycznie.
    """
    if planned and needs_review:
        return "in-progress"
    if planned:
        return "completed" if ground_truth else "in-progress"
    return "completed" if ground_truth else "not-started"


def level_for_subject(*, ground_truth: int, planned: int, needs_review: int) -> int:
    if needs_review or (not ground_truth and not planned):
        return 3
    if planned:
        return 2
    return 1


def level_for_content(
    *, in_package: bool, needs_review: bool, confidence: float, auto_apply: float
) -> int:
    if in_package:
        return 1
    if needs_review or confidence < auto_apply:
        return 3
    return 2


def status_for_content(action: str, *, in_package: bool) -> str:
    """Materiał: w paczce = ``completed``, zaplanowany = ``in-progress``, reszta = ``not-started``."""
    if in_package:
        return "completed"
    if action in ("copy", "media"):
        return "in-progress"
    return "not-started"


def subject_note_id(semester: int, skrot: str, grupa: str = "", *, ambiguous: bool = False) -> str:
    parts = [f"sem{semester}", slugify(skrot)]
    if ambiguous and grupa:
        parts.append(slugify(grupa, limit=24))
    return "-".join(parts)


def content_note_id(skrot: str, sha256: str, filename: str = "") -> str:
    """Id treści: czytelny kawałek nazwy + skrót sha, żeby był stabilny i unikalny."""
    name = slugify(filename, limit=32) if filename else ""
    parts = [slugify(skrot, limit=12)] + ([name] if name and name != "bez-nazwy" else [])
    parts.append(sha256[:8])
    return "-".join(parts)


def wikilink(note_id: str, label: str | None = None) -> str:
    return f"[[{note_id}]]" if label is None else f"[[{note_id}|{label}]]"


def vault_readme(notes: Sequence[Note], vault: str, generated_at: str) -> str:
    """README vaulta — mapowanie pól, żeby nikt nie musiał zgadywać, co znaczy `level`."""
    by_category: dict[str, int] = {}
    for note in notes:
        by_category[note.category] = by_category.get(note.category, 0) + 1
    rows = "\n".join(
        f"| {category} | {count} | `{CATEGORY_COLORS.get(category, '#888')}` |"
        for category, count in sorted(by_category.items())
    )
    levels = "\n".join(f"- **L{level}** — {meaning}" for level, meaning in LEVEL_MEANING.items())
    return f"""# {vault}

Vault **generowany** przez `scripts/synapse_export.py` z indeksu organizera.
Nie edytuj notatek ręcznie — kolejny eksport je nadpisze.

- Wygenerowano: {generated_at}
- Notatek: {len(notes)}

## Co znaczy `level`

Prototyp `synapse` ma filtr poziomów zaszyty jako `[1, 2, 3]`, więc semestr (1-7)
tam nie wchodzi — semestr jest w `category` i w tagach. `level` niesie to, co ma
dokładnie trzy stopnie i jest w tym projekcie decyzyjne:

{levels}

## Statusy

`completed` / `in-progress` / `not-started` — słownictwo prototypu, u nas znaczy
etap potoku: w paczce / zaplanowane / nietknięte.

## Kategorie

| kategoria | notatek | kolor |
|---|---:|---|
{rows}
"""


def catalog_colors(notes: Iterable[Note]) -> dict[str, str]:
    """Mapa kolorów dla kategorii, które faktycznie wystąpiły (pole ``catColors``)."""
    return {
        note.category: CATEGORY_COLORS.get(note.category, "#8b949e")
        for note in sorted(notes, key=lambda n: n.category)
    }


def dedupe_ids(notes: Sequence[Note]) -> list[Note]:
    """Id musi być unikalne — na nim stoją wikilinki. Kolizję rozstrzyga przyrostek."""
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
