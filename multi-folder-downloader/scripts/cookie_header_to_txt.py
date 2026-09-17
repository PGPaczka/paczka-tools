#!/usr/bin/env python3
"""
Zamienia surowy nagłówek `cookie:` (skopiowany z DevTools → Network →
dowolny request do drive.google.com → Request Headers → cookie) na plik
cookies.txt w formacie Netscape, którego oczekuje gdown (--cookies).

Nie wymaga żadnego rozszerzenia do przeglądarki.

Domyślnie zapisuje cookies.txt w katalogu danych (czyli w
multi-folder-downloader/cookies/), skąd downloader bierze je automatycznie.

Użycie (dowolny wariant):

  # 1) wklej nagłówek interaktywnie:
  python scripts/cookie_header_to_txt.py
  # ...wklej linię "SID=...; HSID=...; ..." i naciśnij Enter

  # 2) z pliku, do którego wkleiłeś nagłówek:
  python scripts/cookie_header_to_txt.py -i cookies/header.txt

  # 3) przez potok:
  echo 'SID=...; HSID=...; ...' | python scripts/cookie_header_to_txt.py

  # 4) inna ścieżka wyjściowa, jeśli potrzebna:
  python scripts/cookie_header_to_txt.py -o ~/cookies.txt

Nagłówek może zaczynać się od "cookie:" — zostanie to obcięte.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Daleka data ważności — Google i tak unieważni część cookies wcześniej.
FAR_FUTURE = int(time.time()) + 10 * 365 * 24 * 3600

# Cookies logowania Google żyją na .google.com; te trafiają też na
# subdomeny (drive.google.com, docs.google.com), więc host-only ustawiamy
# na .google.com z flagą domenową TRUE.
DOMAIN = ".google.com"

# Domyślnie zapisuje w cookies/cookies.txt, niezależnie od tego,
# z jakiego katalogu skrypt jest uruchamiany.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = str(PROJECT_DIR / "cookies" / "cookies.txt")


def parse_cookie_header(raw: str) -> list[tuple[str, str]]:
    raw = raw.strip()
    # Usuń ewentualny prefiks "cookie:" / "Cookie:".
    if raw[:7].lower() == "cookie:":
        raw = raw[7:].strip()

    pairs: list[tuple[str, str]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            pairs.append((name, value))
    return pairs


def to_netscape(pairs: list[tuple[str, str]]) -> str:
    lines = [
        "# Netscape HTTP Cookie File",
        "# Wygenerowane przez cookie_header_to_txt.py",
        "",
    ]
    for name, value in pairs:
        # domain  include_subdomains  path  secure  expiry  name  value
        lines.append(
            "\t".join(
                [
                    DOMAIN,
                    "TRUE",
                    "/",
                    "TRUE",
                    str(FAR_FUTURE),
                    name,
                    value,
                ]
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-i",
        "--input",
        help="Plik z wklejonym nagłówkiem cookie (domyślnie: stdin/prompt).",
    )
    ap.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help="Ścieżka wyjściowa cookies.txt (domyślnie: cookies/cookies.txt w katalogu projektu).",
    )
    args = ap.parse_args()

    if args.input:
        raw = Path(args.input).expanduser().read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        print(
            "Wklej nagłówek 'cookie:' z DevTools i naciśnij Enter:\n",
            file=sys.stderr,
        )
        raw = sys.stdin.readline()

    pairs = parse_cookie_header(raw)
    if not pairs:
        print(
            "Nie znaleziono żadnych cookies w wejściu. "
            "Upewnij się, że wkleiłeś całą wartość nagłówka cookie.",
            file=sys.stderr,
        )
        return 1

    names = {n for n, _ in pairs}
    # Cookies krytyczne dla uwierzytelnienia Google.
    important = {"SID", "SSID", "HSID", "SAPISID", "APISID", "__Secure-1PSID"}
    missing = important - names
    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(to_netscape(pairs), encoding="utf-8")
    try:
        out_path.chmod(0o600)
    except OSError:
        pass

    print(f"Zapisano {len(pairs)} cookies → {out_path}")
    if missing:
        print(
            "UWAGA: brakuje typowych cookies logowania: "
            + ", ".join(sorted(missing))
            + ".\nSkopiuj nagłówek z requestu do drive.google.com, gdy "
            "jesteś zalogowany (nie z trybu incognito).",
            file=sys.stderr,
        )
    print(
        "Użyj tak:\n"
        f"  python download_drive_dashboard_sqlite.py --workers 2 "
        f"--cookies {out_path} --retry-failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
