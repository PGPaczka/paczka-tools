#!/usr/bin/env python3
"""
Diagnostyka Google Drive — jeden skrypt do folderów, plików i plików native
(Docs/Sheets/Slides). Pokazuje, CO naprawdę zwraca Google, żeby zdiagnozować
puste listowania, throttling, ściany logowania/zgody i błędy eksportu.

Wszystko dzieje się lokalnie — żaden bajt nie wychodzi poza Twój komputer.

Typ celu jest wykrywany automatycznie z linku (lub podaj --type):
  - folder:        .../drive/folders/<ID>   lub  embeddedfolderview?id=<ID>
  - plik:          .../file/d/<ID>/view     lub  uc?id=<ID>
  - native (Docs): docs.google.com/document|spreadsheets|presentation/d/<ID>
  - samo ID / open?id=<ID>: typ nieznany -> skrypt sam sprawdzi

WAŻNE: listowanie folderu (embeddedfolderview) jest zawsze ANONIMOWE —
wysłanie cookies do tego endpointu powoduje przekierowanie na logowanie i
pustą odpowiedź. Cookies są używane tylko przy pliku/eksporcie.

Przykłady:
  python diag_drive.py 'https://drive.google.com/drive/folders/ID'
  python diag_drive.py 'https://drive.google.com/uc?id=ID' --cookies cookies.txt
  python diag_drive.py ID --type sheet --cookies cookies.txt
  python diag_drive.py 'https://drive.google.com/open?id=ID' --cookies cookies.txt
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

# child_type-like -> (segment eksportu, format)
EXPORT = {
    "doc": ("document", "docx"),
    "sheet": ("spreadsheets", "xlsx"),
    "slide": ("presentation", "pptx"),
}
IMPORTANT_COOKIES = {"SID", "SSID", "HSID", "SAPISID", "APISID", "__Secure-1PSID"}


# ---------------------------------------------------------------- detekcja typu
def detect(target: str) -> tuple[str, str | None]:
    """Zwraca (kind, file_id). kind: folder|file|doc|sheet|slide|unknown."""
    t = target.strip()

    m = re.search(
        r"docs\.google\.com/(document|spreadsheets|presentation)/d/([-\w]{20,})",
        t,
    )
    if m:
        seg = {"document": "doc", "spreadsheets": "sheet",
               "presentation": "slide"}[m.group(1)]
        return seg, m.group(2)

    if "embeddedfolderview" in t:
        m = re.search(r"[?&]id=([-\w]{20,})", t)
        if m:
            return "folder", m.group(1)

    m = re.search(r"/folders/([-\w]{20,})", t)
    if m:
        return "folder", m.group(1)

    m = re.search(r"/file/d/([-\w]{20,})", t)
    if m:
        return "file", m.group(1)

    if "uc?id=" in t or "uc?export=" in t:
        m = re.search(r"[?&]id=([-\w]{20,})", t)
        if m:
            return "file", m.group(1)

    # open?id / ?id / bare id -> nieznany typ
    m = re.search(r"[?&]id=([-\w]{20,})", t)
    if m:
        return "unknown", m.group(1)
    m = re.fullmatch(r"[-\w]{20,}", t)
    if m:
        return "unknown", t

    return "unknown", None


# ------------------------------------------------------------------- sesje HTTP
def make_session(cookies: str | None, no_ua: bool) -> tuple[requests.Session, int]:
    sess = requests.Session()
    if not no_ua:
        sess.headers.update({"User-Agent": UA})
    n = 0
    if cookies:
        jar = MozillaCookieJar(str(Path(cookies).expanduser()))
        jar.load(ignore_discard=True, ignore_expires=True)
        sess.cookies.update(jar)
        n = len(list(jar))
    return sess, n


# --------------------------------------------------------------------- probes
def probe_folder(folder_id: str, no_ua: bool, had_cookies: bool) -> int:
    print(f"[FOLDER] id={folder_id}")
    if had_cookies:
        print("  (cookies celowo pominięte — psują embeddedfolderview)")
    sess, _ = make_session(None, no_ua)  # zawsze anonimowo
    params = urllib.parse.urlencode({"id": folder_id})
    url = f"https://drive.google.com/embeddedfolderview?{params}"
    print(f"  GET {url}")
    res = sess.get(url, timeout=60)
    soup = bs4.BeautifulSoup(res.text, features="html.parser")
    title = soup.title.string if soup.title else None
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
    print(f"  status={res.status_code}  title={title!r}  "
          f"pliki={files} docs={docs} foldery={folders} RAZEM={total}")
    if total > 0:
        print("  => OK: folder ma zawartość. Jeśli lokalnie pusty -> --relist-empty.")
        return 0
    low = res.text.lower()
    if "servicelogin" in low or "accounts.google.com" in low:
        print("  => LOGOWANIE: endpoint odbił na logowanie (zwykle bo wysłano "
              "cookies albo folder nie jest publiczny).")
    elif title and "redirect" not in str(title).lower():
        print("  => PUSTO: folder wygląda na realnie pusty.")
    else:
        print("  => PUSTO / nieznana odpowiedź.")
    print("  fragment:", " ".join(res.text.split())[:400])
    return 0


def probe_file(file_id: str, cookies: str | None, no_ua: bool) -> int:
    print(f"[PLIK] id={file_id}")
    sess, n = make_session(cookies, no_ua)
    print(f"  cookies: {n if cookies else 'brak'}")
    url = f"https://drive.google.com/uc?id={file_id}"
    print(f"  GET {url}")
    res = sess.get(url, stream=True, allow_redirects=True, timeout=60)
    print(f"  status={res.status_code}  final={res.url[:100]}")
    for h in res.history:
        print(f"    -> {h.status_code} {h.headers.get('Location','')[:80]}")
    ct = res.headers.get("Content-Type", "")
    cd = res.headers.get("Content-Disposition", "")
    print(f"  Content-Type={ct}  Content-Disposition={cd or '(brak)'}")
    if cd or not ct.startswith("text/html"):
        print("  => PLIK: Google zwrócił zawartość (gdown pobierze).")
    else:
        low = res.text.lower()
        if "many accesses" in low or "quota" in low:
            print("  => LIMIT/quota lub throttling.")
        elif "servicelogin" in low or "accounts.google.com" in low:
            print("  => LOGOWANIE: brak dostępu anonimowo — potrzebne cookies "
                  "lub plik nie jest publiczny.")
        elif "document" in res.url or "spreadsheets" in res.url or \
                "presentation" in res.url:
            print("  => To wygląda na plik NATIVE (Docs/Sheets/Slides) — użyj "
                  "--type doc|sheet|slide, żeby przetestować eksport.")
        else:
            print("  => STRONA HTML (nierozpoznana). Fragment:")
            print("    " + " ".join(res.text.split())[:400])
    return 0


def probe_export(kind: str, file_id: str, cookies: str | None, no_ua: bool) -> int:
    seg, fmt = EXPORT[kind]
    print(f"[NATIVE:{kind}] id={file_id}")
    sess, n = make_session(cookies, no_ua)
    print(f"  cookies: {n if cookies else 'brak'}")
    url = f"https://docs.google.com/{seg}/d/{file_id}/export?format={fmt}"
    print(f"  GET {url}")
    res = sess.get(url, stream=True, allow_redirects=True, timeout=60)
    ct = res.headers.get("Content-Type", "")
    cd = res.headers.get("Content-Disposition", "")
    print(f"  status={res.status_code}  Content-Type={ct}  "
          f"Content-Disposition={cd or '(brak)'}")
    if res.status_code == 200 and not ct.startswith("text/html"):
        print(f"  => OK: eksport do .{fmt} działa.")
    else:
        low = res.text.lower()
        if "servicelogin" in low or "accounts.google.com" in low:
            print("  => LOGOWANIE: eksport wymaga dostępu — sprawdź cookies "
                  "(dokument musi być widoczny dla Twojego konta).")
        else:
            print("  => Eksport nie zwrócił pliku. Fragment:")
            print("    " + " ".join(res.text.split())[:400])
    return 0


# ----------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("target", help="URL lub ID (folder / plik / native)")
    ap.add_argument("--cookies", default=None, help="Ścieżka do cookies.txt")
    ap.add_argument(
        "--type",
        choices=["auto", "folder", "file", "doc", "sheet", "slide"],
        default="auto",
        help="Wymuś typ celu (domyślnie: auto-wykrywanie z linku).",
    )
    ap.add_argument("--no-ua", action="store_true",
                    help="Wyślij bez UA przeglądarki (do porównania).")
    args = ap.parse_args()

    kind, file_id = detect(args.target)
    if args.type != "auto":
        kind = args.type
        # gdy podano --type a target to URL, i tak wyłuskaj ID
        if file_id is None:
            _, file_id = detect(args.target)
    if file_id is None:
        print("Nie udało się wyłuskać ID z:", args.target, file=sys.stderr)
        return 2

    if args.cookies and kind in {"file", "doc", "sheet", "slide", "unknown"}:
        p = Path(args.cookies).expanduser()
        if not p.is_file():
            print(f"Brak pliku cookies: {p}", file=sys.stderr)
            return 2
        jar = MozillaCookieJar(str(p))
        jar.load(ignore_discard=True, ignore_expires=True)
        names = {c.name for c in jar}
        miss = IMPORTANT_COOKIES - names
        if miss:
            print(f"UWAGA: w cookies brak: {sorted(miss)}")

    print(f"Wykryty typ: {kind}\n")

    if kind == "folder":
        return probe_folder(file_id, args.no_ua, had_cookies=bool(args.cookies))
    if kind in EXPORT:
        return probe_export(kind, file_id, args.cookies, args.no_ua)
    if kind == "file":
        return probe_file(file_id, args.cookies, args.no_ua)

    # unknown -> najpierw spróbuj jako folder (anonimowo), potem jako plik
    print("Typ nieznany — próbuję najpierw jako FOLDER, potem jako PLIK.\n")
    sess, _ = make_session(None, args.no_ua)
    params = urllib.parse.urlencode({"id": file_id})
    res = sess.get(
        f"https://drive.google.com/embeddedfolderview?{params}", timeout=60
    )
    soup = bs4.BeautifulSoup(res.text, features="html.parser")
    has_items = any(
        isinstance(a.get("href"), str)
        and re.search(r"/(file/d|folders)/|docs\.google\.com/\w+/d/",
                      a.get("href"))
        for a in soup.find_all("a")
    )
    if has_items:
        return probe_folder(file_id, args.no_ua, had_cookies=bool(args.cookies))
    print("(embeddedfolderview nie wygląda na folder — traktuję jako PLIK)\n")
    return probe_file(file_id, args.cookies, args.no_ua)


if __name__ == "__main__":
    raise SystemExit(main())
