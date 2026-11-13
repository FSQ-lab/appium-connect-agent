"""Formal stdio MCP bootstrap and fixed readiness tool registration."""

from __future__ import annotations

import inspect
import logging
import os
import stat
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from appium_connect_agent.configuration import ConfigurationError, load_configuration

from ._application import Application, ApplicationError
from ._catalog import TOOL_CATALOG, ToolSpec
from ._models import canonical_json, canonical_value_and_json

_LOGGER_NAME = "appium_connect_agent.integrations"


class _McpLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "mcp" or record.name.startswith("mcp."):
            record.msg = "mcp_sdk_internal_error"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


class _BootstrapError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_McpLogFilter())
    logging.basicConfig(
        force=True,
        level=logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
        handlers=[handler],
    )


def _parse_bootstrap(arguments: Sequence[str]) -> tuple[Path, Path]:
    if len(arguments) != 4:
        raise _BootstrapError("bootstrap_invalid")
    values: dict[str, Path] = {}
    for index in (0, 2):
        option = arguments[index]
        value = arguments[index + 1]
        if option not in ("--config", "--adb-executable") or option in values:
            raise _BootstrapError("bootstrap_invalid")
        if value.startswith("-"):
            raise _BootstrapError("bootstrap_invalid")
        path = Path(value)
        if not path.is_absolute():
            raise _BootstrapError("bootstrap_invalid")
        values[option] = path
    if set(values) != {"--config", "--adb-executable"}:
        raise _BootstrapError("bootstrap_invalid")
    return values["--config"], values["--adb-executable"]


def _validate_adb_executable(path: Path) -> Path:
    if not path.is_absolute():
        raise _BootstrapError("adb_executable_invalid")
    try:
        metadata = path.stat()
        executable = os.access(path, os.X_OK)
    except (OSError, ValueError):
        raise _BootstrapError("adb_executable_invalid") from None
    if not stat.S_ISREG(metadata.st_mode) or not executable:
        raise _BootstrapError("adb_executable_invalid")
    return path


def _only_broken_pipe(error: BaseException) -> bool:
    if isinstance(error, BrokenPipeError):
        return True
    if isinstance(error, BaseExceptionGroup):
        return bool(error.exceptions) and all(
            _only_broken_pipe(nested) for nested in error.exceptions
        )
    return False


def _success(model: BaseModel) -> CallToolResult:
    structured, text = canonical_value_and_json(model)
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=structured,
        is_error=False,
    )


def create_server(application: Application) -> MCPServer[Application]:
    """Construct the fixed server without starting Runtime, ADB, or transport I/O."""
    if application.surface != "mcp":
        raise ValueError("MCP server requires surface='mcp'")
    _configure_logging()

    @asynccontextmanager
    async def lifespan(_: MCPServer[Application]) -> AsyncIterator[Application]:
        try:
            yield application
        finally:
            await application.aclose()

    server = MCPServer[Application](
        "appium-connect-agent",
        version="0.1.0",
        instructions=(
            "Local readiness, explicit Session lifecycle, Native observation, caller-requested "
            "Element click, text, IME action, and gesture tools, Device back, keycode, keyboard, "
            "clipboard, alert, and status-bar controls, and application lifecycle, install, and "
            "remove tools; no automatic observation, verification, navigation, action chain, retry, "
            "replay, rollback, attach, recovery, clear-app, or HTTP tools."
        ),
        log_level="WARNING",
        lifespan=lifespan,
        subscriptions=False,
    )

    def build_handler(
        spec: ToolSpec,
    ) -> Callable[[BaseModel, Context[Application]], Awaitable[BaseModel]]:
        async def handler(
            request: BaseModel,
            ctx: Context[Application],
        ) -> BaseModel:
            try:
                result = await ctx.request_context.lifespan_context._dispatch_mcp(
                    spec, request
                )
            except ApplicationError as error:
                raise ToolError(f"ACA_ERROR {canonical_json(error.data)}") from None
            return cast(BaseModel, _success(result))

        handler.__name__ = spec.handler_symbol
        handler.__qualname__ = spec.handler_symbol
        handler.__annotations__ = {
            "request": spec.request_annotation,
            "ctx": Context[Application],
            "return": spec.result_model,
        }
        cast(Any, handler).__signature__ = inspect.Signature(
            parameters=(
                inspect.Parameter(
                    "request",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=spec.request_annotation,
                ),
                inspect.Parameter(
                    "ctx",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=Context[Application],
                ),
            ),
            return_annotation=spec.result_model,
        )
        return handler

    for spec in TOOL_CATALOG.specs:
        hints = spec.annotations
        server.add_tool(
            build_handler(spec),
            name=spec.mcp_name,
            description=spec.description,
            structured_output=True,
            annotations=ToolAnnotations(
                read_only_hint=hints.read_only,
                destructive_hint=hints.destructive,
                idempotent_hint=hints.idempotent,
                open_world_hint=hints.open_world,
            ),
        )

    return server


def main() -> int:
    """Load one immutable bootstrap and run the official MCP stdio transport."""
    _configure_logging()
    try:
        config_path, adb_path = _parse_bootstrap(sys.argv[1:])
        adb_executable = _validate_adb_executable(adb_path)
        if not config_path.is_absolute():
            raise _BootstrapError("config_invalid")
        loaded = load_configuration(config_path)
    except ConfigurationError:
        logging.getLogger(_LOGGER_NAME).error("startup_error code=config_invalid")
        return 2
    except _BootstrapError as error:
        logging.getLogger(_LOGGER_NAME).error("startup_error code=%s", error.code)
        return 2

    application = Application(loaded.settings, adb_executable, surface="mcp")
    server = create_server(application)
    try:
        server.run("stdio")
    except KeyboardInterrupt:
        return 130
    except BaseException as error:
        if _only_broken_pipe(error):
            return 4 if application.shutdown_degraded else 0
        logging.getLogger(_LOGGER_NAME).error(
            "server_error code=stdio_transport_failed"
        )
        return 4 if application.shutdown_degraded else 1
    return 4 if application.shutdown_degraded else 0
