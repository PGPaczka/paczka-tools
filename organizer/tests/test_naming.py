"""Q7: ta sama treść pod wieloma nazwami — którą z nich zaproponować człowiekowi.

Przypadki NIE są wymyślone: to zestawy nazw wzięte wprost z indeksu tej paczki
(613 treści ma więcej niż jedną nazwę, rekordzista 81). Dlatego reguła jest krótka
i opisuje to, co w danych widać naprawdę: znaczniki kopii, nazwy generyczne z aparatu
i nazwy opisowe, które ktoś kiedyś nadał ręcznie.

Funkcja niczego nie zmienia — zwraca JEDNĄ z podanych nazw. Wymyślanie nowej nazwy
byłoby zgadywaniem, a nazwa pliku w paczce to jedyny indeks, jaki człowiek ma pod ręką.
"""

from __future__ import annotations

import pytest

from orglib.naming import best_name


def test_a_copy_marker_loses_to_the_original() -> None:
    assert best_name(["Kopia egzamin 23.06.2009.pdf", "egzamin 23.06.2009.pdf"]) \
        == "egzamin 23.06.2009.pdf"


def test_english_copy_marker_loses_too() -> None:
    assert best_name(["Copy of 11.jpg", "11.jpg"]) == "11.jpg"


def test_numbered_duplicate_loses() -> None:
    assert best_name(["egzamin_SO (1).pdf", "egzamin_SO.pdf"]) == "egzamin_SO.pdf"


def test_the_most_telling_name_wins() -> None:
    """Zestaw prosto z indeksu: cztery nazwy tego samego skanu zerówki."""
    nazwy = [
        "Kopia zerówka2013_B.jpg",
        "zerówka2013_B.jpg",
        "2013_zerówka_B.jpg",
        "AiSD_2012_egzamin_zerowy_grupa_B.jpg",
    ]

    assert best_name(nazwy) == "AiSD_2012_egzamin_zerowy_grupa_B.jpg"


def test_a_camera_name_loses_to_a_human_one() -> None:
    """`IMG_20190312_123456.jpg` nie mówi nic — to nazwa nadana przez telefon."""
    assert best_name(["IMG_20190312_123456.jpg", "kolokwium_1_zadania.jpg"]) \
        == "kolokwium_1_zadania.jpg"


def test_a_descriptive_name_starting_like_a_scanner_is_not_generic() -> None:
    """„Skaner" rozpoznajemy po cyfrach, nie po pierwszych literach.

    `Scan_wykladu_AKO.pdf` to nazwa nadana ręcznie — wzorzec `scan*` bez tego warunku
    zdegradowałby ją do poziomu `scan001.pdf`.
    """
    assert best_name(["IMG_0001.jpg", "Scan_wykladu_AKO.pdf"]) == "Scan_wykladu_AKO.pdf"


def test_only_camera_names_still_give_an_answer() -> None:
    """Gdy wszystkie nazwy są byle jakie, wybór ma być POWTARZALNY, a nie losowy."""
    nazwy = ["IMG_0002.jpg", "IMG_0001.jpg"]

    assert best_name(nazwy) == best_name(list(reversed(nazwy))) == "IMG_0001.jpg"


def test_the_answer_is_always_one_of_the_given_names() -> None:
    """Nazw nie wymyślamy: wynik musi dać się wskazać palcem w prowenancji."""
    nazwy = ["Kopia AiSDegz2013.pdf", "AiSDegz2013.pdf", "2013_AiSDegz.pdf"]

    assert best_name(nazwy) in nazwy


def test_a_single_name_is_the_answer() -> None:
    assert best_name(["wyklad.pdf"]) == "wyklad.pdf"


def test_no_names_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError):
        best_name([])


def test_blank_entries_are_ignored() -> None:
    assert best_name(["", "   ", "egzamin.pdf"]) == "egzamin.pdf"
