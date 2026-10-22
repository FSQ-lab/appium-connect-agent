"""One bounded HTTP exchange over a cancellable nonblocking numeric socket."""

import errno
import re
import selectors
import socket
import time
from collections.abc import Callable
from urllib.parse import urlsplit


class HTTPFailure(Exception):
    def __init__(self, code: str = "service_invalid_response") -> None:
        self.code = code


def _body_size(value: bytes, base: int) -> int:
    """Convert validated digits without a text-length or global int-limit shortcut."""
    significant = value.lstrip(b"0") or b"0"
    if len(significant) > 5:
        raise HTTPFailure("service_response_too_large")
    size = int(significant, base)
    if size > 64 * 1024:
        raise HTTPFailure("service_response_too_large")
    return size


class _Wire:
    def __init__(
        self,
        peer: socket.socket,
        selector: selectors.BaseSelector,
        checkpoint: Callable[[], None],
        deadline: float,
    ) -> None:
        self.peer, self.selector = peer, selector
        self.checkpoint, self.deadline = checkpoint, deadline
        self.buffer = bytearray()
        self.wire_bytes = 0
        self.header_bytes = 0

    def wait(self, event: int) -> None:
        self.selector.modify(self.peer, event)
        while True:
            self.checkpoint()
            ready = self.selector.select(
                max(0, min(0.1, self.deadline - time.monotonic()))
            )
            self.checkpoint()
            if ready:
                return

    def receive(self) -> None:
        while True:
            self.checkpoint()
            try:
                data = self.peer.recv(min(4096, 96 * 1024 - self.wire_bytes + 1))
            except BlockingIOError:
                self.wait(selectors.EVENT_READ)
                continue
            self.checkpoint()
            if not data:
                raise HTTPFailure()
            self.wire_bytes += len(data)
            if self.wire_bytes > 96 * 1024:
                raise HTTPFailure("service_response_too_large")
            self.buffer.extend(data)
            return

    def line(self, *, header: bool = False) -> bytes:
        while True:
            self.checkpoint()
            end = self.buffer.find(b"\r\n")
            size = end + 2 if end >= 0 else len(self.buffer)
            if header and self.header_bytes + size > 16 * 1024:
                raise HTTPFailure("service_response_too_large")
            if end >= 0:
                line = bytes(self.buffer[:end])
                del self.buffer[: end + 2]
                if header:
                    self.header_bytes += size
                return line
            self.receive()

    def take(self, size: int) -> bytes:
        while len(self.buffer) < size:
            self.receive()
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        self.checkpoint()
        return result

    def headers(self) -> dict[bytes, bytes]:
        headers: dict[bytes, bytes] = {}
        while line := self.line(header=True):
            name, separator, value = line.partition(b":")
            if (
                not separator
                or re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None
                or any((char < 32 and char != 9) or char == 127 for char in value)
            ):
                raise HTTPFailure()
            name = name.lower()
            if name in headers and name in (b"content-length", b"transfer-encoding"):
                raise HTTPFailure()
            value = value.strip(b" \t")
            if name == b"content-encoding" and name in headers:
                headers[name] += b"," + value
            else:
                headers[name] = value
        return headers

    def response(self) -> bytes:
        status = self.line(header=True)
        match = re.fullmatch(rb"HTTP/1\.[01] ([0-9]{3}) [\x20-\x7e]*", status)
        if match is None:
            raise HTTPFailure()
        headers = self.headers()
        code = int(match[1])
        if code != 200:
            raise HTTPFailure(
                "service_access_denied"
                if code in (401, 403)
                else "service_redirect"
                if 300 <= code < 400
                else "service_http_error"
            )
        if any(
            coding.strip(b" \t").lower() != b"identity"
            for coding in headers.get(b"content-encoding", b"identity").split(b",")
        ):
            raise HTTPFailure()
        length, encoding = (
            headers.get(b"content-length"),
            headers.get(b"transfer-encoding"),
        )
        if encoding is None:
            if length is None or re.fullmatch(rb"[0-9]+", length) is None:
                raise HTTPFailure()
            return self.take(_body_size(length, 10))
        if length is not None or encoding.lower() != b"chunked":
            raise HTTPFailure()
        body = bytearray()
        while True:
            line = self.line()
            match = re.fullmatch(
                rb"([0-9a-fA-F]+)(?:;[!#$%&'*+.^_`|~0-9A-Za-z-]+"
                rb"(?:=(?:[!#$%&'*+.^_`|~0-9A-Za-z-]+|"
                rb'"(?:[\t\x20-\x21\x23-\x5b\x5d-\x7e\x80-\xff]|'
                rb'\\[\t\x20-\x7e\x80-\xff])*"))?)*',
                line,
            )
            if match is None:
                raise HTTPFailure()
            size = _body_size(match[1], 16)
            if size + len(body) > 64 * 1024:
                raise HTTPFailure("service_response_too_large")
            if not size:
                trailers = self.headers()
                if b"content-length" in trailers or b"transfer-encoding" in trailers:
                    raise HTTPFailure()
                return bytes(body)
            body.extend(self.take(size))
            if self.take(2) != b"\r\n":
                raise HTTPFailure()


def get_status(url: str, checkpoint: Callable[[], None], deadline: float) -> bytes:
    parts = urlsplit(url)
    assert parts.hostname is not None and parts.port is not None
    family = socket.AF_INET6 if ":" in parts.hostname else socket.AF_INET
    checkpoint()
    try:
        with (
            socket.socket(family, socket.SOCK_STREAM) as peer,
            selectors.DefaultSelector() as selector,
        ):
            peer.setblocking(False)
            selector.register(peer, selectors.EVENT_WRITE)
            wire = _Wire(peer, selector, checkpoint, deadline)
            checkpoint()
            result = peer.connect_ex((parts.hostname, parts.port))
            checkpoint()
            if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EINTR):
                raise HTTPFailure("service_unavailable")
            if result:
                wire.wait(selectors.EVENT_WRITE)
                if peer.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                    raise HTTPFailure("service_unavailable")
            pending = memoryview(
                f"GET {parts.path}/status HTTP/1.1\r\nHost: {parts.netloc}\r\n"
                "Connection: close\r\nAccept: application/json\r\n\r\n".encode("ascii")
            )
            while pending:
                checkpoint()
                try:
                    sent = peer.send(pending)
                except BlockingIOError:
                    wire.wait(selectors.EVENT_WRITE)
                    continue
                if not sent:
                    raise HTTPFailure("service_unavailable")
                pending = pending[sent:]
            return wire.response()
    except OSError:
        raise HTTPFailure("service_unavailable") from None
