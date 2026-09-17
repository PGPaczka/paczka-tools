from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]
CODEX_DIR = REPO_ROOT / ".codex"

EXPECTED_AGENTS = {
    "documentation_engineer": ("workspace-write", "medium"),
    "explorer": ("read-only", "medium"),
    "python_pro": ("workspace-write", "high"),
    "readme_generator": ("workspace-write", "medium"),
    "reviewer": ("read-only", "high"),
    "runner": ("workspace-write", "medium"),
    "sql_pro": ("workspace-write", "high"),
    "test_automator": ("workspace-write", "high"),
}


def load_toml(path: Path) -> dict:
    with path.open("rb") as file:
        return tomllib.load(file)


def test_codex_subagent_defaults_are_centralized() -> None:
    config = load_toml(CODEX_DIR / "config.toml")

    assert config["agents"] == {
        "enabled": True,
        "max_concurrent_threads_per_session": 6,
        "default_subagent_model": "gpt-6-astra",
        "default_subagent_reasoning_effort": "medium",
    }


def test_codex_agent_roles_have_safe_explicit_policies() -> None:
    agent_files = sorted((CODEX_DIR / "agents").glob("*.toml"))
    agents = {load_toml(path)["name"]: load_toml(path) for path in agent_files}

    assert set(agents) == set(EXPECTED_AGENTS)
    for name, (sandbox_mode, reasoning_effort) in EXPECTED_AGENTS.items():
        agent = agents[name]
        assert agent["description"].strip()
        assert agent["developer_instructions"].strip()
        assert agent["sandbox_mode"] == sandbox_mode
        assert agent["model_reasoning_effort"] == reasoning_effort
        assert "model" not in agent
        assert "AGENTS.md" in agent["developer_instructions"]
        assert "00_SOURCES" in agent["developer_instructions"]


def test_codex_read_only_roles_cannot_edit_workspace() -> None:
    for name in ("explorer", "reviewer"):
        agent = load_toml(CODEX_DIR / "agents" / f"{name}.toml")
        assert agent["sandbox_mode"] == "read-only"
