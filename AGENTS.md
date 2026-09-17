# Zasady pracy w paczka-tools

Każde narzędzie ma własny katalog. Dla `organizer/` stosuj dodatkowo
`organizer/AGENTS.md`, w szczególności ochronę materiałów i proces zatwierdzania
planu. Nie zmieniaj niepowiązanych plików ani cudzych zmian.

## Lokalne commity zmian narzędzi

Po zakończeniu spójnej zmiany kodu, konfiguracji, skryptów, testów,
dokumentacji lub tekstowych raportów technicznych w tym repo **domyślnie
wykonaj lokalny commit**. Nie czekaj na osobne polecenie użytkownika.
Wyjątkiem jest jawne życzenie pozostawienia zmian bez commita.

- Najpierw wykonaj odpowiednie testy i przejrzyj diff.
- Commituj małe, logiczne zakresy i tylko sprawdzone pliki związane z zadaniem.
- Nie dołączaj niepowiązanych zmian użytkownika, sekretów ani danych lokalnych.
- W pracy delegowanej commity przygotowuje koordynator po przeglądzie wyników
  subagentów; sama możliwość zapisu plików nie upoważnia subagenta do commita.
- Nie wykonuj automatycznie push, PR ani merge. Wymagają osobnego polecenia;
  merge materiałów pozostaje po stronie człowieka.
- Na końcu podaj identyfikatory commitów, wynik kontroli i pozostałe ograniczenia.

## Materiały — bez zmiany dotychczasowych zasad

Zgoda na automatyczne commity narzędzi **nie obejmuje materiałów**,
niezależnie od tego, czy leżą poza repo, czy kiedyś pojawią się w jego obrębie.
Nie dodawaj ich do commitów narzędzi.

`00_SOURCES` pozostaje read-only. Zmiany kanonicznej paczki wykonują wyłącznie
skrypty organizera po walidacji i jawnej akceptacji konkretnego planu.
Commit materiałów wymaga dotychczasowej autoryzacji procesu, pomyślnego
`verify` i brancha przedmiotu. Samo zlecenie pracy nad narzędziami, wybór
skillu ani milczenie użytkownika nie są taką autoryzacją.
