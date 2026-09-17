#!/usr/bin/env python3
"""Walidacja metadanych współdzielonych skilli projektu, z rozszerzeniami Claude."""

from __future__ import annotations

import re
from pathlib import Path

import jsonschema
import yaml


ORGANIZER = Path(__file__).resolve().parents[2]
SKILLS = ORGANIZER / ".claude" / "skills"
TEXT = {"type": "string", "minLength": 1, "pattern": r"\S"}
TEXT_OR_LIST = {
    "anyOf": [TEXT, {"type": "array", "items": TEXT, "minItems": 1}]
}
# Kontrakt projektu, nie pełny schemat wszystkich hostów ani walidator ich runtime.
SCHEMA = {
    "type": "object",
    "required": ["name", "description"],
    "additionalProperties": False,
    "properties": {
        "name": {
            "type": "string",
            "maxLength": 64,
            "pattern": r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        },
        "description": {**TEXT, "maxLength": 1024},
        "license": TEXT,
        "compatibility": TEXT,
        "metadata": {"type": "object"},
        "allowed-tools": TEXT_OR_LIST,
        "argument-hint": TEXT,
        "arguments": TEXT_OR_LIST,
        "disable-model-invocation": {"type": "boolean"},
        "user-invocable": {"type": "boolean"},
        "context": {"const": "fork"},
        "agent": TEXT,
        "model": TEXT,
    },
}


class UniqueKeyLoader(yaml.SafeLoader):
    """Nie pozwala, by drugi wpis YAML po cichu nadpisał pierwszy."""

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        if len(mapping) != len(node.value):
            raise yaml.constructor.ConstructorError(
                None, None, "Powtórzony klucz YAML", node.start_mark
            )
        return mapping


def validate_skill(directory: Path) -> dict:
    """Zwraca metadane; błędy pliku lub kontraktu zgłasza jako ValueError."""
    try:
        content = (directory / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", content, re.DOTALL)
        if not match:
            raise ValueError("Brak poprawnego nagłówka YAML między liniami ---")
        metadata = yaml.load(match.group(1), Loader=UniqueKeyLoader)
        jsonschema.validate(metadata, SCHEMA)
        if metadata["name"] != directory.name:
            raise ValueError("Pole name musi odpowiadać nazwie katalogu")
        if not content[match.end():].strip():
            raise ValueError("Brak instrukcji skillu pod nagłówkiem YAML")
        return metadata
    except (OSError, UnicodeError, yaml.YAMLError, jsonschema.ValidationError) as exc:
        raise ValueError(str(exc)) from exc


def validate_invocation_policy(directory: Path, metadata: dict) -> None:
    """Projekt wymaga jawnie włączonego automatycznego doboru w obu hostach."""
    if metadata.get("disable-model-invocation") is not False:
        raise ValueError("Claude: wymagane disable-model-invocation: false")
    try:
        content = (directory / "agents" / "openai.yaml").read_text(encoding="utf-8")
        settings = yaml.load(content, Loader=UniqueKeyLoader)
        jsonschema.validate(settings, {
            "type": "object",
            "required": ["policy"],
            "properties": {
                "policy": {
                    "type": "object",
                    "required": ["allow_implicit_invocation"],
                    "properties": {
                        "allow_implicit_invocation": {"type": "boolean", "const": True}
                    },
                }
            },
        })
    except (OSError, UnicodeError, yaml.YAMLError, jsonschema.ValidationError) as exc:
        raise ValueError(f"Codex: niepoprawne agents/openai.yaml: {exc}") from exc


def main() -> int:
    directories = sorted(SKILLS.glob("organizer-*"))
    if not directories:
        print(f"BŁĄD: brak skilli w {SKILLS}")
        return 1
    failed = False
    for directory in directories:
        try:
            metadata = validate_skill(directory)
            alias = ORGANIZER / ".agents" / "skills" / directory.name
            if not alias.is_symlink() or alias.resolve() != directory.resolve():
                raise ValueError("Brak poprawnego symlinku w .agents/skills")
            validate_invocation_policy(directory, metadata)
        except ValueError as exc:
            print(f"BŁĄD {directory.name}: {exc}")
            failed = True
        else:
            print(f"OK   {directory.name}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
