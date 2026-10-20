"""Partial npm comparison: unsupported syntax deliberately stays unknown."""

import re

Version = tuple[int, int, int]
_VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"


def version(value: object) -> Version | None:
    if not isinstance(value, str) or len(value) > 128:
        return None
    match = re.fullmatch(_VERSION, value)
    if match is None:
        return None
    a, b, c = map(int, match.groups())
    return a, b, c


def satisfies(actual: str, expression: str) -> bool | None:
    parsed = version(actual)
    if parsed is None or not expression or len(expression) > 256:
        return None
    branches: list[bool | None] = []
    for branch in expression.split("||"):
        comparisons: list[bool] = []
        tokens = branch.strip().split()
        for token in tokens:
            match = re.fullmatch(r"(\^|~|>=|<=|>|<|=)?" + _VERSION, token)
            if match is None:
                branches.append(None)
                break
            operator = match[1] or "="
            a, b, c = map(int, match.groups()[1:])
            minimum = (a, b, c)
            if operator == "^":
                maximum = (
                    (a + 1, 0, 0) if a else ((0, b + 1, 0) if b else (0, 0, c + 1))
                )
                result = minimum <= parsed < maximum
            elif operator == "~":
                result = minimum <= parsed < (a, b + 1, 0)
            else:
                result = {
                    "=": parsed == minimum,
                    ">=": parsed >= minimum,
                    "<=": parsed <= minimum,
                    ">": parsed > minimum,
                    "<": parsed < minimum,
                }[operator]
            comparisons.append(result)
        else:
            branches.append(all(comparisons) if tokens else None)
    if any(result is True for result in branches):
        return True
    return None if None in branches else False
