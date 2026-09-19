# AGENTS.md — studio

**Najpierw obowiązuje `organizer/AGENTS.md`.** Ten plik nic z niego nie zdejmuje;
dokłada wyłącznie reguły wynikające z tego, że studio jest interfejsem **do zapisu**
nad bazą, którą reszta potoku traktuje jako źródło prawdy.

Zakres: `organizer/studio/` — backend `api/`, frontend `web/`. Plan i uzasadnienia
decyzji: `PLAN.md`. Stan prac: `TODO-studio.md` (odhaczaj tam, nie w `organizer/TODO.md`).

## Reguły tego podprojektu

1. **Frontend nie liczy nic, czego nie policzył `orglib`.** Kategorie, progi,
   ścieżki docelowe, klastry, walidacja planu — wszystko przychodzi z API. Pierwsza
   reguła policzona w JS oznacza dwie klasyfikacje dające różne wyniki.
2. **Backend importuje `orglib`, a długich etapów nie przepisuje.** Extract,
   classify, build_plan, apply i verify uruchamiaj jako podproces istniejącego CLI
   ze streamem logów. Jedna implementacja potoku, nie druga.
3. **Serwer nasłuchuje wyłącznie na `127.0.0.1`.** Bez kont, bez autoryzacji, bez
   wystawiania na zewnątrz — to narzędzie jednego człowieka na jego maszynie.
   Adres inny niż loopback ma odmawiać startu, nie ostrzegać.
4. **Endpoint podglądu jest tylko do odczytu i wyłącznie po plikach z indeksu.**
   Ścieżki przepuszczaj przez ten sam helper containmentu, co reszta potoku. Podgląd
   nie jest boczną ścieżką do `00_SOURCES` ani do repo paczki.
5. **Zapis decyzji idzie przez funkcję z B14**, nie własnym SQL-em w widoku.
   Strażnik na wiersze `run_id='ground_truth'` obowiązuje tak samo jak w CLI.
6. **Bramka przed `apply` zostaje bramką.** Kod wyjścia 2 z `validate_plan`
   unieruchamia zapis **po stronie serwera**; ukrycie przycisku w interfejsie nie
   jest zabezpieczeniem. Potwierdzenie człowieka dotyczy konkretnego planu.
7. **Nie dublujemy synapse.** Graf zostaje w `vendor/synapse`; studio go osadza
   i linkuje po identyfikatorze treści.
8. **Baza jest współdzielona z CLI.** Sprawdzaj `schema_version` przy starcie, używaj
   WAL i pokaż czytelny komunikat, gdy zapis trzyma inny proces.
9. **Błąd, którego nie złapały testy, najpierw dostaje czerwony test** — reguła
   z `organizer/AGENTS.md` obowiązuje tu bez wyjątku, łącznie z warstwą HTTP.

## Testy

Te same warstwy co w organizerze (`just test-fast|cli-check|e2e|probe`) plus
kontrakt API: liczby z endpointów muszą zgadzać się z tym, co liczy `orglib`
(punkt odniesienia: `scripts/status_report.py`). Do tego dwie kontrole, które nie
mogą zniknąć wraz z refaktorem: odmowa startu na adresie spoza loopbacka
i containment ścieżek podglądu. Obie mają mutację w `tests/mutations/`.

Frontend testuj jak `synapse-viewer` (vitest), a widoki, które mają być czytelne,
sprawdzaj **oczami na realnych danych** — przy 4 189 węzłach grafu cztery realne
wady wyszły dopiero w przeglądarce, nie w kodzie ani w testach.
