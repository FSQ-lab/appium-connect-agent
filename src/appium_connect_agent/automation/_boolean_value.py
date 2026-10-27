"""Narrow shared normalization for Android boolean attribute values."""


def _parse_boolean_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in {"true", "false"}:
            return normalized == "true"
    raise ValueError("invalid boolean attribute value")
