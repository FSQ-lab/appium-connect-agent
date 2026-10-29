from __future__ import annotations

import contextlib
import json
import os
import select
import shlex
import signal
import stat
import string
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import anyio
import pytest
from mcp import Client

from .conftest import CANARY, SECRET_PATH, TOOL_NAMES, McpHarness


def diagnostics(harness: McpHarness, result: subprocess.CompletedProcess[str]) -> str:
    logged = (
        harness.stderr_file.read_text(encoding="utf-8")
        if harness.stderr_file.exists()
        else ""
    )
    return result.stderr + logged


def assert_preflight_rejected(
    harness: McpHarness,
    result: subprocess.CompletedProcess[str],
    *,
    secrets: tuple[str, ...] = (),
    expected_code: str,
) -> None:
    assert result.returncode != 0
    assert result.stdout == ""
    assert harness.events() == []
    stderr = diagnostics(harness, result)
    assert f"startup_error code={expected_code}" in stderr
    assert stderr
    for value in (
        *secrets,
        str(harness.config),
        str(harness.adb),
        CANARY,
        SECRET_PATH,
        "Traceback",
        "repr(",
    ):
        assert value not in stderr


def invoke_rejected(
    harness: McpHarness,
    args: list[str],
    *,
    environment: dict[str, str] | None = None,
    secrets: tuple[str, ...] = (),
    expected_code: str = "bootstrap_invalid",
) -> None:
    harness.reset_records()
    result = harness.run(args, environment=environment)
    assert_preflight_rejected(
        harness, result, secrets=secrets, expected_code=expected_code
    )


def test_two_required_long_options_work_in_either_order_and_eof_is_clean(
    mcp_harness: McpHarness,
) -> None:
    for reverse in (False, True):
        mcp_harness.reset_records()
        result = mcp_harness.run(
            mcp_harness.arguments(reverse=reverse), mode="normal", timeout=5
        )
        assert result.returncode == 0
        assert result.stdout == ""
        assert mcp_harness.events() == []
        stderr = diagnostics(mcp_harness, result)
        assert str(mcp_harness.config) not in stderr
        assert str(mcp_harness.adb) not in stderr
        assert "Traceback" not in stderr


def test_harness_python_override_applies_to_all_server_and_helper_launches(
    mcp_harness: McpHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    python = mcp_harness.root / "consumer-python"
    invocations = mcp_harness.root / "python-invocations"
    python.write_text(
        "#!/bin/sh\n"
        + "printf '%s\\n' \"$1\" >> "
        + shlex.quote(str(invocations))
        + "\nexec "
        + shlex.quote(sys.executable)
        + ' "$@"\n',
        encoding="utf-8",
    )
    python.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    monkeypatch.setenv("ACA_MCP_TEST_PYTHON", str(python))

    assert mcp_harness.python_command == str(python)
    assert mcp_harness.parameters().command == str(python)
    raw_server = mcp_harness.run(mcp_harness.arguments(), mode="normal", timeout=5)
    assert raw_server.returncode == 0
    assert raw_server.stdout == ""
    assert mcp_harness.events() == []

    helper = mcp_harness.root / "helper.py"
    helper.write_text("raise SystemExit(0)\n", encoding="utf-8")
    helper_result = subprocess.run(
        [mcp_harness.python_command, str(helper)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        cwd=mcp_harness.root,
    )
    assert helper_result.returncode == 0
    assert invocations.read_text(encoding="utf-8").splitlines() == [
        str(mcp_harness.launcher),
        str(helper),
    ]


def test_missing_repeated_and_positional_arguments_fail_before_all_io(
    mcp_harness: McpHarness,
) -> None:
    cases: tuple[list[str], ...] = (
        [],
        ["--config", str(mcp_harness.config)],
        ["--adb-executable", str(mcp_harness.adb)],
        ["--help"],
        ["--version"],
        [
            f"--config={mcp_harness.config}",
            f"--adb-executable={mcp_harness.adb}",
        ],
        [
            "--config",
            str(mcp_harness.config),
            "--config",
            str(mcp_harness.config),
            "--adb-executable",
            str(mcp_harness.adb),
        ],
        [
            "--config",
            str(mcp_harness.config),
            "--adb-executable",
            str(mcp_harness.adb),
            "--adb-executable",
            str(mcp_harness.adb),
        ],
        [*mcp_harness.arguments(), "positional"],
        ["positional", *mcp_harness.arguments()],
    )
    for args in cases:
        invoke_rejected(
            mcp_harness,
            list(args),
            secrets=(str(mcp_harness.config), str(mcp_harness.adb)),
        )


def test_every_ascii_short_option_is_rejected(
    mcp_harness: McpHarness,
) -> None:
    for letter in string.ascii_letters:
        flag = f"-{letter}"
        cases = (
            [flag, "short-config", "--adb-executable", str(mcp_harness.adb)],
            ["--config", str(mcp_harness.config), flag, "short-adb"],
        )
        for args in cases:
            invoke_rejected(
                mcp_harness,
                args,
                secrets=("short-config", "short-adb"),
            )


def test_relative_missing_directory_and_non_executable_inputs_are_rejected(
    mcp_harness: McpHarness,
) -> None:
    non_executable = mcp_harness.root / "adb-non-executable"
    non_executable.write_text("not executable", encoding="utf-8")
    missing_config = mcp_harness.root / "missing-config.toml"
    missing_adb = mcp_harness.root / "missing-adb"
    cases = (
        (
            [
                "--config",
                mcp_harness.config.name,
                "--adb-executable",
                str(mcp_harness.adb),
            ],
            "bootstrap_invalid",
        ),
        (
            [
                "--config",
                str(mcp_harness.config),
                "--adb-executable",
                mcp_harness.adb.name,
            ],
            "bootstrap_invalid",
        ),
        (mcp_harness.arguments(config=missing_config), "config_invalid"),
        (mcp_harness.arguments(config=mcp_harness.root), "config_invalid"),
        (mcp_harness.arguments(adb=missing_adb), "adb_executable_invalid"),
        (mcp_harness.arguments(adb=mcp_harness.root), "adb_executable_invalid"),
        (mcp_harness.arguments(adb=non_executable), "adb_executable_invalid"),
    )
    for args, expected_code in cases:
        invoke_rejected(
            mcp_harness,
            args,
            secrets=(
                str(missing_config),
                str(missing_adb),
                str(non_executable),
                str(mcp_harness.root),
            ),
            expected_code=expected_code,
        )


def test_config_symlink_follows_file_target_and_rejects_non_file_targets(
    mcp_harness: McpHarness,
) -> None:
    valid = mcp_harness.root / "selected-config-link.toml"
    valid.symlink_to(mcp_harness.config)
    result = mcp_harness.run(
        mcp_harness.arguments(config=valid), mode="normal", timeout=5
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert str(valid) not in diagnostics(mcp_harness, result)

    for name, target in (
        ("dangling-config.toml", mcp_harness.root / "absent-config"),
        ("directory-config.toml", mcp_harness.root),
    ):
        link = mcp_harness.root / name
        link.symlink_to(target)
        invoke_rejected(
            mcp_harness,
            mcp_harness.arguments(config=link),
            secrets=(str(link), str(target)),
            expected_code="config_invalid",
        )


def test_adb_symlink_follows_target_stat_but_preserves_selected_path(
    mcp_harness: McpHarness,
) -> None:
    valid_link = mcp_harness.root / "selected-adb-link"
    valid_link.symlink_to(mcp_harness.adb)

    async def scenario() -> None:
        async with Client(
            mcp_harness.parameters(
                args=mcp_harness.arguments(adb=valid_link), mode="normal"
            )
        ) as client:
            result = await client.call_tool(
                TOOL_NAMES[2], {"request": {"schema_version": 1}}
            )
            assert result.is_error is False

    anyio.run(scenario)
    device_call = next(
        event for event in mcp_harness.events() if event["event"] == "list_devices"
    )
    assert device_call["adb"] == str(valid_link)

    for name, target in (
        ("dangling-adb", mcp_harness.root / "absent-target"),
        ("directory-adb", mcp_harness.root),
    ):
        link = mcp_harness.root / name
        link.symlink_to(target)
        invoke_rejected(
            mcp_harness,
            mcp_harness.arguments(adb=link),
            secrets=(str(link), str(target)),
            expected_code="adb_executable_invalid",
        )

    ordinary = mcp_harness.root / "ordinary-target"
    ordinary.write_text("ordinary", encoding="utf-8")
    link = mcp_harness.root / "non-executable-link"
    link.symlink_to(ordinary)
    invoke_rejected(
        mcp_harness,
        mcp_harness.arguments(adb=link),
        secrets=(str(link), str(ordinary)),
        expected_code="adb_executable_invalid",
    )


def test_missing_adb_option_never_falls_back_to_env_path_toml_or_sdk_roots(
    mcp_harness: McpHarness,
) -> None:
    candidate = mcp_harness.root / "candidate-adb"
    marker = mcp_harness.root / "candidate-invoked"
    candidate.write_text(
        "#!"
        + sys.executable
        + "\nfrom pathlib import Path\n"
        + f"Path({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )
    candidate.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    path_root = mcp_harness.root / "path-bin"
    path_root.mkdir()
    (path_root / "adb").symlink_to(candidate)
    sdk_root = mcp_harness.root / "sdk"
    (sdk_root / "platform-tools").mkdir(parents=True)
    (sdk_root / "platform-tools/adb").symlink_to(candidate)
    adb_config = mcp_harness.root / "adb-in-toml.toml"
    adb_config.write_text(
        "[runtime]\n" + f'adb_executable = "{candidate}"\n', encoding="utf-8"
    )
    sdk_config = mcp_harness.root / "sdk-in-toml.toml"
    sdk_config.write_text(
        "[runtime]\n" + f'android_sdk_root = "{sdk_root}"\n',
        encoding="utf-8",
    )
    cases: tuple[tuple[Path, dict[str, str]], ...] = (
        (mcp_harness.config, {"ADB_EXECUTABLE": str(candidate)}),
        (mcp_harness.config, {"ACA_ADB_EXECUTABLE": str(candidate)}),
        (
            mcp_harness.config,
            {"APPIUM_CONNECT_AGENT_ADB_EXECUTABLE": str(candidate)},
        ),
        (mcp_harness.config, {"PATH": str(path_root)}),
        (adb_config, {}),
        (sdk_config, {}),
        (mcp_harness.config, {"ANDROID_HOME": str(sdk_root)}),
        (mcp_harness.config, {"ANDROID_SDK_ROOT": str(sdk_root)}),
    )
    for config, environment in cases:
        marker.unlink(missing_ok=True)
        invoke_rejected(
            mcp_harness,
            ["--config", str(config)],
            environment=environment,
            secrets=(str(config), str(candidate), str(path_root), str(sdk_root)),
        )
        assert not marker.exists()


def test_each_negative_bootstrap_path_keeps_transport_runtime_and_adb_at_zero(
    mcp_harness: McpHarness,
) -> None:
    secret_config = mcp_harness.root / f"{CANARY}-config.toml"
    secret_config.write_text("[runtime]\n", encoding="utf-8")
    secret_adb = mcp_harness.root / f"{CANARY}-adb"
    secret_adb.write_text("not executable", encoding="utf-8")
    cases = (
        (["--config", str(secret_config)], "bootstrap_invalid"),
        (["--adb-executable", str(secret_adb)], "bootstrap_invalid"),
        (
            mcp_harness.arguments(config=secret_config, adb=secret_adb),
            "adb_executable_invalid",
        ),
    )
    for args, expected_code in cases:
        invoke_rejected(
            mcp_harness,
            args,
            secrets=(str(secret_config), str(secret_adb), CANARY),
            expected_code=expected_code,
        )


def test_public_devices_call_invokes_only_selected_fake_adb_devices_list(
    mcp_harness: McpHarness,
) -> None:
    record = mcp_harness.root / "adb-argv.json"
    serial = "serial-private-canary"
    mcp_harness.adb.write_text(
        "#!"
        + sys.executable
        + "\nimport json, sys\n"
        + "from pathlib import Path\n"
        + f"Path({str(record)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        + f"print('List of devices attached\\n{serial} device model:Pixel_8')\n",
        encoding="utf-8",
    )
    mcp_harness.adb.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="passthrough")) as client:
            result = await client.call_tool(
                TOOL_NAMES[2], {"request": {"schema_version": 1}}
            )
            assert result.is_error is False
            assert result.structured_content["data"] == {
                "count": 1,
                "devices": [
                    {
                        "id": serial,
                        "name": "Pixel_8",
                        "connection_state": "connected",
                    }
                ],
            }

    anyio.run(scenario)
    assert json.loads(record.read_text(encoding="utf-8")) == ["devices", "-l"]
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert serial not in stderr
    assert str(mcp_harness.adb) not in stderr


def test_malformed_frame_is_not_a_tool_call_and_cleanly_exits(
    mcp_harness: McpHarness,
) -> None:
    env = os.environ.copy()
    env.update(mcp_harness.environment("normal"))
    process = subprocess.Popen(
        [
            mcp_harness.python_command,
            str(mcp_harness.launcher),
            *mcp_harness.arguments(),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=mcp_harness.root,
        env=env,
    )
    protocol_output, _ = process.communicate(input=b"{malformed-json\n", timeout=5)
    assert process.returncode == 0
    assert protocol_output == b""
    assert mcp_harness.events() == []
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert stderr == ""


def test_broken_stdout_drains_without_lower_calls_or_leaking(
    mcp_harness: McpHarness,
) -> None:
    env = os.environ.copy()
    env.update(mcp_harness.environment("normal"))
    process = subprocess.Popen(
        [
            mcp_harness.python_command,
            str(mcp_harness.launcher),
            *mcp_harness.arguments(),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=mcp_harness.root,
        env=env,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdout.close()
    process.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"server/discover"}\n')
    process.stdin.close()
    assert process.wait(timeout=5) == 0
    assert mcp_harness.events() == []
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert "server_error" not in stderr
    for forbidden in (
        CANARY,
        SECRET_PATH,
        str(mcp_harness.config),
        str(mcp_harness.adb),
        "Traceback",
    ):
        assert forbidden not in stderr


CANCELLED_STALL_LINE = (
    "WARNING appium_connect_agent.integrations "
    "cancelled_worker_stalled worker_count=1\n"
)


def test_inflight_broken_stdout_cancels_worker_and_cleans_up(
    mcp_harness: McpHarness,
) -> None:
    env = os.environ.copy()
    env.update(mcp_harness.environment("eof_stalled"))
    process = subprocess.Popen(
        [
            mcp_harness.python_command,
            str(mcp_harness.launcher),
            *mcp_harness.arguments(),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=mcp_harness.root,
        env=env,
    )
    stdin = process.stdin
    stdout = process.stdout
    assert stdin is not None
    assert stdout is not None

    def send(frame: dict[str, object]) -> None:
        stdin.write(json.dumps(frame, separators=(",", ":")).encode() + b"\n")
        stdin.flush()

    def wait_for(predicate: Callable[[], bool], description: str) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError(f"timed out waiting for {description}")

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "raw-pipe-test", "version": "1"},
                },
            }
        )
        readable, _, _ = select.select([stdout], [], [], 5)
        assert readable == [stdout]
        initialized = json.loads(stdout.readline())
        assert initialized["id"] == 1
        assert "result" in initialized
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": TOOL_NAMES[2],
                    "arguments": {"request": {"schema_version": 1}},
                },
            }
        )
        wait_for(
            lambda: any(
                event["event"] == "worker_entered" for event in mcp_harness.events()
            ),
            "devices worker",
        )
        stdout.close()
        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": TOOL_NAMES[0],
                    "arguments": {"request": {"schema_version": 1}},
                },
            }
        )
        wait_for(
            lambda: any(
                event["event"] == "worker_cancel_observed"
                for event in mcp_harness.events()
            ),
            "worker cancellation",
        )
        wait_for(
            lambda: (
                CANCELLED_STALL_LINE
                in mcp_harness.stderr_file.read_text(encoding="utf-8")
            ),
            "neutral stall log",
        )
        assert process.poll() is None
        events = mcp_harness.events()
        assert [event["event"] for event in events].count("list_devices") == 1
        cancelled = next(
            event for event in events if event["event"] == "worker_cancel_observed"
        )
        assert cancelled["cancelled"] is True
        assert not any(event["event"] == "server_stopped" for event in events)

        mcp_harness.release_file.touch()
        with contextlib.suppress(BrokenPipeError, ValueError):
            stdin.close()
        assert process.wait(timeout=5) == 0
        final_events = mcp_harness.events()
        stopped = next(
            event for event in final_events if event["event"] == "server_stopped"
        )
        assert stopped["result"] == 0
        stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
        assert stderr == CANCELLED_STALL_LINE
        for forbidden in (
            CANARY,
            SECRET_PATH,
            str(mcp_harness.config),
            str(mcp_harness.adb),
            "Traceback",
        ):
            assert forbidden not in stderr
    finally:
        mcp_harness.release_file.touch()
        with contextlib.suppress(BrokenPipeError, ValueError):
            stdin.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


async def wait_for_event(
    harness: McpHarness,
    name: str,
    *,
    call_index: int | None = None,
) -> None:
    with anyio.fail_after(2):
        while not any(
            event["event"] == name
            and (call_index is None or event.get("call_index") == call_index)
            for event in harness.events()
        ):
            await anyio.sleep(0.001)


def test_cancel_completion_before_threshold_has_no_stall_log(
    mcp_harness: McpHarness,
) -> None:
    async def release() -> None:
        try:
            await wait_for_event(mcp_harness, "worker_cancel_observed", call_index=1)
        finally:
            mcp_harness.release_file.touch()

    async def scenario() -> None:
        scopes: list[anyio.CancelScope] = []

        async def call_device(client: Client) -> None:
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await client.call_tool(
                    TOOL_NAMES[2], {"request": {"schema_version": 1}}
                )

        async with Client(mcp_harness.parameters(mode="cancel_stalled")) as client:
            async with anyio.create_task_group() as group:
                group.start_soon(release)
                group.start_soon(call_device, client)
                await wait_for_event(mcp_harness, "worker_entered", call_index=1)
                assert len(scopes) == 1
                scopes[0].cancel()
            after = await client.call_tool(
                TOOL_NAMES[0], {"request": {"schema_version": 1}}
            )
            assert after.is_error is False

    anyio.run(scenario)
    assert mcp_harness.stderr_file.read_text(encoding="utf-8") == ""
    names = [event["event"] for event in mcp_harness.events()]
    assert names.count("list_devices") == 1
    assert names.count("worker_cancel_observed") == 1


def test_stalled_request_cancel_logs_exactly_once_and_connection_continues(
    mcp_harness: McpHarness,
) -> None:
    async def release_after_log() -> None:
        try:
            with anyio.fail_after(2):
                while CANCELLED_STALL_LINE not in mcp_harness.stderr_file.read_text(
                    encoding="utf-8"
                ):
                    await anyio.sleep(0.001)
        finally:
            mcp_harness.release_file.touch()

    async def scenario() -> None:
        scopes: list[anyio.CancelScope] = []

        async def call_device(client: Client) -> None:
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await client.call_tool(
                    TOOL_NAMES[2], {"request": {"schema_version": 1}}
                )

        async with Client(mcp_harness.parameters(mode="cancel_stalled")) as client:
            async with anyio.create_task_group() as group:
                group.start_soon(release_after_log)
                group.start_soon(call_device, client)
                await wait_for_event(mcp_harness, "worker_entered", call_index=1)
                assert len(scopes) == 1
                scopes[0].cancel()
            after = await client.call_tool(
                TOOL_NAMES[0], {"request": {"schema_version": 1}}
            )
            assert after.is_error is False

    anyio.run(scenario)
    assert mcp_harness.stderr_file.read_text(encoding="utf-8") == (CANCELLED_STALL_LINE)
    events = mcp_harness.events()
    assert [event["event"] for event in events].count("list_devices") == 1
    assert (
        next(event for event in events if event["event"] == "worker_cancel_observed")[
            "cancelled"
        ]
        is True
    )


def test_two_independent_stalled_cancels_each_log_once(
    mcp_harness: McpHarness,
) -> None:
    releases = (
        Path(str(mcp_harness.release_file) + ".first"),
        Path(str(mcp_harness.release_file) + ".second"),
    )

    async def release_after_log(index: int) -> None:
        try:
            with anyio.fail_after(2):
                while (
                    mcp_harness.stderr_file.read_text(encoding="utf-8").count(
                        CANCELLED_STALL_LINE
                    )
                    < index
                ):
                    await anyio.sleep(0.001)
        finally:
            releases[index - 1].touch()

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="cancel_twice")) as client:

            async def call_device(scopes_for_call: list[anyio.CancelScope]) -> None:
                with anyio.CancelScope() as scope:
                    scopes_for_call.append(scope)
                    await client.call_tool(
                        TOOL_NAMES[2], {"request": {"schema_version": 1}}
                    )

            for index in (1, 2):
                scopes: list[anyio.CancelScope] = []
                async with anyio.create_task_group() as group:
                    group.start_soon(release_after_log, index)
                    group.start_soon(call_device, scopes)
                    await wait_for_event(
                        mcp_harness, "worker_entered", call_index=index
                    )
                    assert len(scopes) == 1
                    scopes[0].cancel()
                after = await client.call_tool(
                    TOOL_NAMES[0], {"request": {"schema_version": 1}}
                )
                assert after.is_error is False

    try:
        anyio.run(scenario)
    finally:
        for release in releases:
            release.touch()
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert stderr == CANCELLED_STALL_LINE * 2
    events = mcp_harness.events()
    assert [event["event"] for event in events].count("list_devices") == 2
    cancelled = [
        event for event in events if event["event"] == "worker_cancel_observed"
    ]
    assert len(cancelled) == 2
    assert [event["call_index"] for event in cancelled] == [1, 2]
    assert all(event["cancelled"] is True for event in cancelled)


def test_inflight_eof_logs_neutral_stall_then_releases_cleanly(
    mcp_harness: McpHarness,
) -> None:
    parameters = mcp_harness.parameters(mode="eof_stalled")
    client_script = mcp_harness.root / "abrupt_client.py"
    client_script.write_text(
        "import anyio\n"
        "from mcp import Client, StdioServerParameters\n"
        f"PARAMETERS = StdioServerParameters(command={parameters.command!r}, "
        f"args={parameters.args!r}, env={parameters.env!r}, "
        f"cwd={str(parameters.cwd)!r})\n"
        "async def main() -> None:\n"
        "    async with Client(PARAMETERS) as client:\n"
        f"        await client.call_tool({TOOL_NAMES[2]!r}, "
        "{'request': {'schema_version': 1}})\n"
        "anyio.run(main)\n",
        encoding="utf-8",
    )
    helper = subprocess.Popen(
        [mcp_harness.python_command, str(client_script)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=mcp_harness.root,
        start_new_session=True,
    )

    def process_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def wait_for(predicate: Callable[[], bool], description: str) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError(f"timed out waiting for {description}")

    server_pid: int | None = None
    try:
        wait_for(
            lambda: any(
                event["event"] == "server_started" for event in mcp_harness.events()
            ),
            "server start",
        )
        started = next(
            event
            for event in mcp_harness.events()
            if event["event"] == "server_started"
        )
        assert isinstance(started["pid"], int)
        server_pid = started["pid"]
        wait_for(
            lambda: any(
                event["event"] == "worker_entered" for event in mcp_harness.events()
            ),
            "worker",
        )
        helper.terminate()
        helper.wait(timeout=5)
        wait_for(
            lambda: (
                CANCELLED_STALL_LINE
                in mcp_harness.stderr_file.read_text(encoding="utf-8")
            ),
            "neutral stall log",
        )
        assert server_pid is not None
        os.kill(server_pid, 0)
        assert not any(
            event["event"] == "server_stopped" for event in mcp_harness.events()
        )
        mcp_harness.release_file.touch()
        wait_for(
            lambda: any(
                event["event"] == "server_stopped" for event in mcp_harness.events()
            ),
            "server stop",
        )
        events = mcp_harness.events()
        assert [event["event"] for event in events].count("list_devices") == 1
        cancelled = next(
            event for event in events if event["event"] == "worker_cancel_observed"
        )
        assert cancelled["cancelled"] is True
        stopped = next(event for event in events if event["event"] == "server_stopped")
        assert stopped["result"] == 0
        wait_for(
            lambda: not process_exists(server_pid),
            "server process natural exit",
        )
        assert not process_exists(server_pid)
        stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
        assert stderr == CANCELLED_STALL_LINE
        for forbidden in (
            CANARY,
            SECRET_PATH,
            str(mcp_harness.config),
            str(mcp_harness.adb),
            "Traceback",
        ):
            assert forbidden not in stderr
    finally:
        mcp_harness.release_file.touch()
        if helper.poll() is None:
            helper.kill()
            helper.wait(timeout=5)
        if server_pid is not None and process_exists(server_pid):
            with contextlib.suppress(ProcessLookupError):
                os.kill(server_pid, signal.SIGKILL)


def test_active_session_broken_stdout_cleans_once_and_exits_zero(
    mcp_harness: McpHarness,
) -> None:
    env = os.environ.copy()
    env.update(mcp_harness.environment("session_normal"))
    process = subprocess.Popen(
        [
            mcp_harness.python_command,
            str(mcp_harness.launcher),
            *mcp_harness.arguments(),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=mcp_harness.root,
        env=env,
    )
    stdin = process.stdin
    stdout = process.stdout
    assert stdin is not None
    assert stdout is not None

    def send(frame: dict[str, object]) -> None:
        stdin.write(json.dumps(frame, separators=(",", ":")).encode() + b"\n")
        stdin.flush()

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {},
                    "clientInfo": {"name": "session-broken-pipe", "version": "1"},
                },
            }
        )
        readable, _, _ = select.select([stdout], [], [], 5)
        assert readable == [stdout]
        assert json.loads(stdout.readline())["id"] == 1
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": TOOL_NAMES[3],
                    "arguments": {
                        "request": {"schema_version": 1, "device_id": "device"}
                    },
                },
            }
        )
        readable, _, _ = select.select([stdout], [], [], 5)
        assert readable == [stdout]
        opened = json.loads(stdout.readline())
        assert opened["id"] == 2
        assert "result" in opened

        stdout.close()
        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": TOOL_NAMES[0],
                    "arguments": {"request": {"schema_version": 1}},
                },
            }
        )
        stdin.close()
        assert process.wait(timeout=5) == 0
        names = [event["event"] for event in mcp_harness.events()]
        assert names.count("create_session") == 1
        assert names.count("session_quit") == 1
        assert names.count("runtime_connect_enter") == 1
        assert names.count("runtime_connect_exit") == 1
        stopped = next(
            event
            for event in mcp_harness.events()
            if event["event"] == "server_stopped"
        )
        assert stopped["result"] == 0
        stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
        for forbidden in (
            "device",
            CANARY,
            SECRET_PATH,
            str(mcp_harness.config),
            str(mcp_harness.adb),
            "Traceback",
        ):
            assert forbidden not in stderr
    finally:
        with contextlib.suppress(BrokenPipeError, ValueError):
            stdin.close()
        with contextlib.suppress(ValueError):
            stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
