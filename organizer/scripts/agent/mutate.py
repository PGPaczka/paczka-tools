"""Czy testy w ogóle coś łapią? Psuje KOPIĘ repo i sprawdza, czy robi się czerwono.

Pokrycie mierzy wykonane linie, nie to, czy asercje cokolwiek znaczą. Audyt
2026-09-18 pokazał to dobitnie: 615 zielonych testów przy niepilnowanej
serializacji hashy — zamiana separatorów `\\0`/`\\n` na `|`/`;` przechodziła całe
repo. Jedyny wiarygodny sprawdzian to zepsuć zachowanie i zobaczyć, co padnie.

    just mutate-check                     # cały katalog specyfikacji
    just mutate tests/mutations/hashes-separator.yaml

Mutacja jest opisana w pliku YAML, a nie w wierszu poleceń: fragmenty kodu mają
cudzysłowy, nawiasy i znaki specjalne, których `just` nie przenosi bez zmian.
Dzięki temu sprawdzenia są też **wersjonowane** — raz udowodniony kontrakt daje
się powtórzyć bez pamiętania, co dokładnie się psuło.

Wynik `WYKRYTE` = kontrakt jest pilnowany. `PRZEPUSZCZONE` = dziura w pokryciu:
mutacja zmieniła zachowanie i nikt tego nie zauważył.

Prawdziwe repo nie jest dotykane — praca dzieje się w katalogu tymczasowym.
Domyślnie podmieniane są WSZYSTKIE wystąpienia wzorca: podmiana tylko pierwszego
potrafi trafić w inne miejsce, niż się zakłada, i dać mylące „PRZEPUSZCZONE"
(sprawdzone na własnej skórze — `_is_encodable` ma w `scan.py` dwa wywołania).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import typer
import yaml

app = typer.Typer(add_completion=False, help=__doc__)

#: Co kopiujemy do piaskownicy. `.venv` świadomie pomijamy — interpreter bierzemy
#: z prawdziwego repo, kopiowanie środowiska trwałoby dłużej niż sam test.
_COPIED = ("scripts", "studio", "tests", "config", "prompts", "setup", "pytest.ini",
           "justfile", ".agents", ".claude")

ORGANIZER = Path(__file__).resolve().parents[2]


def _prepare(workdir: Path) -> None:
    """Kopiuje repo do piaskownicy (bez `.venv` i bez `.git`)."""
    workdir.mkdir(parents=True, exist_ok=True)
    for item in _COPIED:
        source = ORGANIZER / item
        if not source.exists():
            continue
        target = workdir / item
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    codex = ORGANIZER.parent / ".codex"
    if codex.is_dir():
        shutil.copytree(codex, workdir.parent / ".codex", dirs_exist_ok=True)


@dataclass(frozen=True)
class Spec:
    """Jedna mutacja: co zepsuć, czym i które testy mają to wykryć."""

    name: str
    file: Path
    find: str
    replace: str
    tests: list[str]
    first_only: bool = False
    #: Czego oczekujemy. ``caught`` = testy MUSZĄ paść (domyślne).
    expect: str = "caught"


def load_spec(path: Path) -> Spec:
    """Wczytuje opis mutacji z YAML-a."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Spec(
        name=str(data.get("name") or Path(path).stem),
        file=Path(str(data["file"])),
        find=str(data["find"]),
        replace=str(data.get("replace", "")),
        tests=[str(t) for t in data["tests"]],
        first_only=bool(data.get("first_only", False)),
        expect=str(data.get("expect", "caught")),
    )


def run_spec(spec: Spec, *, keep: bool = False) -> bool:
    """Wykonuje jedną mutację; zwraca True, gdy wynik jest ZGODNY z oczekiwaniem."""
    sandbox = Path(tempfile.mkdtemp(prefix="mutate-")) / "organizer"
    _prepare(sandbox)

    target = sandbox / spec.file
    if not target.is_file():
        typer.echo(f"  BŁĄD: brak pliku w kopii: {spec.file}", err=True)
        return False
    text = target.read_text(encoding="utf-8")
    if spec.find not in text:
        typer.echo(f"  BŁĄD: nie znaleziono fragmentu do mutacji w {spec.file}", err=True)
        return False

    occurrences = text.count(spec.find)
    target.write_text(
        text.replace(spec.find, spec.replace, 1 if spec.first_only else -1), encoding="utf-8"
    )
    completed = subprocess.run(
        [str(ORGANIZER / ".venv" / "bin" / "python"), "-m", "pytest", *spec.tests, "-q",
         "--no-header", "-p", "no:cacheprovider"],
        cwd=sandbox, capture_output=True, text=True,
    )
    lines = [line for line in completed.stdout.strip().splitlines() if line.strip()]
    summary = lines[-1][:90] if lines else "(brak wyjścia)"
    caught = completed.returncode != 0
    zgodne = caught if spec.expect == "caught" else not caught

    status = "WYKRYTE" if caught else "PRZEPUSZCZONE"
    marker = "ok" if zgodne else "!!"
    typer.echo(f"  [{marker}] {spec.name}: {status} (wystąpień: {1 if spec.first_only else occurrences})")
    if not zgodne:
        typer.echo(f"      {summary}")
        typer.echo("      Testy nie pilnują tego zachowania — dopisz asercję albo popraw istniejącą.")
    if keep:
        typer.echo(f"      piaskownica: {sandbox}")
    else:
        shutil.rmtree(sandbox.parent, ignore_errors=True)
    return zgodne


@app.command("one")
def run_one(
    spec_path: Path = typer.Argument(..., help="Plik YAML z opisem mutacji."),
    keep: bool = typer.Option(False, "--keep", help="Zostaw piaskownicę do obejrzenia."),
) -> None:
    """Uruchamia jedną mutację z pliku specyfikacji."""
    typer.echo(f"== {spec_path} ==")
    raise typer.Exit(code=0 if run_spec(load_spec(spec_path), keep=keep) else 1)


@app.command("check")
def run_all(
    directory: Path = typer.Argument(
        Path("tests/mutations"), help="Katalog z plikami *.yaml."
    ),
) -> None:
    """Uruchamia wszystkie zapisane mutacje; kod 1, gdy którykolwiek kontrakt przestał być pilnowany."""
    specs = sorted(Path(directory).glob("*.yaml"))
    if not specs:
        typer.echo(f"brak specyfikacji w {directory}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"== sprawdzam {len(specs)} zapisanych mutacji ==")
    wyniki = [run_spec(load_spec(path)) for path in specs]
    zgodne = sum(1 for wynik in wyniki if wynik)
    typer.echo(f"zgodne z oczekiwaniem: {zgodne}/{len(wyniki)}")
    raise typer.Exit(code=0 if zgodne == len(wyniki) else 1)


if __name__ == "__main__":
    app()
