"""Klient AI wymienny na backendy: chowa Claude/Codex/Gemini/API za jednym interfejsem.

Kontrakt: ``docs/ARCHITEKTURA_FINALv1.md`` §12 i ``AGENTS.md``. Skrypty potoku
(``ai_resolve.py`` i przyszłe) wołają wyłącznie
:class:`LLMClient` — nie wiedzą, który backend faktycznie odpowiedział. Wybór
backendu per zadanie (``classify``/``relate``/...) pochodzi z
``config/thresholds.yaml: llm`` (patrz :func:`load_llm_config`) i może zostać
jawnie nadpisany przez ``PACZKA_LLM_<TASK>_BACKEND`` /
``PACZKA_LLM_<TASK>_MODEL``. Launchery agentów używają tego mechanizmu, żeby
Claude i Codex mogły mieć różne backendy bez edycji wersjonowanego YAML.

Backendy
--------
- ``anthropic`` / ``openai`` — SDK importowane leniwie (brak pakietu => :class:`LLMError`
  z instrukcją instalacji); jeden user message, ``max_tokens=4096``; przy ``schema``
  system prompt prosi o czysty JSON.
- ``claude_cli`` — ``claude -p --permission-mode plan --output-format json [--model M]``,
  prompt przez stdin, stdout to JSON z polem ``result`` (tekst odpowiedzi modelu).
- ``codex_cli`` — ``codex exec -c model_provider="openai" -s read-only --ephemeral
  --skip-git-repo-check -C {cwd}
  [-m M] [--output-schema plik.json] -o {out.txt} -``, prompt przez stdin (argument
  ``-``); odpowiedź czyta się z pliku ``-o`` (stdout bywa zaśmiecony logiem sesji).
  ``-c model_provider="openai"`` wymusza konto OpenAI nawet gdyby ktoś ponownie
  przestawił bazowy ``~/.codex/config.toml`` na proxy (np. ``claude-code-router``) —
  wywołanie ma iść na limit ChatGPT, nigdy na limit Anthropic. Świadomie *nie*
  używamy ``--ignore-user-config``: ta flaga odcina też ``[hooks.state]``, przez co
  Codex przestaje uruchamiać ``.codex/hooks.json`` (guard ``00_SOURCES``) —
  zweryfikowane 2026-09-18.
- ``agy_cli`` (Antigravity CLI = Gemini) — ``agy -p {prompt} [--model M] --sandbox
  --output-format json [--json-schema plik.json] --print-timeout {N}m``. Prompt idzie
  WYŁĄCZNIE przez argv — ``-p``/``--prompt`` zawsze konsumuje następny token jako
  wartość, ``agy`` nie czyta promptu ze stdin w trybie ``--print`` (potwierdzone
  smoke testem: ``--input-format text`` na stdin zwraca błąd „took --input-format
  as its prompt”). Dlatego prompt > ``_AGY_MAX_PROMPT_BYTES`` podnosi :class:`LLMError`
  zamiast ryzykować limit długości argv systemu. Stdout to JSON z polami
  ``status`` (musi być ``"SUCCESS"``) i ``response`` (tekst odpowiedzi). Uwaga:
  ``status="SUCCESS"`` *nie* gwarantuje odpowiedzi — gdy model sięgnie po narzędzie
  (``read_file``/``command``), sandbox headless auto-odrzuca żądanie i ``agy`` zwraca
  ``response: ""`` z niepustym ``denied_actions``. Traktujemy to jako :class:`LLMError`
  z czytelnym komunikatem, a nie jako „brak JSON-a w odpowiedzi”.

Wszystkie trzy CLI zweryfikowane smoke testem (2026-09-17, konta zalogowane,
trywialny prompt ``Odpowiedz wyłącznie JSON: {"ok": true}``, sandboxy jak wyżej):
działają, mieszczą się w limicie czasu, żadne nie wymaga potwierdzenia
interaktywnego. Żadne wywołanie nie używa flag ``--dangerously*``/
``--allow-dangerously-skip-permissions`` — sandbox jest zawsze wymuszony i
nie jest tu konfigurowalny (reguły klasyfikatora z ``AGENTS.md``).

Parsowanie JSON (:func:`extract_json`) jest odporne na płoty markdown
(```` ```json ... ``` ````) i prozę wokół odpowiedzi — szuka pierwszego
zbalansowanego obiektu/tablicy JSON w tekście.

Cache decyzji: SQLite ``paths.work / "ai_cache.sqlite"`` (tabela ``ai_cache``,
klucz ``cache_key``) — trafienie pomija wywołanie backendu (``cached=True``,
``elapsed_s=0.0``). ``thresholds.yaml: llm.cache: false`` wyłącza cache całkowicie.
"""

from __future__ import annotations

import hashlib
import json as jsonlib
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from orglib import config
from orglib.db import now_iso

#: Backendy znane klientowi — inna wartość w konfiguracji/zadaniu to błąd.
KNOWN_BACKENDS: frozenset[str] = frozenset(
    {"anthropic", "openai", "claude_cli", "codex_cli", "agy_cli"}
)

#: Domyślne modele per (backend, zadanie), gdy zadanie nie podaje własnego.
#: ``codex_cli``/``agy_cli`` świadomie bez wpisu: brak ``-m``/``--model`` =
#: domyślny model konta zalogowanego w danym CLI.
_DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "anthropic": {
        "classify": "claude-haiku-4-5-20251001",
        "relate": "claude-sonnet-5",
    },
    "openai": {
        "classify": "gpt-5-mini",
        "relate": "gpt-5",
    },
    "claude_cli": {
        "classify": "haiku",
        "relate": "sonnet",
    },
}

#: Klucze skalarne sekcji ``llm`` w thresholds.yaml — reszta map to nadpisania per zadanie.
_SCALAR_KEYS: frozenset[str] = frozenset({"backend", "max_text_head_bytes", "timeout_s", "cache"})

#: Bezpieczny limit promptu przekazywanego przez argv do ``agy -p`` (nie ma stdin).
_AGY_MAX_PROMPT_BYTES = 100_000

#: Maksymalna długość ogona stderr dołączanego do komunikatu błędu.
_STDERR_TAIL_BYTES = 2048

_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    backend TEXT NOT NULL,
    model TEXT,
    prompt_sha256 TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class LLMError(Exception):
    """Błąd bazowy klienta AI (backend nieznany, CLI padło, SDK brak, itp.)."""


class LLMTimeout(LLMError):
    """Wywołanie backendu przekroczyło ``timeout_s``."""


class LLMParseError(LLMError):
    """Odpowiedź modelu nie zawiera poprawnego JSON, choć był wymagany."""


@dataclass(frozen=True)
class TaskConfig:
    """Rozwiązana konfiguracja jednego zadania (po dziedziczeniu z domyślnych)."""

    backend: str
    model: str | None
    timeout_s: int


@dataclass(frozen=True)
class LLMConfig:
    """Konfiguracja klienta AI wczytana z ``config/thresholds.yaml: llm``."""

    default_backend: str
    max_text_head_bytes: int
    timeout_s: int
    cache: bool
    task_overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def task(self, name: str) -> TaskConfig:
        """Zwraca konfigurację zadania ``name``: dziedziczy backend/model, gdy brak własnych."""
        override = self.task_overrides.get(name, {})
        env_prefix = f"PACZKA_LLM_{name.upper().replace('-', '_')}"
        env_backend = os.environ.get(f"{env_prefix}_BACKEND") or None
        env_model = os.environ.get(f"{env_prefix}_MODEL")
        backend = env_backend or str(override.get("backend") or self.default_backend)
        if env_model is not None:
            model = env_model or None
        elif env_backend is not None:
            model = _DEFAULT_MODELS.get(backend, {}).get(name)
        else:
            model = override.get("model")
        if model is None:
            model = _DEFAULT_MODELS.get(backend, {}).get(name)
        timeout_s = int(override.get("timeout_s", self.timeout_s))
        return TaskConfig(backend=backend, model=model, timeout_s=timeout_s)


@dataclass(frozen=True)
class LLMResult:
    """Wynik jednego wywołania :meth:`LLMClient.complete`."""

    text: str
    data: Any | None
    backend: str
    model: str | None
    cached: bool
    elapsed_s: float


def load_llm_config(thresholds: dict[str, Any] | None = None) -> LLMConfig:
    """Wczytuje sekcję ``llm`` z ``thresholds.yaml`` (albo z podanego słownika testowego).

    Brak sekcji ``llm`` (albo brak pliku wcale) daje sensowne domyślne: backend
    ``anthropic``, cache włączony, 300 s timeoutu, 2048 B głowy tekstu.
    """
    if thresholds is None:
        thresholds = config.load_thresholds()
    llm = thresholds.get("llm") or {}
    if not isinstance(llm, dict):
        raise ValueError("thresholds.yaml: sekcja 'llm' musi być mapą")

    task_overrides = {
        str(name): value
        for name, value in llm.items()
        if name not in _SCALAR_KEYS and isinstance(value, dict)
    }
    return LLMConfig(
        default_backend=str(llm.get("backend", "anthropic")),
        max_text_head_bytes=int(llm.get("max_text_head_bytes", 2048)),
        timeout_s=int(llm.get("timeout_s", 300)),
        cache=bool(llm.get("cache", True)),
        task_overrides=task_overrides,
    )


def truncate_head(text: str, max_bytes: int) -> str:
    """Ucina ``text`` do co najwyżej ``max_bytes`` bajtów UTF-8, bez łamania znaku."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""


def _iter_balanced_candidates(text: str) -> Iterator[str]:
    """Generuje kolejne zbalansowane podciągi ``{...}``/``[...]`` z ``text``.

    Respektuje literały stringów JSON (i ich escape'y), żeby nawiasy wewnątrz
    napisów nie psuły liczenia głębokości.
    """
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch in "{[":
            close_ch = "}" if ch == "{" else "]"
            depth = 0
            in_string = False
            escape = False
            j = i
            while j < n:
                c = text[j]
                if in_string:
                    if escape:
                        escape = False
                    elif c == "\\":
                        escape = True
                    elif c == '"':
                        in_string = False
                else:
                    if c == '"':
                        in_string = True
                    elif c == ch:
                        depth += 1
                    elif c == close_ch:
                        depth -= 1
                        if depth == 0:
                            yield text[i : j + 1]
                            break
                j += 1
        i += 1


def extract_json(text: str) -> Any:
    """Odporne wyciąganie JSON z odpowiedzi modelu (płoty markdown, proza wokół).

    Próbuje najpierw sparsować cały (przycięty) tekst, potem po kolei każdy
    zbalansowany fragment ``{...}``/``[...]``. Brak poprawnego JSON => :class:`LLMParseError`.
    """
    stripped = text.strip()
    try:
        return jsonlib.loads(stripped)
    except jsonlib.JSONDecodeError:
        pass
    for candidate in _iter_balanced_candidates(text):
        try:
            return jsonlib.loads(candidate)
        except jsonlib.JSONDecodeError:
            continue
    raise LLMParseError(f"nie znaleziono poprawnego JSON w odpowiedzi: {text[:200]!r}")


def _default_cache_key(task: str, backend: str, model: str | None, prompt: str) -> str:
    """Domyślny klucz cache: sha256(task|backend|model|sha256(prompt))."""
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    raw = f"{task}|{backend}|{model or ''}|{prompt_sha}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stderr_tail(stderr: str | None) -> str:
    """Ostatnie ``_STDERR_TAIL_BYTES`` bajtów stderr — dość, by zdiagnozować błąd CLI."""
    if not stderr:
        return ""
    encoded = stderr.encode("utf-8", errors="replace")
    return encoded[-_STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")


class LLMClient:
    """Woła skonfigurowany backend AI, cache'uje odpowiedzi po treści promptu."""

    def __init__(
        self,
        cfg: LLMConfig,
        *,
        cwd: Path | None = None,
        cache_path: Path | None = None,
        runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run,
    ) -> None:
        self.cfg = cfg
        self._cwd = Path(cwd) if cwd is not None else config.ORGANIZER_ROOT
        if cache_path is not None:
            self._cache_path: Path | None = Path(cache_path)
        elif cfg.cache:
            self._cache_path = config.load_paths().work / "ai_cache.sqlite"
        else:
            self._cache_path = None
        self._runner = runner

    # -- API publiczne ----------------------------------------------------

    def complete(
        self,
        task: str,
        prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        json: bool = False,
        cache_key: str | None = None,
    ) -> LLMResult:
        """Woła backend przypisany do ``task`` i zwraca :class:`LLMResult`.

        ``schema`` (JSON Schema) albo ``json=True`` włączają parsowanie
        odpowiedzi jako JSON (:func:`extract_json`) — porażka parsowania
        podnosi :class:`LLMParseError`. Trafienie cache pomija wywołanie
        backendu (``cached=True``, ``elapsed_s=0.0``).
        """
        task_cfg = self.cfg.task(task)
        if task_cfg.backend not in KNOWN_BACKENDS:
            raise LLMError(f"nieznany backend: {task_cfg.backend!r}")
        need_json = json or schema is not None
        key = cache_key or _default_cache_key(task, task_cfg.backend, task_cfg.model, prompt)

        use_cache = self.cfg.cache and self._cache_path is not None
        if use_cache:
            cached_text = self._cache_get(key)
            if cached_text is not None:
                data = extract_json(cached_text) if need_json else None
                return LLMResult(
                    text=cached_text,
                    data=data,
                    backend=task_cfg.backend,
                    model=task_cfg.model,
                    cached=True,
                    elapsed_s=0.0,
                )

        call = self._DISPATCH[task_cfg.backend]
        started = time.monotonic()
        text = call(self, prompt=prompt, model=task_cfg.model, timeout_s=task_cfg.timeout_s, schema=schema)
        elapsed = time.monotonic() - started

        data = extract_json(text) if need_json else None

        if use_cache:
            self._cache_set(key, task, task_cfg.backend, task_cfg.model, prompt, text)

        return LLMResult(
            text=text,
            data=data,
            backend=task_cfg.backend,
            model=task_cfg.model,
            cached=False,
            elapsed_s=elapsed,
        )

    # -- Backendy CLI (subprocess, sandbox read-only wymuszony) -----------

    def _run(
        self, argv: Sequence[str], *, input_text: str | None, timeout_s: int
    ) -> "subprocess.CompletedProcess[str]":
        """Uruchamia CLI bez powłoki; mapuje timeout/OSError na wyjątki klienta."""
        try:
            return self._runner(
                list(argv),
                cwd=str(self._cwd),
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMTimeout(f"{argv[0]}: przekroczono limit {timeout_s}s") from exc
        except OSError as exc:
            raise LLMError(f"{argv[0]}: nie udało się uruchomić ({exc})") from exc

    @staticmethod
    def _check_returncode(completed: "subprocess.CompletedProcess[str]", argv: Sequence[str]) -> None:
        if completed.returncode != 0:
            raise LLMError(
                f"{argv[0]}: exit={completed.returncode}: {_stderr_tail(completed.stderr)}"
            )

    def _call_claude_cli(
        self, *, prompt: str, model: str | None, timeout_s: int, schema: dict[str, Any] | None
    ) -> str:
        """``claude -p --permission-mode plan ...``, prompt na stdin, wynik w ``result``."""
        argv = ["claude", "-p", "--permission-mode", "plan", "--output-format", "json"]
        if model:
            argv += ["--model", model]
        completed = self._run(argv, input_text=prompt, timeout_s=timeout_s)
        self._check_returncode(completed, argv)
        try:
            payload = jsonlib.loads(completed.stdout)
        except jsonlib.JSONDecodeError as exc:
            raise LLMError(f"claude -p: nie udało się sparsować JSON ze stdout ({exc})") from exc
        result = payload.get("result")
        if not isinstance(result, str):
            raise LLMError("claude -p: odpowiedź nie ma pola tekstowego 'result'")
        return result

    def _call_codex_cli(
        self, *, prompt: str, model: str | None, timeout_s: int, schema: dict[str, Any] | None
    ) -> str:
        """``codex exec -c model_provider="openai" -s read-only ...``; wynik z ``-o``."""
        with tempfile.TemporaryDirectory(prefix="llm_client_codex_") as tmp_dir:
            out_path = Path(tmp_dir) / "out.txt"
            argv = [
                "codex",
                "exec",
                "-c",
                'model_provider="openai"',
                "-s",
                "read-only",
                "--ephemeral",
                "--skip-git-repo-check",
                "-C",
                str(self._cwd),
            ]
            if model:
                argv += ["-m", model]
            if schema is not None:
                schema_path = Path(tmp_dir) / "schema.json"
                schema_path.write_text(jsonlib.dumps(schema), encoding="utf-8")
                argv += ["--output-schema", str(schema_path)]
            argv += ["-o", str(out_path), "-"]

            completed = self._run(argv, input_text=prompt, timeout_s=timeout_s)
            self._check_returncode(completed, argv)
            if not out_path.exists():
                raise LLMError("codex exec: brak pliku wyjściowego (-o) — sesja nic nie zapisała")
            return out_path.read_text(encoding="utf-8")

    def _call_agy_cli(
        self, *, prompt: str, model: str | None, timeout_s: int, schema: dict[str, Any] | None
    ) -> str:
        """``agy -p {prompt} --sandbox --output-format json ...``; wynik w polu ``response``.

        Prompt idzie WYŁĄCZNIE przez argv (``-p`` nie czyta stdin w print mode) —
        patrz docstring modułu.
        """
        prompt_bytes = len(prompt.encode("utf-8"))
        if prompt_bytes > _AGY_MAX_PROMPT_BYTES:
            raise LLMError(
                f"agy -p: prompt ({prompt_bytes} B) przekracza bezpieczny limit argv "
                f"({_AGY_MAX_PROMPT_BYTES} B) — agy przyjmuje prompt tylko przez argv, nie stdin"
            )
        with tempfile.TemporaryDirectory(prefix="llm_client_agy_") as tmp_dir:
            argv = ["agy", "-p", prompt, "--sandbox", "--output-format", "json"]
            if model:
                argv += ["--model", model]
            if schema is not None:
                schema_path = Path(tmp_dir) / "schema.json"
                schema_path.write_text(jsonlib.dumps(schema), encoding="utf-8")
                argv += ["--json-schema", str(schema_path)]
            minutes = max(1, -(-timeout_s // 60))  # sufit w minutach
            argv += ["--print-timeout", f"{minutes}m"]

            completed = self._run(argv, input_text=None, timeout_s=timeout_s)
            self._check_returncode(completed, argv)
            try:
                payload = jsonlib.loads(completed.stdout)
            except jsonlib.JSONDecodeError as exc:
                raise LLMError(f"agy -p: nie udało się sparsować JSON ze stdout ({exc})") from exc
            status = payload.get("status")
            if status != "SUCCESS":
                raise LLMError(f"agy -p: status={status!r} (odpowiedź: {completed.stdout[:500]!r})")
            response = payload.get("response")
            if not isinstance(response, str):
                raise LLMError("agy -p: odpowiedź nie ma pola tekstowego 'response'")
            if not response.strip():
                # status=SUCCESS + pusty response = model sięgnął po narzędzie,
                # a sandbox headless odrzucił żądanie (nie ma jak zapytać użytkownika).
                denied = payload.get("denied_actions") or []
                names = ", ".join(
                    str(item.get("action")) for item in denied if isinstance(item, Mapping)
                )
                hint = (
                    f" — sandbox odrzucił narzędzia: {names}; wklej potrzebną treść"
                    " do promptu zamiast liczyć na to, że model sam przeczyta pliki"
                    if names
                    else ""
                )
                raise LLMError(f"agy -p: pusta odpowiedź mimo status=SUCCESS{hint}")
            return response

    # -- Backendy API (SDK importowane leniwie) ----------------------------

    def _call_anthropic(
        self, *, prompt: str, model: str | None, timeout_s: int, schema: dict[str, Any] | None
    ) -> str:
        """Messages API (jeden user message, ``max_tokens=4096``)."""
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError(
                "backend 'anthropic' wymaga pakietu: pip install anthropic"
            ) from exc
        client = anthropic.Anthropic(timeout=timeout_s)
        kwargs: dict[str, Any] = {}
        if schema is not None:
            kwargs["system"] = (
                "Odpowiadaj WYŁĄCZNIE poprawnym JSON-em zgodnym z podanym schematem, "
                f"bez żadnego innego tekstu. Schemat: {jsonlib.dumps(schema)}"
            )
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

    def _call_openai(
        self, *, prompt: str, model: str | None, timeout_s: int, schema: dict[str, Any] | None
    ) -> str:
        """Chat Completions API (jeden user message, ``max_tokens=4096``)."""
        try:
            import openai
        except ImportError as exc:
            raise LLMError("backend 'openai' wymaga pakietu: pip install openai") from exc
        client = openai.OpenAI(timeout=timeout_s)
        messages: list[dict[str, str]] = []
        if schema is not None:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Odpowiadaj WYŁĄCZNIE poprawnym JSON-em zgodnym z podanym schematem, "
                        f"bez żadnego innego tekstu. Schemat: {jsonlib.dumps(schema)}"
                    ),
                }
            )
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(model=model, max_tokens=4096, messages=messages)
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise LLMError("openai: odpowiedź bez treści tekstowej")
        return content

    _DISPATCH: dict[str, Callable[..., str]] = {
        "anthropic": _call_anthropic,
        "openai": _call_openai,
        "claude_cli": _call_claude_cli,
        "codex_cli": _call_codex_cli,
        "agy_cli": _call_agy_cli,
    }

    # -- Cache (SQLite, paths.work / "ai_cache.sqlite") --------------------

    def _cache_connect(self) -> Any:
        import sqlite3

        assert self._cache_path is not None
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._cache_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_CACHE_SCHEMA)
        return conn

    def _cache_get(self, cache_key: str) -> str | None:
        conn = self._cache_connect()
        try:
            row = conn.execute(
                "SELECT response FROM ai_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row is not None else None

    def _cache_set(
        self,
        cache_key: str,
        task: str,
        backend: str,
        model: str | None,
        prompt: str,
        response: str,
    ) -> None:
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        conn = self._cache_connect()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO ai_cache "
                    "(cache_key, task, backend, model, prompt_sha256, response, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cache_key, task, backend, model, prompt_sha, response, now_iso()),
                )
        finally:
            conn.close()
