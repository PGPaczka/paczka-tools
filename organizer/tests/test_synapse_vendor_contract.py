"""C3: nasz vault przepuszczony przez PRAWDZIWY generator synapse.

To jest jedyny test, który sprawdza to, co naprawdę się liczy: czy `Synapse.Generator`
rozumie nasz front matter i czy jego `graph.json` spełnia ICH schemat. Reszta testów
opisuje nasz kontrakt; ten opisuje cudzy — i zrobi się czerwony, gdy któraś strona
odejdzie od ustaleń (np. zmieni nazwę klucza albo enum statusów).

Pomijany, gdy nie ma klona (`vendor/synapse`) albo `dotnet` — wtedy po prostu nie da się
go wykonać. Obecny klon + brak zgodności = czerwono, nigdy „pominięte”.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest

from orglib import config
from orglib.synapse_vault import (
    EDGE_BELONGS_TO,
    NODE_FILE,
    NODE_SEMESTER,
    NODE_SUBJECT,
    STATUS_ACTIVE,
    STATUS_DONE,
    Note,
    Relation,
    render_note,
)

VENDOR = config.ORGANIZER_ROOT / "vendor" / "synapse"
PROJECT = VENDOR / "Synapse.Generator" / "Synapse.Generator"
SCHEMA = VENDOR / "schema" / "graph.schema.v2.json"

pytestmark = [
    pytest.mark.vendor,
    pytest.mark.skipif(not PROJECT.is_dir(), reason="brak klona vendor/synapse"),
    pytest.mark.skipif(shutil.which("dotnet") is None, reason="brak dotnet"),
]


def build_vault(root: Path) -> None:
    """Miniaturowy vault o tej samej strukturze, co produkcyjny: semestr → przedmiot → plik."""
    notes = [
        Note(id="sem3", title="Semestr 3", type=NODE_SEMESTER, category="semestr",
             status=STATUS_ACTIVE, body="Semestr testowy."),
        Note(id="sem3-ako", title="AKO — Architektura", type=NODE_SUBJECT, category="SEM3",
             level=2, status=STATUS_ACTIVE, tags=["sem3"], aliases=["AKO"],
             relations=[Relation("sem3", EDGE_BELONGS_TO)], body="Przedmiot testowy.",
             folder="sem3"),
        Note(id="ako-lab-aaaaaaaa", title="lab.pdf", type=NODE_FILE, category="laboratoria",
             level=2, status=STATUS_ACTIVE, tags=["rodzaj-pdf"], modified="2026-09-19",
             relations=[
                 Relation("sem3-ako", EDGE_BELONGS_TO),
                 Relation("ako-kol-bbbbbbbb", "near_duplicate", 0.78),
                 Relation("nieprzypisane-cccccccc", "older_version", 0.6),
             ],
             body="Plik testowy.", folder="sem3/ako"),
        Note(id="ako-kol-bbbbbbbb", title="kol.png", type=NODE_FILE, category="kolokwia",
             level=1, status=STATUS_DONE, tags=["w-paczce"], modified="2026-09-18",
             relations=[Relation("sem3-ako", EDGE_BELONGS_TO)],
             body="Drugi plik testowy.", folder="sem3/ako"),
    ]
    for note in notes:
        note.validate()
        target = root / note.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_note(note), encoding="utf-8")


@pytest.fixture(scope="module")
def graph(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("vault")
    build_vault(root)
    out = root.parent / "graph.json"

    result = subprocess.run(
        ["dotnet", "run", "--project", str(PROJECT), "-c", "Release", "--nologo",
         "--", "--vault", str(root), "--out", str(out), "--no-git"],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"generator padł: {result.stderr or result.stdout}"
    return json.loads(out.read_text(encoding="utf-8-sig"))


def test_graph_validates_against_their_schema(graph) -> None:
    jsonschema.validate(graph, json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert graph["schemaVersion"] == 2


def test_node_types_survive_the_round_trip(graph) -> None:
    types = {n["id"]: n.get("type") for n in graph["nodes"] if n["kind"] == "real"}

    assert types["sem3"] == NODE_SEMESTER
    assert types["sem3-ako"] == NODE_SUBJECT
    assert types["ako-lab-aaaaaaaa"] == NODE_FILE


def test_relation_kinds_and_confidence_survive_the_round_trip(graph) -> None:
    edges = {(e["source"], e["target"]): e for e in graph["edges"]}

    assert edges[("sem3-ako", "sem3")]["kind"] == EDGE_BELONGS_TO
    near = edges[("ako-lab-aaaaaaaa", "ako-kol-bbbbbbbb")]
    assert near["kind"] == "near_duplicate"
    assert near["confidence"] == pytest.approx(0.78)


def test_relation_outside_the_vault_becomes_a_ghost(graph) -> None:
    ghosts = [n for n in graph["nodes"] if n["kind"] == "ghost"]

    assert [g["id"] for g in ghosts] == ["nieprzypisane-cccccccc"]
    assert ghosts[0]["referencedBy"] == ["ako-lab-aaaaaaaa"]


def test_statuses_are_accepted_not_nulled(graph) -> None:
    """Status spoza ich enumu generator po cichu zamienia na null — nasz musi przechodzić."""
    statuses = {n["id"]: n.get("status") for n in graph["nodes"] if n["kind"] == "real"}

    assert statuses["ako-lab-aaaaaaaa"] == STATUS_ACTIVE
    assert statuses["ako-kol-bbbbbbbb"] == STATUS_DONE


def test_vault_has_no_warnings(graph) -> None:
    """`duplicate-id` albo `ambiguous-link` znaczy, że nasze id przestały być unikalne."""
    assert graph["warnings"] == []


def test_history_without_git_is_at_most_the_declared_modified_date(graph) -> None:
    """Vault nie jest repozytorium, więc historii commitów nie ma.

    Generator ma jednak świadomy fallback: notatka z `modified` dostaje
    jednoelementową historię z tą datą (żeby heatmapa w dashboardzie nie była pusta).
    Kontrakt brzmi więc: historia to albo nic, albo dokładnie zadeklarowana data —
    nigdy daty commitów, bo tych po prostu nie ma skąd wziąć.
    """
    for node in graph["nodes"]:
        if node["kind"] != "real":
            continue
        history = node.get("history")
        if history is None:
            continue
        assert history == [node["modified"]], node["id"]
