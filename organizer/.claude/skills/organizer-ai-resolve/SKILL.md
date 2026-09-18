---
name: organizer-ai-resolve
description: "Użyj, gdy manifest jednego przedmiotu ma pozycje nierozstrzygnięte po klasyfikacji deterministycznej: uruchom klasyfikator AI (scripts/ai_resolve.py) i oceń jego decyzje. Sam nie klasyfikujesz i nie wykonujesz apply."
disable-model-invocation: false
argument-hint: "SKROT SEMESTR [--limit N]"
arguments: [skrot, semestr]
allowed-tools: Bash, Read, Write(reports/**)
---

# organizer-ai-resolve — $skrot sem $semestr

Jesteś **koordynatorem**, nie klasyfikatorem. Masowa klasyfikacja resztek idzie do
backendu z `config/thresholds.yaml: llm` (domyślnie `codex_cli` = limit ChatGPT), a nie
do Twojej sesji — to jest cel tego skilla. **Nie klasyfikuj pozycji samodzielnie** i nie
forkuj do tego podagenta: jedna i druga droga zjada limit koordynatora, który ma iść na
myślenie o planie, a nie na przepisywanie nazw plików.

## Krok 1 — zobacz, co w ogóle jest do zrobienia

```bash
just subject-ai-resolve $semestr $skrot --dry-run
```

Wypisze przedmiot, liczbę pozycji w manifeście, liczbę do rozstrzygnięcia i backend.
Brak manifestu = najpierw `just subject-prepare $semestr $skrot`.

Gdy pozycji jest dużo, zacznij od próbki: dodaj `--limit 10`, oceń jakość decyzji
(krok 3) i dopiero potem puść resztę. Skrypt jest wznawialny — sha256 już zapisane
w `plan.ai.jsonl` są pomijane, więc druga część przebiegu nie płaci za pierwszą.

## Krok 2 — uruchom klasyfikator

```bash
just subject-ai-resolve $semestr $skrot
```

Wynik: `plan.ai.jsonl` obok manifestu, jedna linia na sha256, zgodna z
`prompts/plan_line.schema.json`. Skrypt sam waliduje każdą linię wobec schematu,
wymusza progi z `thresholds.yaml` i odrzuca kategorie spoza form przedmiotu — pozycje,
których nie dało się domknąć, trafiają na listę błędów zamiast do planu.

Niezerowy kod wyjścia oznacza, że część pozycji się nie powiodła. Przeczytaj wypisane
błędy: to zwykle brak `text_head` (nie zrobiono ekstrakcji) albo model uparcie
proponuje kategorię niedozwoloną dla tego przedmiotu.

## Krok 3 — oceń wynik (to jest Twoja właściwa praca)

Przejrzyj `plan.ai.jsonl` i odpowiedz człowiekowi **≤10 linii**:

1. ile decyzji zapisano, rozkład `action`, ile `needs_review`;
2. czy jakaś decyzja z `confidence` ≥ 0.90 wygląda podejrzanie — typowo: `target_rel`
   niezgodny z `config/syntax.yaml`, rok wzięty z nazwy katalogu zamiast z treści,
   kategoria `inne` przy oczywistym wykładzie;
3. co wymaga decyzji człowieka, zanim plan pójdzie dalej.

Nie poprawiaj decyzji modelu edycją `plan.ai.jsonl` w ciemno. Jeśli klasa błędów się
powtarza, popraw **prompt** (`prompts/classify_ambiguous.md`) albo próg
w `thresholds.yaml` i puść przebieg ponownie na tę próbkę — inaczej ten sam błąd wróci
przy następnym przedmiocie.

## Granice

- Nie uruchamiasz `apply` ani niczego, co dotyka materiałów. Ten skill kończy się na
  pliku `plan.ai.jsonl` i Twojej ocenie.
- Nie skanujesz `00_SOURCES`. Wejściem jest manifest, nie źródła.
- Nie zmieniasz backendu na `claude_cli` „żeby było lepiej”. Gdy jakość nie wystarcza,
  zgłoś to człowiekowi z przykładami — wybór modelu to jego decyzja kosztowa.
