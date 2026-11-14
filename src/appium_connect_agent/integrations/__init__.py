"""MCP, in-process ToolCall, and CLI surfaces over one Integrations application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._catalog import (
    TOOL_CATALOG,
    JsonValue,
    SchemaProjectionError,
    ToolAnnotations,
    ToolCatalog,
    ToolSpec,
)
from ._toolcall import (
    ToolBindingExport,
    ToolCallLike,
    ToolInputFailureLike,
)

if TYPE_CHECKING:
    from ._application import Application, ApplicationError
    from ._toolcall import SyncApplication

__all__ = [
    "TOOL_CATALOG",
    "Application",
    "ApplicationError",
    "JsonValue",
    "SchemaProjectionError",
    "SyncApplication",
    "ToolAnnotations",
    "ToolBindingExport",
    "ToolCallLike",
    "ToolCatalog",
    "ToolInputFailureLike",
    "ToolSpec",
]


def __getattr__(name: str) -> object:
    if name == "Application":
        from ._application import Application

        return Application
    if name == "ApplicationError":
        from ._application import ApplicationError

        return ApplicationError
    if name == "SyncApplication":
        from ._toolcall import SyncApplication

        return SyncApplication
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
