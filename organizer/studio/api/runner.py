"""S3.5: uruchamianie etapów potoku jako PODPROCES istniejącego CLI, ze strumieniem logów.

Studio nie przepisuje etapów (``studio/AGENTS.md``, reguła 2). `validate_plan`,
`build_plan`, `apply` i `verify` to te same skrypty, które człowiek uruchamia
z konsoli — studio je woła, pokazuje ich wyjście na żywo i przekazuje dalej ich
**kod wyjścia**. Dzięki temu bramka jest jedna: kod 2 znaczy „nie wolno”
niezależnie od tego, kto etap uruchomił.

Argumenty buduje wyłącznie :func:`build_argv` z zamkniętej listy etapów. Nazwa
etapu przychodzi z sieci, więc nigdy nie trafia do powłoki ani do ścieżki —
nieznany etap to błąd, a nie próba uruchomienia czegokolwiek.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Iterator, Sequence

from orglib import config

#: Katalog skryptów potoku. Liczony ze ścieżki TEGO pliku, a nie z
#: ``config.ORGANIZER_ROOT``: skrypty są zasobem repo i leżą obok kodu, a tamtą
#: stałą testy przestawiają, żeby przekierować RAPORTY. Zbudowana na niej ścieżka
#: znikała dokładnie wtedy, gdy test próbował uruchomić prawdziwy etap.
SCRIPTS_DIR: Path = Path(__file__).resolve().parents[2] / "scripts"

#: Etapy: skrypt i flagi, które ten skrypt NAPRAWDĘ przyjmuje. Nie wszystkie są
#: jednakowe — `review_report.py` nie zna ani `--db`, ani `--plan` (czyta manifest),
#: a `build_plan.py` planu dopiero go tworzy. Dopisanie flagi „na wszelki wypadek"
#: kończy się etapem, który startuje i od razu odbija się od parsera, więc kontrakt
#: jest tu jawny i pilnuje go test wobec prawdziwych parserów.
STAGE_SCRIPTS: dict[str, dict[str, Any]] = {
    # Etapy przygotowania przedmiotu. Żaden nie rusza materiałów: piszą do bazy
    # i do `reports/{SKROT}/`, więc są odwracalne przez ponowne uruchomienie.
    "prepare": {"script": "prepare_subject.py", "db": True, "plan": False},
    "classify": {"script": "classify.py", "db": True, "plan": False},
    # `ai_resolve.py` jako JEDYNY z tej grupy nie zna `--db` (czyta manifest,
    # pisze plan.ai.jsonl obok niego). Dopisanie flagi „dla symetrii" dałoby etap,
    # który startuje i od razu odbija się od parsera.
    "ai-resolve": {"script": "ai_resolve.py", "db": False, "plan": False},
    "relate": {"script": "near_dupe.py", "db": True, "plan": False},
    "plan": {"script": "build_plan.py", "db": True, "plan": False},
    "validate": {"script": "validate_plan.py", "db": True, "plan": True},
    "review": {"script": "review_report.py", "db": False, "plan": False},
    "apply-dry": {"script": "apply.py", "db": True, "plan": True},
    "apply": {"script": "apply.py", "db": True, "plan": True},
    "verify": {"script": "verify.py", "db": True, "plan": True},
}

#: Etapy całego INDEKSU, nie przedmiotu: nie znają `--semester/--skrot`, więc nie
#: przechodzą przez `build_argv` ani przez trasę przedmiotu. Wszystkie czytają
#: źródła tylko do odczytu i piszą do `20_WORK`; żaden nie dotyka repo paczki.
GLOBAL_STAGE_SCRIPTS: dict[str, dict[str, Any]] = {
    "scan": {"script": "scan.py"},
    "hash": {"script": "hash_files.py"},
    "fold-hash": {"script": "fold_hash.py"},
    "extract": {"script": "extract_text.py"},
    "scan-target": {"script": "scan_target.py"},
    "status": {"script": "status_report.py"},
}

#: Etapy, które ruszają materiały. Wymagają potwierdzenia KONKRETNEGO planu.
WRITING_STAGES: frozenset[str] = frozenset({"apply"})

#: Limit czasu jednego etapu; `apply` na dużym przedmiocie to tysiące kopii.
TIMEOUT_S = 3600

#: Limity dla etapów, którym godzina nie wystarcza. Zmierzone, nie zgadnięte:
#: `extract --ocr-images` na tym indeksie zajął **2977 s**, czyli 83% domyślnego
#: limitu — pierwszy większy zestaw źródeł przekroczyłby go i etap zostałby ubity
#: w połowie. `scan` i `hash` chodzą po wszystkich plikach źródeł, więc rosną
#: razem z nimi.
STAGE_TIMEOUTS: dict[str, int] = {
    "scan": 6 * 3600,
    "hash": 6 * 3600,
    "fold-hash": 6 * 3600,
    "extract": 12 * 3600,
    "scan-target": 6 * 3600,
}


def timeout_for(stage: str) -> int:
    """Limit czasu etapu; brak wpisu = domyślna godzina."""
    return STAGE_TIMEOUTS.get(stage, TIMEOUT_S)


#: Projekt generatora .NET i katalog danych grafu — obie ścieżki liczone od modułu,
#: nie od katalogu roboczego procesu (ta sama pułapka co przy `SCRIPTS_DIR`).
GENERATOR_PROJECT = (
    SCRIPTS_DIR.parent / "studio" / "graf" / "Synapse.Generator" / "Synapse.Generator"
)


def graph_commands(*, db_path: Path, work_dir: Path | None = None) -> list[list[str]]:
    """Dwie komendy, które odświeżają DANE grafu: eksport vaulta i generator.

    Budowania frontu tu nie ma i nie powinno być: viewer czyta `graph.json` z `work`
    przy starcie, więc po zmianie decyzji wystarczy przebudować dane. Przebudowa
    paczki JS trwa dłużej niż cała reszta i niczego by nie zmieniła.

    Ścieżki idą bezwzględne, bo generator startuje z katalogiem roboczym swojego
    projektu — względne `../../20_WORK` z `justfile` działa tylko stamtąd.
    """
    praca = (work_dir or db_path.parent).resolve()
    vault = praca / "synapse" / "vault"
    graph = praca / "synapse" / "graph.json"
    return [
        [sys.executable, str(SCRIPTS_DIR / "synapse_export.py"), "--db", str(db_path),
         "--out-dir", str(vault)],
        ["dotnet", "run", "--project", str(GENERATOR_PROJECT), "-c", "Release", "--nologo",
         "--", "--vault", str(vault), "--out", str(graph), "--no-git"],
    ]


class UnknownStage(ValueError):
    """Nazwa etapu spoza zamkniętej listy."""


class StageBusy(RuntimeError):
    """Inny etap już działa. Niesie jego nazwę, żeby widok mógł ją pokazać."""


#: Jeden etap na raz — na CAŁE studio, nie na przedmiot.
#:
#: Wszystkie etapy piszą do tej samej bazy `20_WORK/organizer.sqlite`, a część
#: z nich (`scan`, `hash`, `extract`) przemiela ją w całości. Dwa naraz to nie
#: jest „wolniej": to `classify` czytający stan, który `extract` właśnie zmienia.
#: Dopóki etapy trzeba było wpisywać z konsoli, pilnowała tego jedna para rąk;
#: z przyciskami w przeglądarce równoległe uruchomienie to jedno kliknięcie.
_LOCK = threading.Lock()
_RUNNING: str | None = None


def acquire(label: str) -> None:
    """Zajmuje blokadę albo odmawia. Nie czeka — kolejka etapów byłaby gorsza
    niż jasne „teraz trwa X", bo użytkownik nie wie, na co czeka."""
    global _RUNNING
    if not _LOCK.acquire(blocking=False):
        raise StageBusy(_RUNNING or "inny etap")
    _RUNNING = label


def release() -> None:
    """Zwalnia blokadę. Wołane z ``finally`` strumienia, więc także wtedy, gdy
    przeglądarka zamknie połączenie w trakcie etapu."""
    global _RUNNING
    if _LOCK.locked():
        _RUNNING = None
        _LOCK.release()


def running() -> str | None:
    """Nazwa trwającego etapu albo ``None``."""
    return _RUNNING


def released_after(frames: Iterator[str]) -> Iterator[str]:
    """Owija strumień tak, żeby blokada padła razem z jego końcem.

    Blokadę zajmuje TRASA, przed zbudowaniem odpowiedzi — inaczej odmowa nie
    mogłaby być kodem HTTP, bo strumień już by się zaczął.
    """
    try:
        yield from frames
    finally:
        release()


def build_argv(
    stage: str,
    *,
    subject: config.Subject,
    db_path: Path,
    plan_path: Path | None = None,
    plan_hash: str | None = None,
    grupa: str | None = None,
) -> list[str]:
    """Buduje argv etapu. Jedyne miejsce, w którym powstaje komenda studia."""
    if stage not in STAGE_SCRIPTS:
        raise UnknownStage(f"nieznany etap {stage!r}; dozwolone: {sorted(STAGE_SCRIPTS)}")
    spec = STAGE_SCRIPTS[stage]
    argv = [
        sys.executable, str(SCRIPTS_DIR / spec["script"]),
        "--semester", str(subject.semester),
        "--skrot", subject.skrot,
    ]
    if spec["db"]:
        argv += ["--db", str(db_path)]
    if grupa:
        argv += ["--grupa", grupa]
    if spec["plan"] and plan_path is not None:
        argv += ["--plan", str(plan_path)]
    if stage == "apply":
        # Zgoda człowieka dotyczy konkretnego planu — odcisk jedzie do skryptu,
        # który sprawdza go jeszcze raz u siebie i odmawia przy niezgodności.
        argv += ["--yes"]
        if plan_hash:
            argv += ["--expect-hash", plan_hash]
    return argv


def build_global_argv(stage: str, *, db_path: Path, ocr_images: bool = False) -> list[str]:
    """Argv etapu indeksu. Osobno od :func:`build_argv`, bo te skrypty nie znają
    ``--semester/--skrot`` — wciśnięcie ich we wspólną funkcję skończyłoby się
    gałęzią „a dla tych czterech pomiń pierwsze dwa argumenty".

    ``ocr_images`` jest jedynym przełącznikiem wystawionym na zewnątrz i tylko dla
    `extract`: to on odróżnia przebieg kilkuminutowy od kilkugodzinnego, więc musi
    być wyborem człowieka, a nie domyślną wartością ukrytą w kodzie.
    """
    if stage not in GLOBAL_STAGE_SCRIPTS:
        raise UnknownStage(
            f"nieznany etap indeksu {stage!r}; dozwolone: {sorted(GLOBAL_STAGE_SCRIPTS)}"
        )
    spec = GLOBAL_STAGE_SCRIPTS[stage]
    argv = [sys.executable, str(SCRIPTS_DIR / spec["script"]), "--db", str(db_path)]
    if stage == "extract" and ocr_images:
        argv += ["--ocr-images"]
    return argv


def _frame(event: str, payload: dict[str, Any]) -> str:
    """Jedna ramka SSE."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_all(
    commands: Sequence[Sequence[str]],
    *,
    cwd: Path | None = None,
    timeout_s: int | None = None,
) -> Iterator[str]:
    """Łańcuch komend jako JEDEN strumień: wspólny log, jedna ramka ``done``.

    Łańcuch pęka na pierwszym niezerowym kodzie. To nie jest ostrożność na zapas:
    generator grafu uruchomiony po nieudanym eksporcie zbudowałby graf ze STARYCH
    notatek i zameldował sukces — czyli widok pokazałby nieaktualne dane, wyglądając
    na odświeżony.
    """
    ostatni = 0
    for argv in commands:
        for frame in stream(argv, cwd=cwd, final=False, timeout_s=timeout_s):
            if frame.startswith("event: exit"):
                ostatni = json.loads(frame.split("data: ", 1)[1])["code"]
                break
            yield frame
        if ostatni != 0:
            break
    yield _frame("done", {"code": ostatni})


def stream(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    final: bool = True,
    timeout_s: int | None = None,
) -> Iterator[str]:
    """Uruchamia etap i oddaje jego wyjście linia po linii jako zdarzenia SSE.

    Kończy ramką ``done`` z kodem wyjścia — to on, a nie treść logu, mówi
    widokowi, czy etap przeszedł. Zamknięcie strumienia przez przeglądarkę ubija
    podproces: nikt nie chce `apply` działającego po zamknięciu karty.
    """
    limit = TIMEOUT_S if timeout_s is None else timeout_s
    yield _frame("start", {"argv": [str(part) for part in argv]})
    process = subprocess.Popen(
        [str(part) for part in argv],
        cwd=str(cwd or SCRIPTS_DIR.parent),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    try:
        assert process.stdout is not None
        for line in process.stdout:
            yield _frame("line", {"text": line.rstrip("\n")})
        code = process.wait(timeout=limit)
        # `final=False` znaczy „to ogniwo łańcucha": kod wyjścia idzie ramką `exit`,
        # a o `done` decyduje `stream_all` po ostatniej komendzie.
        yield _frame("done" if final else "exit", {"code": code})
    except subprocess.TimeoutExpired:
        process.kill()
        yield _frame(
            "done" if final else "exit",
            {"code": 124, "detail": f"etap przekroczył {limit}s"},
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - etap nie zareagował
                process.kill()
