"""Repository-only adapter for public local static diagnostics; not a product CLI."""

import argparse
import json
import math
import sys
from collections.abc import Sequence
from datetime import UTC
from pathlib import Path
from typing import NoReturn

from appium_connect_agent.runtime import (
    DiagnosticReport,
    EnvironmentBusyError,
    LocalSettings,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    ProgressEvent,
    Runtime,
    RuntimeOperationError,
)


class InvalidArguments(Exception):
    """An argparse failure, without echoing arbitrary command-line contents."""


class DiagnosticParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InvalidArguments


def absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("expected an absolute path")
    return path


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a finite positive number") from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("expected a finite positive number")
    return timeout


def parser() -> DiagnosticParser:
    result = DiagnosticParser(
        description=(
            "Read-only local static diagnostics (macOS / Android / UiAutomator2). "
            "Completion, including exit 0, does not imply environment readiness."
        ),
        allow_abbrev=False,
    )
    result.add_argument("--json", action="store_true", help="emit one JSON result")
    for option in (
        "appium-executable",
        "appium-home",
        "node-executable",
        "npm-executable",
        "java-home",
        "android-sdk-root",
    ):
        result.add_argument(
            f"--{option}",
            type=absolute_path,
            metavar="ABSOLUTE_PATH",
            help="explicit path; no expansion, existence check or fallback",
        )
    result.add_argument(
        "--timeout-seconds",
        type=positive_timeout,
        default=10.0,
        metavar="SECONDS",
        help="finite positive total Runtime budget (default: 10)",
    )
    return result


def report_data(report: DiagnosticReport) -> dict[str, object]:
    return {
        "operation_id": report.operation_id,
        "observed_at": report.observed_at.astimezone(UTC).isoformat(),
        "host": report.host,
        "target": report.target,
        "driver": report.driver,
        "checks": [
            {
                "check_id": check.check_id,
                "status": check.status,
                "reason_code": check.reason_code,
                "evidence": list(check.evidence),
                "remediation": check.remediation,
            }
            for check in report.checks
        ],
        "observer_errors": list(report.observer_errors),
    }


def write_text_report(report: DiagnosticReport) -> None:
    # Quote values so evidence/newlines remain data, with no implicit truncation.
    for field, value in report_data(report).items():
        if field == "checks":
            if not report.checks:
                print("checks: []")
            else:
                print("checks:")
                for index, check in enumerate(report.checks):
                    print(f"  [{index}]")
                    for name, item in (
                        ("check_id", check.check_id),
                        ("status", check.status),
                        ("reason_code", check.reason_code),
                        ("evidence", list(check.evidence)),
                        ("remediation", check.remediation),
                    ):
                        print(f"    {name}: {json.dumps(item, ensure_ascii=False)}")
        else:
            print(f"{field}: {json.dumps(value, ensure_ascii=False)}")


def write_result(
    *,
    json_mode: bool,
    execution: str,
    code: str | None = None,
    message: str | None = None,
    report: DiagnosticReport | None = None,
) -> None:
    error = None if code is None else {"code": code, "message": message}
    if json_mode:
        print(
            json.dumps(
                {
                    "execution": execution,
                    "error": error,
                    "report": None if report is None else report_data(report),
                },
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    elif report is not None:
        write_text_report(report)
    if error is not None:
        print(f"{code}: {message}", file=sys.stderr)


def progress(event: ProgressEvent) -> None:
    fields = (
        ("operation_id", event.operation_id),
        ("phase", event.phase),
        ("check_id", event.check_id),
        ("message", event.message),
    )
    print(
        " ".join(
            f"{name}={json.dumps(value, ensure_ascii=False)}" for name, value in fields
        ),
        file=sys.stderr,
        flush=True,
    )


def operation_message(error: RuntimeOperationError) -> str:
    if isinstance(error, OperationCancelledError):
        return "The diagnostic operation was cancelled."
    if isinstance(error, OperationTimeoutError):
        return "The diagnostic operation exceeded its time budget."
    if isinstance(error, EnvironmentBusyError):
        return "Another operation holds the environment coordination resource."
    return "The diagnostic operation could not complete."


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Select the error channel even when --json follows an invalid argument.
    json_mode = "--json" in arguments
    try:
        options = parser().parse_args(arguments)
    except InvalidArguments:
        write_result(
            json_mode=json_mode,
            execution="error",
            code="invalid_arguments",
            message="Invalid command-line arguments. Use --help for usage.",
        )
        return 2

    try:
        runtime = Runtime(
            LocalSettings(
                appium_executable=options.appium_executable,
                appium_home=options.appium_home,
                node_executable=options.node_executable,
                npm_executable=options.npm_executable,
                java_home=options.java_home,
                android_sdk_root=options.android_sdk_root,
            ),
            on_progress=progress,
        )
        report = runtime.diagnose(
            control=OperationControl(timeout_seconds=options.timeout_seconds)
        )
    except OperationCancelledError as error:
        write_result(
            json_mode=json_mode,
            execution="cancelled",
            code=error.code,
            message=operation_message(error),
            report=error.partial_report,
        )
        return 130
    except RuntimeOperationError as error:
        write_result(
            json_mode=json_mode,
            execution="error",
            code=error.code,
            message=operation_message(error),
            report=error.partial_report,
        )
        return 3
    except KeyboardInterrupt:
        # Runtime has already unwound its resource-release path. No public report.
        write_result(
            json_mode=json_mode,
            execution="cancelled",
            code="operation_cancelled",
            message="The diagnostic operation was cancelled.",
        )
        return 130

    write_result(json_mode=json_mode, execution="completed", report=report)
    return int(any(check.status == "fail" for check in report.checks))


if __name__ == "__main__":
    raise SystemExit(main())
