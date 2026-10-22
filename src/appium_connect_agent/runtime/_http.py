"""One raw HTTPX request, joined before returning to the synchronous caller."""

import time
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

import anyio
import httpcore
import httpx
from anyio.from_thread import start_blocking_portal


class HTTPFailure(Exception):
    def __init__(self, code: str = "service_invalid_response") -> None:
        self.code = code


@dataclass
class HTTPResult:
    body: bytes = b""
    error: BaseException | None = None
    cleanup_errors: list[BaseException] = field(default_factory=list)
    traced_error: BaseException | None = None
    traced_cleanup: BaseException | None = None

    async def trace(self, name: str, info: dict[str, object]) -> None:
        # Fixed HTTPcore HTTP/1 lifecycle: retain only exception objects, no I/O.
        error = info.get("exception")
        if isinstance(error, BaseException):
            if name in (
                "http11.receive_response_headers.failed",
                "http11.receive_response_body.failed",
            ):
                if self.traced_error is None:
                    self.traced_error = error
            elif name == "http11.response_closed.failed":
                self.traced_cleanup = error

    def add_cleanup(self, error: BaseException) -> None:
        if error is not self.error and not any(
            _same_failure(error, prior) for prior in self.cleanup_errors
        ):
            self.cleanup_errors.append(error)

    def retain(self, error: BaseException, response_closed: bool) -> None:
        if self.traced_cleanup is not None:
            self.add_cleanup(self.traced_cleanup)
        if self.traced_error is not None:
            self.error = self.traced_error
            if not _same_failure(error, self.traced_error):
                self.add_cleanup(error)
        elif (
            isinstance(error, httpx.CloseError)
            or response_closed
            or (
                self.traced_cleanup is not None
                and _same_failure(error, self.traced_cleanup)
            )
        ):
            self.add_cleanup(error)
        else:
            self.error = error


def _same_failure(error: BaseException, original: BaseException) -> bool:
    if error is original:
        return True
    # HTTPX 0.28.1 wraps these public HTTPcore types with an explicit direct cause.
    mappings = (
        (httpcore.RemoteProtocolError, httpx.RemoteProtocolError),
        (httpcore.ReadError, httpx.ReadError),
        (httpcore.ReadTimeout, httpx.ReadTimeout),
    )
    return error.__cause__ is original and any(
        type(original) is source and type(error) is target
        for source, target in mappings
    )


def _check_response(response: httpx.Response) -> None:
    code = response.status_code
    if code != 200:
        raise HTTPFailure(
            "service_access_denied"
            if code in (401, 403)
            else "service_redirect"
            if 300 <= code < 400
            else "service_http_error"
        )
    if any(
        coding.strip().lower() != "identity"
        for coding in response.headers.get("content-encoding", "identity").split(",")
    ):
        raise HTTPFailure()
    length = response.headers.get("content-length")
    if (
        length is None
        and response.headers.get("transfer-encoding", "").lower() != "chunked"
    ):
        raise HTTPFailure()
    if length is not None:
        # The library validates syntax; this is only the project body-size policy.
        significant = length.lstrip("0") or "0"
        if len(significant) > 5 or (len(significant) == 5 and significant > "65536"):
            raise HTTPFailure("service_response_too_large")


async def _request(url: str, result: HTTPResult) -> None:
    client: httpx.AsyncClient | None = None
    response: httpx.Response | None = None
    transport: httpx.AsyncHTTPTransport | None = None
    body = bytearray()
    try:
        transport = httpx.AsyncHTTPTransport(
            retries=0,
            trust_env=False,
            http1=True,
            http2=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        )
        client = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=None,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = await client.send(
            client.build_request(
                "GET", url + "/status", extensions={"trace": result.trace}
            ),
            stream=True,
        )
        _check_response(response)
        async for chunk in response.aiter_raw():
            if len(body) + len(chunk) > 64 * 1024:
                raise HTTPFailure("service_response_too_large")
            body.extend(chunk)
    except BaseException as error:
        result.retain(error, response is not None and response.is_closed)
    finally:
        result.body = bytes(body)
        # Each resource still gets its cleanup attempt under cancellation.
        with anyio.CancelScope(shield=True):
            for resource in (response, client if client is not None else transport):
                if resource is not None:
                    try:
                        await resource.aclose()
                    except BaseException as error:
                        result.add_cleanup(error)
                        if resource is client and transport is not None:
                            try:
                                await transport.aclose()
                            except BaseException as transport_error:
                                result.add_cleanup(transport_error)


def get_status(url: str, checkpoint: Callable[[], None], deadline: float) -> HTTPResult:
    result = HTTPResult()
    primary: BaseException | None = None
    try:
        checkpoint()
        with start_blocking_portal(backend="asyncio") as portal:
            checkpoint()
            future = portal.start_task_soon(_request, url, result)
            try:
                while True:
                    checkpoint()
                    try:
                        future.result(
                            timeout=max(0, min(0.1, deadline - time.monotonic()))
                        )
                    except FutureTimeout:
                        if not future.done():
                            checkpoint()
                            continue
                        future.result()
                    if result.error is None:
                        checkpoint()
                    break
            except BaseException as error:
                primary = error
                future.cancel()
        # Portal exit joins the thread; Future cancellation alone proves nothing.
    except BaseException as error:
        if primary is None:
            primary = error
        else:
            result.cleanup_errors.append(error)
    try:
        checkpoint()
    except BaseException as error:
        if primary is None and result.error is None:
            primary = error
    if primary is not None:
        result.error = primary
    return result
