"""Q7: która z nazw tej samej treści jest najlepsza dla człowieka.

Jedna treść leży w tej paczce nawet pod kilkunastoma nazwami (rekordzista: 81), bo
adresujemy ją `sha256`, a nazwy przychodzą z różnych paczek i kopii. Nazwa w paczce jest
więc WYBOREM, nie faktem — i ten wybór da się podpowiedzieć, bo w danych widać trzy
powtarzalne wzorce: znaczniki kopii (`Kopia …`, `… (1)`), nazwy nadane przez aparat
albo skaner (`IMG_20190312_123456.jpg`) i nazwy nadane ręcznie, które mówią, co to jest
(`AiSD_2012_egzamin_zerowy_grupa_B.jpg`).

Funkcja zwraca JEDNĄ z podanych nazw i nigdy nie tworzy nowej: nazwa musi dać się
wskazać palcem w prowenancji, inaczej podpowiedź byłaby zgadywaniem.
"""

from __future__ import annotations

import re
from os.path import splitext
from typing import Sequence

#: Znacznik kopii: `Kopia X`, `Copy of X`, `X (1)`, `X - kopia`.
_COPY_MARKER = re.compile(
    r"^(?:Kop(?:i)?a |Copy of )|\([1-9][0-9]*\)$| - (?:kopia|Copy)$",
    re.IGNORECASE,
)

#: Nazwa nadana przez urządzenie, nie przez człowieka. Wzorce WYMAGAJĄ cyfr albo pełnego
#: dopasowania — inaczej „Scan_wykladu_AKO.pdf" (nazwa opisowa!) wpadłoby w „skaner".
_GENERIC_NAME = re.compile(
    r"^(?:IMG[-_ ]?[0-9]+"
    r"|DSC[-_ ]?[0-9]+"
    r"|scan[-_ ]?[0-9]*$"
    r"|obraz(?: \([0-9]+\))?$"
    r"|zrzut ekranu.*$"
    r"|bez tytu\u0142u$"
    r"|[0-9]{8}[-_ ][0-9]{6}$)",
    re.IGNORECASE,
)


def best_name(names: Sequence[str]) -> str:
    """Wybiera jedną z podanych nazw — nigdy nie tworzy nowej.

    Kryteria, od najważniejszego: brak znacznika kopii, nazwa opisowa zamiast nadanej
    przez urządzenie, więcej członów, dłuższa nazwa, a na koniec kolejność alfabetyczna.
    Ostatnie kryterium nie jest ozdobnikiem: przy pełnym remisie wynik musi być
    POWTARZALNY, bo inaczej ta sama treść dostawałaby różne podpowiedzi przy każdym
    odświeżeniu widoku.

    Człony i długość liczymy bez rozszerzenia; człony rozdzielają `_`, `-`, spacja i kropka.
    """
    candidates = [name for name in names if name.strip()]
    if not candidates:
        raise ValueError("brak nazw do wyboru")

    def score(name: str) -> tuple[bool, bool, int, int, str]:
        stem = splitext(name)[0]
        parts = [part for part in re.split(r"[_\s.-]+", stem) if part]
        # Minusy przy długościach, bo całość wybieramy przez `min`: `False` (brak kopii)
        # i `False` (nie generyczna) mają wygrywać, a „więcej" ma znaczyć „lepiej".
        return (
            bool(_COPY_MARKER.search(stem)),
            bool(_GENERIC_NAME.search(stem)),
            -len(parts),
            -len(stem),
            name,
        )

    return min(candidates, key=score)
