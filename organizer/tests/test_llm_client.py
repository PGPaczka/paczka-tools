"""Testy klienta AI: konfiguracja, dyspozycja backendów, cache, parsowanie JSON.

Bez sieci — wszystkie CLI są mockowane przez ``runner`` (odpowiednik
``subprocess.run``). Cache zawsze w ``tmp_path``, nigdy w prawdziwym ``20_WORK``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from orglib.llm_client import (
    LLMClient,
    LLMConfig,
    LLMError,
    LLMParseError,
    LLMResult,
    LLMTimeout,
    TaskConfig,
    extract_json,
    load_llm_config,
    truncate_head,
)


def _cfg(
    *,
    default_backend: str = "claude_cli",
    cache: bool = True,
    timeout_s: int = 30,
    task_overrides: dict[str, dict[str, Any]] | None = None,
    max_text_head_bytes: int = 2048,
) -> LLMConfig:
    return LLMConfig(
        default_backend=default_backend,
        max_text_head_bytes=max_text_head_bytes,
        timeout_s=timeout_s,
        cache=cache,
        task_overrides=task_overrides or {},
    )


class RecordingRunner:
    """Fałszywy ``subprocess.run``: zapamiętuje wywołania, zwraca zaprogramowany wynik.

    Dla ``codex`` odtwarza rzeczywiste zachowanie CLI: zapisuje odpowiedź do
    pliku wskazanego przez ``-o`` zamiast pisać ją na stdout.
    """

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        codex_out_content: str | None = None,
        raise_timeout: bool = False,
        raise_os_error: bool = False,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.codex_out_content = codex_out_content
        self.raise_timeout = raise_timeout
        self.raise_os_error = raise_os_error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), **kwargs})
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))
        if self.raise_os_error:
            raise FileNotFoundError(f"nie znaleziono: {argv[0]}")
        if self.codex_out_content is not None and "-o" in argv:
            out_path = Path(argv[argv.index("-o") + 1])
            out_path.write_text(self.codex_out_content, encoding="utf-8")
        return subprocess.CompletedProcess(
            args=list(argv), returncode=self.returncode, stdout=self.stdout, stderr=self.stderr
        )


# -- load_llm_config -----------------------------------------------------


def test_load_llm_config_missing_section_has_sane_defaults() -> None:
    cfg = load_llm_config({})

    assert cfg.default_backend == "anthropic"
    assert cfg.cache is True
    assert cfg.timeout_s == 300
    assert cfg.max_text_head_bytes == 2048
    task = cfg.task("classify")
    assert task.backend == "anthropic"
    assert task.model == "claude-haiku-4-5-20251001"


def test_load_llm_config_task_inherits_default_backend_and_model() -> None:
    cfg = load_llm_config({"llm": {"backend": "claude_cli"}})

    task = cfg.task("classify")
    assert task.backend == "claude_cli"
    assert task.model == "haiku"
    assert task.timeout_s == cfg.timeout_s


def test_load_llm_config_task_own_backend_and_explicit_model() -> None:
    cfg = load_llm_config(
        {
            "llm": {
                "backend": "agy_cli",
                "classify": {"backend": "agy_cli", "model": "gemini-3.8-flash-medium"},
                "relate": {"backend": "claude_cli", "model": "sonnet"},
            }
        }
    )

    classify = cfg.task("classify")
    assert classify.backend == "agy_cli"
    assert classify.model == "gemini-3.8-flash-medium"

    relate = cfg.task("relate")
    assert relate.backend == "claude_cli"
    assert relate.model == "sonnet"


def test_load_llm_config_codex_and_agy_have_no_default_model() -> None:
    cfg = load_llm_config({"llm": {"backend": "codex_cli"}})

    assert cfg.task("classify").model is None
    assert cfg.task("relate").model is None


def test_task_environment_override_switches_backend_and_model(monkeypatch) -> None:
    cfg = load_llm_config(
        {"llm": {"backend": "agy_cli", "relate": {"backend": "claude_cli", "model": "sonnet"}}}
    )
    monkeypatch.setenv("PACZKA_LLM_RELATE_BACKEND", "codex_cli")
    monkeypatch.setenv("PACZKA_LLM_RELATE_MODEL", "gpt-test")

    task = cfg.task("relate")

    assert task.backend == "codex_cli"
    assert task.model == "gpt-test"


def test_task_environment_backend_override_drops_old_provider_model(monkeypatch) -> None:
    cfg = load_llm_config(
        {"llm": {"backend": "agy_cli", "relate": {"backend": "claude_cli", "model": "sonnet"}}}
    )
    monkeypatch.setenv("PACZKA_LLM_RELATE_BACKEND", "codex_cli")

    task = cfg.task("relate")

    assert task.backend == "codex_cli"
    assert task.model is None


def test_load_llm_config_reads_scalars() -> None:
    cfg = load_llm_config(
        {"llm": {"backend": "openai", "max_text_head_bytes": 512, "timeout_s": 60, "cache": False}}
    )

    assert cfg.max_text_head_bytes == 512
    assert cfg.timeout_s == 60
    assert cfg.cache is False
    assert cfg.task("relate").model == "gpt-5"


# -- truncate_head ---------------------------------------------------------


def test_truncate_head_keeps_short_text() -> None:
    assert truncate_head("abc", 10) == "abc"


def test_truncate_head_does_not_split_multibyte_char() -> None:
    text = "a" * 9 + "ę"  # 'ę' to 2 bajty UTF-8
    truncated = truncate_head(text, 10)

    assert truncated.encode("utf-8") == b"a" * 9
    assert len(truncated.encode("utf-8")) <= 10


def test_truncate_head_exact_boundary_keeps_whole_char() -> None:
    text = "ą" * 5  # każdy znak to 2 bajty
    truncated = truncate_head(text, 6)

    assert truncated == "ąąą"


# -- extract_json ------------------------------------------------------------


def test_extract_json_plain() -> None:
    assert extract_json('{"ok": true}') == {"ok": True}


def test_extract_json_with_markdown_fence() -> None:
    text = '```json\n{"ok": true, "n": 1}\n```'
    assert extract_json(text) == {"ok": True, "n": 1}


def test_extract_json_with_surrounding_prose() -> None:
    text = 'Oto odpowiedź:\n{"a": [1, 2, {"b": "c}d"}]}\ni to wszystko.'
    assert extract_json(text) == {"a": [1, 2, {"b": "c}d"}]}


def test_extract_json_array() -> None:
    assert extract_json("wynik: [1, 2, 3] koniec") == [1, 2, 3]


def test_extract_json_raises_when_no_json() -> None:
    with pytest.raises(LLMParseError):
        extract_json("to nie jest json, tylko proza")


# -- LLMClient.complete: dyspozycja i błędy ----------------------------------


def test_complete_unknown_backend_raises() -> None:
    cfg = _cfg(default_backend="carrier_pigeon", cache=False)
    client = LLMClient(cfg, cwd=Path("/tmp"), cache_path=None, runner=RecordingRunner())

    with pytest.raises(LLMError):
        client.complete("classify", "prompt")


def test_complete_timeout_raises_llm_timeout(tmp_path: Path) -> None:
    runner = RecordingRunner(raise_timeout=True)
    cfg = _cfg(default_backend="claude_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    with pytest.raises(LLMTimeout):
        client.complete("classify", "prompt")


def test_complete_backend_binary_missing_raises_llm_error(tmp_path: Path) -> None:
    runner = RecordingRunner(raise_os_error=True)
    cfg = _cfg(default_backend="claude_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    with pytest.raises(LLMError):
        client.complete("classify", "prompt")


def test_complete_nonzero_exit_raises_with_stderr_tail(tmp_path: Path) -> None:
    runner = RecordingRunner(returncode=1, stderr="boom: nie zalogowano")
    cfg = _cfg(default_backend="claude_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    with pytest.raises(LLMError, match="nie zalogowano"):
        client.complete("classify", "prompt")


# -- claude_cli ---------------------------------------------------------------


def test_claude_cli_prompt_via_stdin_and_parses_result_field(tmp_path: Path) -> None:
    payload = json.dumps({"result": '```json\n{"ok": true}\n```'})
    runner = RecordingRunner(stdout=payload)
    cfg = _cfg(default_backend="claude_cli", cache=False, task_overrides={"classify": {"model": "haiku"}})
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    result = client.complete("classify", "Odpowiedz JSON", json=True)

    assert isinstance(result, LLMResult)
    assert result.data == {"ok": True}
    assert result.backend == "claude_cli"
    assert result.model == "haiku"
    assert result.cached is False

    [call] = runner.calls
    assert call["argv"][:5] == [
        "claude",
        "-p",
        "--permission-mode",
        "plan",
        "--output-format",
    ]
    assert "--model" in call["argv"] and "haiku" in call["argv"]
    assert call["input"] == "Odpowiedz JSON"
    assert not any(flag.startswith("--dangerously") for flag in call["argv"])


def test_claude_cli_missing_result_field_raises(tmp_path: Path) -> None:
    runner = RecordingRunner(stdout=json.dumps({"nope": 1}))
    cfg = _cfg(default_backend="claude_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    with pytest.raises(LLMError):
        client.complete("classify", "prompt")


# -- codex_cli ------------------------------------------------------------


def test_codex_cli_sandbox_flags_stdin_prompt_and_reads_output_file(tmp_path: Path) -> None:
    runner = RecordingRunner(codex_out_content='{"ok": true}')
    cfg = _cfg(default_backend="codex_cli", cache=False, task_overrides={"classify": {"model": "gpt-mini"}})
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    result = client.complete("classify", "Odpowiedz JSON", json=True)

    assert result.data == {"ok": True}
    [call] = runner.calls
    argv = call["argv"]
    assert argv[:3] == ["codex", "--ignore-user-config", "exec"]
    assert "-s" in argv and argv[argv.index("-s") + 1] == "read-only"
    assert "--ephemeral" in argv
    assert "--skip-git-repo-check" in argv
    assert "-C" in argv and argv[argv.index("-C") + 1] == str(tmp_path)
    assert "-m" in argv and argv[argv.index("-m") + 1] == "gpt-mini"
    assert argv[-1] == "-"  # prompt przez stdin
    assert call["input"] == "Odpowiedz JSON"
    assert not any(flag.startswith("--dangerously") for flag in argv)


def test_codex_cli_missing_output_file_raises(tmp_path: Path) -> None:
    runner = RecordingRunner(codex_out_content=None)  # nic nie zapisze do -o
    cfg = _cfg(default_backend="codex_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    with pytest.raises(LLMError):
        client.complete("classify", "prompt")


def test_codex_cli_writes_schema_file(tmp_path: Path) -> None:
    seen_schema_path: dict[str, Path] = {}

    def runner(argv, **kwargs):
        if "--output-schema" in argv:
            seen_schema_path["path"] = Path(argv[argv.index("--output-schema") + 1])
            assert seen_schema_path["path"].exists()
            assert json.loads(seen_schema_path["path"].read_text(encoding="utf-8")) == {
                "type": "object"
            }
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text('{"ok": true}', encoding="utf-8")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    cfg = _cfg(default_backend="codex_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    client.complete("classify", "prompt", schema={"type": "object"})

    assert "path" in seen_schema_path
    assert not seen_schema_path["path"].exists()  # tmpdir posprzątany po wywołaniu


# -- agy_cli ----------------------------------------------------------------


def test_agy_cli_sandbox_flags_prompt_via_argv_and_parses_response(tmp_path: Path) -> None:
    payload = json.dumps({"status": "SUCCESS", "response": '{"ok": true}'})
    runner = RecordingRunner(stdout=payload)
    cfg = _cfg(default_backend="agy_cli", cache=False, task_overrides={"classify": {"model": "gemini-3.8-flash-medium"}})
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    result = client.complete("classify", "Odpowiedz JSON", json=True)

    assert result.data == {"ok": True}
    [call] = runner.calls
    argv = call["argv"]
    assert argv[0] == "agy"
    assert argv[1] == "-p" and argv[2] == "Odpowiedz JSON"  # prompt przez argv, nie stdin
    assert call["input"] is None
    assert "--sandbox" in argv
    assert "--model" in argv and "gemini-3.8-flash-medium" in argv
    assert "--print-timeout" in argv
    assert not any(flag.startswith("--dangerously") for flag in argv)


def test_agy_cli_status_failure_raises(tmp_path: Path) -> None:
    payload = json.dumps({"status": "ERROR", "response": None})
    runner = RecordingRunner(stdout=payload)
    cfg = _cfg(default_backend="agy_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    with pytest.raises(LLMError):
        client.complete("classify", "prompt")


def test_agy_cli_prompt_too_large_for_argv_raises_without_calling_runner(tmp_path: Path) -> None:
    runner = RecordingRunner()
    cfg = _cfg(default_backend="agy_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=None, runner=runner)

    huge_prompt = "x" * 200_000
    with pytest.raises(LLMError):
        client.complete("classify", huge_prompt)
    assert runner.calls == []


# -- cache ----------------------------------------------------------------


def test_cache_hit_skips_runner(tmp_path: Path) -> None:
    cache_path = tmp_path / "ai_cache.sqlite"
    runner = RecordingRunner(stdout=json.dumps({"result": '{"n": 1}'}))
    cfg = _cfg(default_backend="claude_cli", cache=True)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=cache_path, runner=runner)

    first = client.complete("classify", "prompt", json=True)
    assert first.cached is False
    assert len(runner.calls) == 1

    second = client.complete("classify", "prompt", json=True)
    assert second.cached is True
    assert second.data == {"n": 1}
    assert second.elapsed_s == 0.0
    assert len(runner.calls) == 1  # runner nie wołany drugi raz


def test_cache_disabled_always_calls_runner(tmp_path: Path) -> None:
    cache_path = tmp_path / "ai_cache.sqlite"
    runner = RecordingRunner(stdout=json.dumps({"result": '{"n": 1}'}))
    cfg = _cfg(default_backend="claude_cli", cache=False)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=cache_path, runner=runner)

    client.complete("classify", "prompt", json=True)
    client.complete("classify", "prompt", json=True)

    assert len(runner.calls) == 2
    assert not cache_path.exists()


def test_cache_custom_cache_key_is_used(tmp_path: Path) -> None:
    cache_path = tmp_path / "ai_cache.sqlite"
    runner = RecordingRunner(stdout=json.dumps({"result": '{"n": 1}'}))
    cfg = _cfg(default_backend="claude_cli", cache=True)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=cache_path, runner=runner)

    client.complete("classify", "prompt A", json=True, cache_key="fixed-key")
    # Inny prompt, ten sam jawny cache_key => trafienie cache, runner nie wołany ponownie.
    second = client.complete("classify", "prompt B", json=True, cache_key="fixed-key")

    assert second.cached is True
    assert len(runner.calls) == 1


def test_cache_different_prompts_get_different_default_keys(tmp_path: Path) -> None:
    cache_path = tmp_path / "ai_cache.sqlite"
    runner = RecordingRunner(stdout=json.dumps({"result": '{"n": 1}'}))
    cfg = _cfg(default_backend="claude_cli", cache=True)
    client = LLMClient(cfg, cwd=tmp_path, cache_path=cache_path, runner=runner)

    client.complete("classify", "prompt A", json=True)
    client.complete("classify", "prompt B", json=True)

    assert len(runner.calls) == 2


# -- LLMConfig.task / TaskConfig ---------------------------------------------


def test_task_config_is_a_plain_dataclass() -> None:
    task = TaskConfig(backend="claude_cli", model="haiku", timeout_s=30)
    assert (task.backend, task.model, task.timeout_s) == ("claude_cli", "haiku", 30)
