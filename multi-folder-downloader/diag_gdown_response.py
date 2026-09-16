#!/usr/bin/env python3
"""
Diagnostyka pobierania z Google Drive: pokazuje, CO naprawdę zwraca Google
dla jednego pliku, z Twoimi cookies i UA przeglądarki. Uruchom lokalnie —
żaden bajt nie wychodzi poza Twój komputer.

Użycie:
  python diag_gdown_response.py --id <DRIVE_FILE_ID> [--cookies ~/cookies.txt]

DRIVE_FILE_ID to część po 'id=' z linku (np. z kolumny w dashboardzie albo
z https://drive.google.com/uc?id=XXXX). Wybierz plik, który failuje.

Wypisze: łańcuch przekierowań, końcowy URL, Content-Type, czy dostał PLIK
czy stronę HTML, i sklasyfikuje HTML (consent / logowanie / quota / inne)
plus krótki, ocenzurowany fragment. Na tej podstawie wiadomo, czego brakuje.
"""
from __future__ import annotations

import argparse
import sys
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import requests

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/98.0.4758.102 Safari/537.36"
)


def classify(html: str) -> str:
    low = html.lower()
    if "consent.google.com" in low or "before you continue" in low or (
        "zanim przejdziesz" in low
    ):
        return ("STRONA ZGODY (consent). Brakuje cookie SOCS/CONSENT — Google "
                "pokazuje ścianę zgody klientom bez zaakceptowanej zgody.")
    if "accounts.google.com" in low or "signin" in low or "zaloguj" in low:
        return ("STRONA LOGOWANIA. Cookies nie są rozpoznane jako zalogowana "
                "sesja (niekompletne/wygasłe cookies).")
    if "download-form" in low or "uc?export=download" in low:
        return ("STRONA POTWIERDZENIA (duży plik / skan antywirusowy) — "
                "gdown normalnie ją obsługuje.")
    if "quota" in low or "too many users" in low or "many accesses" in low:
        return "STRONA LIMITU (quota / too many users) — twardy limit pobrań."
    return "Nierozpoznana strona HTML (patrz fragment poniżej)."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", required=True, help="Google Drive file ID")
    ap.add_argument("--cookies", default=None, help="Ścieżka do cookies.txt")
    ap.add_argument(
        "--no-ua", action="store_true",
        help="Wyślij bez UA przeglądarki (jak domyślny python-requests), "
             "żeby porównać zachowanie."
    )
    args = ap.parse_args()

    sess = requests.Session()
    if not args.no_ua:
        sess.headers.update({"User-Agent": BROWSER_UA})

    n_cookies = 0
    if args.cookies:
        cpath = Path(args.cookies).expanduser()
        if not cpath.is_file():
            print(f"Brak pliku cookies: {cpath}", file=sys.stderr)
            return 2
        jar = MozillaCookieJar(str(cpath))
        jar.load(ignore_discard=True, ignore_expires=True)
        sess.cookies.update(jar)
        n_cookies = len(list(jar))
        names = sorted(c.name for c in jar)
        important = {"SID", "SSID", "HSID", "SAPISID", "APISID",
                     "__Secure-1PSID"}
        print(f"Wczytano {n_cookies} cookies. Kluczowe obecne: "
              f"{sorted(important & set(names))}")
        missing = important - set(names)
        if missing:
            print(f"  UWAGA brak: {sorted(missing)}")
        if "SOCS" not in names and "CONSENT" not in names:
            print("  UWAGA: brak cookie SOCS/CONSENT — możliwa ściana zgody EU.")
    else:
        print("Bez cookies (test anonimowy).")

    url = f"https://drive.google.com/uc?id={args.id}"
    print(f"\nGET {url}  (UA: {'brak' if args.no_ua else 'przeglądarka'})")
    res = sess.get(url, stream=True, allow_redirects=True, timeout=60)

    print(f"\nStatus: {res.status_code}")
    if res.history:
        print("Przekierowania:")
        for h in res.history:
            print(f"  {h.status_code} -> {h.headers.get('Location','?')}")
    print(f"Końcowy URL: {res.url}")
    ct = res.headers.get("Content-Type", "")
    cd = res.headers.get("Content-Disposition", "")
    print(f"Content-Type: {ct}")
    print(f"Content-Disposition: {cd or '(brak)'}")

    if cd or not ct.startswith("text/html"):
        print("\n=> WYNIK: Google zwrócił PLIK (jest Content-Disposition / "
              "nie-HTML). gdown powinien go pobrać. Jeśli mimo to failuje, "
              "problem jest po stronie zapisu/temp, nie pobierania.")
        return 0

    # HTML — pokaż klasyfikację i fragment
    html = res.text
    print(f"\n=> WYNIK: Google zwrócił STRONĘ HTML ({len(html)} znaków).")
    print("Klasyfikacja:", classify(html))
    snippet = " ".join(html.split())[:600]
    print("\nFragment (ocenzurowany do 600 znaków):\n" + snippet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
