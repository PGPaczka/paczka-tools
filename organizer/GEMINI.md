# GEMINI.md — adapter Gemini / Antigravity

Najpierw przeczytaj `AGENTS.md` i trzymaj się go bez wyjątków. To kanoniczne,
model-agnostyczne źródło zasad projektu.

Gemini jest tu używany głównie przez `agy -p` i
`scripts/orglib/llm_client.py` do masowego przetwarzania tekstu. W trybie
headless z sandboxem nie zakładaj dostępu do narzędzi: wejście powinno być
samowystarczalne i zawierać wymagane fragmenty tekstu, a wyjście musi odpowiadać
żądanemu schematowi.

Nie modyfikuj filesystemu ani `00_SOURCES`; dla pracy programistycznej użyj
Claude Code lub Codexa.
