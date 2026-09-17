"""Walidacja rzeczywistych skilli i regresje dla metadanych Claude."""

from pathlib import Path

import pytest

from agent import validate_skills


def make_skill(tmp_path: Path, fields: str = "", body: str = "Instrukcje.") -> Path:
    directory = tmp_path / "example"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: example\ndescription: Opis procedury.\n"
        f"{fields}---\n{body}\n",
        encoding="utf-8",
    )
    return directory


def test_project_skills_and_shared_symlinks() -> None:
    assert validate_skills.main() == 0


def test_claude_fields_are_valid_and_preserved(tmp_path: Path) -> None:
    directory = make_skill(
        tmp_path,
        'disable-model-invocation: true\nargument-hint: "SKROT SEMESTR"\n'
        "arguments: [skrot, semestr]\ncontext: fork\nagent: general-purpose\n"
        "model: haiku\nallowed-tools: Read, Write(reports/**)\n",
    )
    before = (directory / "SKILL.md").read_bytes()

    metadata = validate_skills.validate_skill(directory)

    assert metadata["disable-model-invocation"] is True
    assert metadata["argument-hint"] == "SKROT SEMESTR"
    assert metadata["arguments"] == ["skrot", "semestr"]
    assert (directory / "SKILL.md").read_bytes() == before


@pytest.mark.parametrize("fields", [
    "disable-model-invocations: true\n",  # literówka, nie nowy dozwolony klucz
    'disable-model-invocation: "true"\n',  # string zamiast boolean
    "disable-model-invocation: 1\n",  # projekt wymaga jawnego boolean
    "argument-hint: [SKROT]\n",
    "arguments: [skrot, 3]\n",
    "context: unknown\n",
    "model: null\n",
    "metadata: []\n",
    "broken: [\n",
    "name: other\n",  # powtórzony klucz
    "disable-model-invocation: true\ndisable-model-invocation: false\n",
])
def test_invalid_metadata_is_rejected(tmp_path: Path, fields: str) -> None:
    with pytest.raises(ValueError):
        validate_skills.validate_skill(make_skill(tmp_path, fields))


@pytest.mark.parametrize("content", [
    "Instrukcje bez nagłówka.",
    "---\nname: example\ndescription: test\n",  # brak zamknięcia YAML
    "---\nname: example\n---\nInstrukcje.",  # brak description
    "---\nname: other\ndescription: test\n---\nInstrukcje.",
    "---\nname: example\ndescription: ''\n---\nInstrukcje.",
    "---\n- example\n---\nInstrukcje.",  # lista zamiast mapy
])
def test_invalid_frontmatter_is_rejected(tmp_path: Path, content: str) -> None:
    directory = make_skill(tmp_path)
    (directory / "SKILL.md").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        validate_skills.validate_skill(directory)


def test_missing_file_and_empty_body_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_skills.validate_skill(tmp_path / "missing")
    with pytest.raises(ValueError):
        validate_skills.validate_skill(make_skill(tmp_path, body=""))


def test_cli_reports_missing_skills(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(validate_skills, "SKILLS", tmp_path)
    assert validate_skills.main() == 1
    assert "brak skilli" in capsys.readouterr().out


def test_cli_reports_broken_shared_symlink(tmp_path: Path, monkeypatch, capsys) -> None:
    directory = make_skill(tmp_path)
    directory.rename(tmp_path / "organizer-example")
    monkeypatch.setattr(validate_skills, "SKILLS", tmp_path)
    monkeypatch.setattr(validate_skills, "ORGANIZER", tmp_path)
    skill = tmp_path / "organizer-example" / "SKILL.md"
    skill.write_text(skill.read_text().replace("name: example", "name: organizer-example"))

    assert validate_skills.main() == 1
    assert "symlinku" in capsys.readouterr().out


@pytest.mark.parametrize("policy", [
    "policy:\n  allow_implicit_invocation: false\n",
    'policy:\n  allow_implicit_invocation: "true"\n',
    "policy:\n  allow_implicit_invocation: 1\n",
    "policy:\n  allow_implicit_invocations: true\n",
    "policy: {}\n",
    "policy: [\n",
    "policy:\n  allow_implicit_invocation: true\n  allow_implicit_invocation: false\n",
])
def test_invalid_codex_invocation_policy(tmp_path: Path, policy: str) -> None:
    directory = make_skill(tmp_path, "disable-model-invocation: false\n")
    (directory / "agents").mkdir()
    (directory / "agents" / "openai.yaml").write_text(policy)
    metadata = validate_skills.validate_skill(directory)
    with pytest.raises(ValueError, match="Codex"):
        validate_skills.validate_invocation_policy(directory, metadata)


def test_missing_codex_policy_is_rejected(tmp_path: Path) -> None:
    directory = make_skill(tmp_path, "disable-model-invocation: false\n")
    with pytest.raises(ValueError, match="Codex"):
        validate_skills.validate_invocation_policy(
            directory, validate_skills.validate_skill(directory)
        )


@pytest.mark.parametrize("fields", ["", "disable-model-invocation: true\n"])
def test_claude_policy_must_explicitly_allow_automatic_selection(
    tmp_path: Path, fields: str
) -> None:
    directory = make_skill(tmp_path, fields)
    with pytest.raises(ValueError, match="Claude"):
        validate_skills.validate_invocation_policy(
            directory, validate_skills.validate_skill(directory)
        )
