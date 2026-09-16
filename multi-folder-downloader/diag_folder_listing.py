#!/usr/bin/env python3
"""
Diagnostyka LISTOWANIA folderu przez endpoint embeddedfolderview (ten sam,
którego używa skrypt do traversalu). Pokazuje, ile pozycji Google zwraca dla
danego folderu — żeby sprawdzić, czy "pusty" folder jest naprawdę pusty, czy
endpoint oddał pustą/blokującą stronę.

Użycie:
  python diag_folder_listing.py --id <FOLDER_ID> [--cookies cookies.txt] [--no-ua]

FOLDER_ID to część po /folders/ w linku do folderu Google Drive.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import bs4
import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/98.0.4758.102 Safari/537.36"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", required=True, help="Google Drive folder ID")
    ap.add_argument("--cookies", default=None)
    ap.add_argument("--no-ua", action="store_true")
    args = ap.parse_args()

    sess = requests.Session()
    if not args.no_ua:
        sess.headers.update({"User-Agent": UA})
    if args.cookies:
        jar = MozillaCookieJar(str(Path(args.cookies).expanduser()))
        jar.load(ignore_discard=True, ignore_expires=True)
        sess.cookies.update(jar)
        print(f"Cookies: {len(list(jar))} wczytanych")
    else:
        print("Cookies: brak (anonimowo)")

    params = urllib.parse.urlencode({"id": args.id})
    url = f"https://drive.google.com/embeddedfolderview?{params}"
    print(f"GET {url}  (UA: {'brak' if args.no_ua else 'przeglądarka'})\n")

    res = sess.get(url, timeout=60)
    print("Status:", res.status_code)
    print("Content-Type:", res.headers.get("Content-Type"))
    print("Rozmiar HTML:", len(res.text), "znaków")

    soup = bs4.BeautifulSoup(res.text, features="html.parser")
    title = soup.title.string if soup.title else None
    print("Title:", repr(title))

    files = docs = folders = 0
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if not isinstance(href, str):
            continue
        if re.match(r"https://drive\.google\.com/file/d/([-\w]{25,})/view", href):
            files += 1
        elif re.match(r"https://docs\.google\.com/(\w+)/d/([-\w]{25,})/", href):
            docs += 1
        elif "/folders/" in href or "embeddedfolderview" in href:
            folders += 1

    total = files + docs + folders
    print(f"\nZnalezione pozycje: pliki={files}, docs={docs}, "
          f"foldery={folders}  (RAZEM={total})")

    if total == 0:
        print("\n=> PUSTO. Endpoint nie zwrócił żadnych pozycji.")
        low = res.text.lower()
        for kw, msg in [
            ("sign in", "strona logowania"),
            ("consent", "strona zgody"),
            ("many accesses", "throttling"),
            ("quota", "limit"),
            ("error", "strona błędu"),
        ]:
            if kw in low:
                print(f"   wykryto: {msg} ('{kw}')")
        print("\nFragment (pierwsze 800 znaków):\n"
              + " ".join(res.text.split())[:800])
    else:
        print("\n=> Folder MA zawartość widoczną dla tego żądania. "
              "Jeśli lokalnie jest pusty, w checkpoint zapisano złe (puste) "
              "listowanie — trzeba go przelistować (patrz --relist-empty).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
