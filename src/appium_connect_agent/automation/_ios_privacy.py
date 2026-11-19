"""iOS public-call error sanitization before and after the Session gate."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

from ._models import AutomationError

_P = ParamSpec("_P")
_Result = TypeVar("_Result")


def _redact_ios_public_errors(
    method: Callable[_P, _Result],
) -> Callable[_P, _Result]:
    """Redact controlled iOS failures, including pre-gate validation causes."""

    @wraps(method)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _Result:
        try:
            return method(*args, **kwargs)
        except AutomationError as error:
            instance = args[0] if args else None
            owner = getattr(instance, "_owner", None)
            if getattr(owner, "platform", None) in ("ios", "macos"):
                from ._session import _redact_xcuitest_error

                _redact_xcuitest_error(error)
                raise error from None
            raise

    return cast(Callable[_P, _Result], wrapped)


_Instance = TypeVar("_Instance")


def _redact_ios_public_methods(cls: type[_Instance]) -> type[_Instance]:
    """Wrap public methods at runtime without changing their static signatures."""
    for name, value in vars(cls).items():
        if not name.startswith("_") and callable(value):
            method = cast(Callable[..., object], value)
            setattr(cls, name, _redact_ios_public_errors(method))
    return cls
