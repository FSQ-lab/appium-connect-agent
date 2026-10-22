"""Bounded project input policy over the approved public npm-semver API."""

from dataclasses import dataclass

import nodesemver


@dataclass(frozen=True)
class Version:
    text: str
    major: int


def version(value: object) -> Version | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or not value.isascii()
        or value.startswith(("v", "="))
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        return None
    parsed = nodesemver.valid(value, loose=False)
    return Version(value, parsed.major) if parsed is not None else None


def constraint(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 256:
        return None
    normalized = " ".join(value.split())
    if (
        not normalized
        or not normalized.isascii()
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
        or any(not branch.strip() for branch in normalized.split("||"))
    ):
        return None
    if nodesemver.valid_range(normalized, loose=False) is None:
        return None
    return normalized


def satisfies(actual: object, expression: object) -> bool | None:
    observed = version(actual)
    declared = constraint(expression)
    if observed is None or declared is None:
        return None
    return nodesemver.Range(declared, loose=False).test(observed.text)
