# STATUS — Paczka Organizer

Plik **generowany** przez `scripts/status_report.py` (`just status`). Nie edytuj ręcznie;
źródłem liczb jest operacyjny indeks SQLite, a nie katalogi z raportami.

- Wygenerowano: 2026-09-19T00:38:21Z
- Źródła: 14 paczek, 9540 katalogów (w tym 4386 duplikatów), 48049 plików
- Statusy plików: error: 37, extracted: 23074, hashed: 24938
- Treści: 19337 unikalnych, 7788 z wyekstrahowanym tekstem
- Relacje podobieństwa: 936 · pozycje planu: 2519 · wpisy w `applied`: 1750 (dziś w całości ground truth — `apply` jeszcze nie działał)

## Przedmioty

`w paczce` = treści rozpoznane w repo docelowym (ground truth). `plan` = decyzje
zapisane przez `just subject-plan`. `do obejrzenia` = pozycje planu z `needs_review`.

| SEM | grupa | skrót | przedmiot | etap | w paczce | plan | do obejrzenia | kopiuj | pomiń | media | ostatni plan |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Wspolne | AL | Algebra_Liniowa | tylko ground truth | 13 | 0 | 0 | 0 | 0 | 0 | — |
| 1 | Wspolne | AM | Analiza_Matematyczna | tylko ground truth | 50 | 0 | 0 | 0 | 0 | 0 | — |
| 1 | Wspolne | HDMI | Humanistyka_Dla_Inżynierów | tylko ground truth | 17 | 0 | 0 | 0 | 0 | 0 | — |
| 1 | Wspolne | HiH | Hipertekst_i_Hipermedia | tylko ground truth | 32 | 0 | 0 | 0 | 0 | 0 | — |
| 1 | Wspolne | ME | Matematyka_Elementarna | tylko ground truth | 85 | 0 | 0 | 0 | 0 | 0 | — |
| 1 | Wspolne | PP | Podstawy_Programowania | tylko ground truth | 228 | 0 | 0 | 0 | 0 | 0 | — |
| 1 | Wspolne | WAI | Wytwarzanie_Aplikacji_Internetowych | tylko ground truth | 25 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | AiSD | Algorytmy_i_Struktury_Danych | tylko ground truth | 212 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | JAI | Język_Angielski_I | tylko ground truth | 3 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | MD | Matematyka_Dyskretna | tylko ground truth | 162 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | PEiM | Podstawy_Elektroniki_i_Metrologii | tylko ground truth | 33 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | PF | Podstawy_Fizyki | tylko ground truth | 5 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | PO | Programowanie_Obiektowe | tylko ground truth | 16 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | SO | Systemy_Operacyjne | tylko ground truth | 25 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | UC | Układy_Cyfrowe | tylko ground truth | 108 | 0 | 0 | 0 | 0 | 0 | — |
| 2 | Wspolne | WFI | Wychowanie_Fizyczne_I | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | AKO | Architektura_Komputerów | plan do przeglądu | 127 | 2437 | 69 | 1497 | 923 | 17 | 2026-09-19T00:25:50Z |
| 3 | Wspolne | BD | Bazy_Danych | tylko ground truth | 2 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | FW | Fizyka_Współczesna | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | GK | Grafika_Komputerowa | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | JAII | Język_Angielski_II | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | JP | Języki_Programowania | tylko ground truth | 2 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | MII | Multimedia_I_Interfejsy | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | PAA | Podstawy_Analizy_Algorytmów | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 3 | Wspolne | WFI | Wychowanie_Fizyczne_II | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | JAIII | Język_Angielski_III | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | MN | Metody_Numeryczne | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | MPwI | Metody_Probabilistyczne_w_Informatyce | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | PR | Przetwarzanie_Rozproszone | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | PT | Platformy_Technologiczne | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | SI | Sztuczna_Inteligencja | tylko ground truth | 1 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | SK | Sieci_Komputerowe | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | SOMOXII | System_Operacyjny_MAC_OS_X_I_IOS | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | SWiM | Systemy_Wbudowane_i_Mikroprocesory | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 4 | Wspolne | WDC | Wprowadzenie_Do_Cyberbezpieczeństwa | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Aplikacje | ASW | Aplikacje_Systemów_Wbudowanych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Aplikacje | AUI | Architektury_Usług_Internetowych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Aplikacje | BE | Biznes_Elektroniczny | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Aplikacje | HD | Hurtownie_Danych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Aplikacje | SIP | Systemy_Informacji_Przestrzennej | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Aplikacje | WI | Wizualizacja_Informacji | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Systemy | ASK | Administrowanie_Systemami_Komputerowymi | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Systemy | KK | Konstrukcja_Kompilatorów | tylko ground truth | 53 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Systemy | KSS | Komputerowe_Systemy_Sterowania | tylko ground truth | 108 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Systemy | OS | Oprogramowanie_Systemowe | tylko ground truth | 60 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Systemy | SA | Systemy_Agentowe | tylko ground truth | 15 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Systemy | SBD | Struktury_Baz_Danych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Wspolne | IO | Inżynieria_Oprogramowania | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Wspolne | JAIV | Język_Angielski_IV | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Wspolne | PGI | Projekt_Grupowy_I | tylko ground truth | 12 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Wspolne | SAI | Społeczne_Aspekty_Informatyki | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 5 | Wspolne | SK-L | Sieci_Komputerowe_-_Laboratorium | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Aplikacje | BSK | Bezpieczeństwo_Systemów_Komputerowych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Aplikacje | BW | Bazy_Wiedzy | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Aplikacje | ED | Eksploracja_Danych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Aplikacje | JO | Jakość_Oprogramowania | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Aplikacje | KSR | Komponentowe_Systemy_Rozproszone | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Aplikacje | WZR | Wirtualne_Zespoły_Robocze | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Systemy | ISP | Inżynieria_Systemów_Programowalnych | tylko ground truth | 51 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Systemy | LSB | Lokalne_Sieci_Bezprzewodowe | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Systemy | MSO | Mobilne_Systemy_Operacyjne | tylko ground truth | 8 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Systemy | SK | Sieci_Korporacyjne | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Systemy | ST | Systemy_Telekomunikacyjne | tylko ground truth | 99 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Systemy | ZAKO | Zaawansowane_Architektury_Komputerów | tylko ground truth | 21 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Wspolne | PDII | Projekt_Dyplomowy_Inżynierski_I | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Wspolne | PGII | Projekt_Grupowy_II | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Wspolne | RPI | Realizacja_Projektu_Informatycznego | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Wspolne | SDII | Seminarium_Dyplomowe_Inżynierskie_I | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Wspolne | TRP | Technika_Radia_Programowalnego | tylko ground truth | 26 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Wspolne | ZBS | Zarządzanie_Bezpieczeństwem_Sieci | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 6 | Wspolne | ZFI | Zarządzanie_Firmą_Informatyczną | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KAIMS_Algorytmy_I_Modelowanie_Systemów | JPNP | Języki_Programowania_Na_Platformie_NET | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KAIMS_Algorytmy_I_Modelowanie_Systemów | PLA | Programowanie_Lokalnych_Aplikacji | tylko ground truth | 15 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KAIMS_Algorytmy_I_Modelowanie_Systemów | RAI | Realizacja_Aplikacji_Internetowych | tylko ground truth | 20 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KAIMS_Algorytmy_I_Modelowanie_Systemów | WPAIT | Wybrane_Problemy_Algorytmiczne_I_Technologiczne | tylko ground truth | 4 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KAIMS_Algorytmy_I_Modelowanie_Systemów | ZTO | Zaawansowane_Techniki_Obiektowe | tylko ground truth | 9 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KASK_Architektura_Systemów_Komputerowych | NIAJ | Narzędzia_I_Aplikacje_JEE | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KASK_Architektura_Systemów_Komputerowych | PAI | Projektowanie_Aplikacji_Internetowych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KASK_Architektura_Systemów_Komputerowych | SI | Serwisy_Internetowe_NET | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KBD_Bazy_Danych | ABD | Aplikacje_Baz_Danych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KBD_Bazy_Danych | NBD | Nierelacyjne_Bazy_Danych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KBD_Bazy_Danych | PSSO | Projektowanie_Skalowalnych_Systemów_Obiektowych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KBD_Bazy_Danych | ZSBD | Zarządzanie_Systemami_Baz_Danych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KISI_Inteligentne_Systemy_Interaktywne | AK | Animacja_Komputerowa | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KISI_Inteligentne_Systemy_Interaktywne | DC | Dokumenty_Cyfrowe | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KISI_Inteligentne_Systemy_Interaktywne | PGK | Projektowanie_Gier_Komputerowych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KISI_Inteligentne_Systemy_Interaktywne | PO | Przetwarzanie_Obrazów | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KSG_Systemy_Geoinformatyczne | PDNPM | Przetwarzanie_Danych_Na_Platformach_Mobilnych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KSG_Systemy_Geoinformatyczne | PKC | Podstawy_Kartografii_Cyfrowej | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KSG_Systemy_Geoinformatyczne | SNSGIG | Systemy_Nawigacji_Satelitarnej_GPS_I_Galileo | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KSG_Systemy_Geoinformatyczne | TWDP | Trójwymiarowa_Wizualizacja_Danych_Przestrzennych | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KT_Teleinformatyka | ASK | Administrowanie_Sieciami_Komputerowymi | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KT_Teleinformatyka | SI | Sieci_IP | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KT_Teleinformatyka | UIAM | Usługi_I_Aplikacje_Multimedialne | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | KT_Teleinformatyka | ZS | Zarządzanie_Sieciami | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | Wspolne | P | Praktyka | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | Wspolne | PDIII | Projekt_Dyplomowy_Inżynierski_II | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |
| 7 | Wspolne | SDIII | Seminarium_Dyplomowe_Inżynierskie_II | nietknięty | 0 | 0 | 0 | 0 | 0 | 0 | — |

## Kolejka

- **plan do przeglądu** (1): AKO (sem 3)
- **tylko ground truth** (32): AL (sem 1), AM (sem 1), AiSD (sem 2), BD (sem 3), HDMI (sem 1), HiH (sem 1), ISP (sem 6), JAI (sem 2), JP (sem 3), KK (sem 5), KSS (sem 5), MD (sem 2) … (+20)
- **nietknięty** (65): ABD (sem 7), AK (sem 7), ASK (sem 5), ASK (sem 7), ASW (sem 5), AUI (sem 5), BE (sem 5), BSK (sem 6), BW (sem 6), DC (sem 7), ED (sem 6), FW (sem 3) … (+53)
