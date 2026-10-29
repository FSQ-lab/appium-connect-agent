"""Formal stdio MCP bootstrap and fixed readiness tool registration."""

from __future__ import annotations

import logging
import os
import stat
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from appium_connect_agent.configuration import ConfigurationError, load_configuration

from ._application import McpApplication
from ._models import (
    CapabilitiesRequest,
    CapabilityResult,
    DeviceListRequest,
    DeviceListResult,
    RuntimeCheckRequest,
    RuntimeCheckResult,
    SessionCloseRequest,
    SessionCloseResult,
    SessionOpenRequest,
    SessionOpenResult,
    SessionStatusRequest,
    SessionStatusResult,
    canonical_json,
)

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
    text = canonical_json(model)
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=model.model_dump(mode="python"),
        is_error=False,
    )


def create_server(application: McpApplication) -> MCPServer[McpApplication]:
    """Construct the fixed server without starting Runtime, ADB, or transport I/O."""
    _configure_logging()

    @asynccontextmanager
    async def lifespan(_: MCPServer[McpApplication]) -> AsyncIterator[McpApplication]:
        try:
            yield application
        finally:
            await application.shutdown()

    server = MCPServer[McpApplication](
        "appium-connect-agent",
        version="0.1.0",
        instructions=(
            "Local readiness and explicit Session lifecycle only; no UI, retry, "
            "attach, recovery, or HTTP tools."
        ),
        log_level="WARNING",
        lifespan=lifespan,
        subscriptions=False,
    )

    @server.tool(
        name="appium.capabilities.get",
        description="Return fixed integration capabilities and qualification limits.",
        structured_output=True,
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    async def capabilities_get(
        request: CapabilitiesRequest,
        ctx: Context[McpApplication],
    ) -> CapabilityResult:
        del request
        result = ctx.request_context.lifespan_context.capabilities()
        return cast(CapabilityResult, _success(result))

    @server.tool(
        name="appium.runtime.check",
        description="Run one bounded static or external Runtime readiness check.",
        structured_output=True,
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        ),
    )
    async def runtime_check(
        request: RuntimeCheckRequest,
        ctx: Context[McpApplication],
    ) -> RuntimeCheckResult:
        result = await ctx.request_context.lifespan_context.runtime_check(
            request.mode,
            request.timeout_seconds,
        )
        return cast(RuntimeCheckResult, _success(result))

    @server.tool(
        name="appium.devices.list",
        description="List Android devices through the bootstrapped ADB executable.",
        structured_output=True,
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        ),
    )
    async def devices_list(
        request: DeviceListRequest,
        ctx: Context[McpApplication],
    ) -> DeviceListResult:
        result = await ctx.request_context.lifespan_context.devices_list(
            request.timeout_seconds
        )
        return cast(DeviceListResult, _success(result))

    @server.tool(
        name="appium.session.open",
        description="Open the single MCP-owned Android Session.",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
        structured_output=True,
    )
    async def session_open(
        request: SessionOpenRequest,
        ctx: Context[McpApplication],
    ) -> SessionOpenResult:
        result = await ctx.request_context.lifespan_context.session_open(request)
        return cast(SessionOpenResult, _success(result))

    @server.tool(
        name="appium.session.status",
        description="Return the local snapshot for one opaque Session handle.",
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def session_status(
        request: SessionStatusRequest,
        ctx: Context[McpApplication],
    ) -> SessionStatusResult:
        result = ctx.request_context.lifespan_context.session_status(
            request.session_handle
        )
        return cast(SessionStatusResult, _success(result))

    @server.tool(
        name="appium.session.close",
        description="Close one MCP-owned Session or its retained tombstone.",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=True,
        ),
        structured_output=True,
    )
    async def session_close(
        request: SessionCloseRequest,
        ctx: Context[McpApplication],
    ) -> SessionCloseResult:
        result = await ctx.request_context.lifespan_context.session_close(
            request.session_handle,
            request.timeout_seconds,
        )
        return cast(SessionCloseResult, _success(result))

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

    application = McpApplication(loaded.settings, adb_executable)
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
