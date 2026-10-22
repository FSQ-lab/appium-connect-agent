"""Pure, deliberately local-only endpoint validation; never resolves a host."""

import ipaddress
import re
from urllib.parse import urlsplit


def normalize_server_url(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or not value
        or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
        or any(char in value for char in "\\%?#")
    ):
        raise ValueError("server_url must be an ASCII HTTP loopback URL")
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
        if (
            parts.scheme.lower() != "http"
            or re.fullmatch(
                r"(?:\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.]+):[0-9]+", parts.netloc
            )
            is None
            or not host
            or port is None
            or not 1 <= port <= 65535
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError
        if host.lower() == "localhost":
            host = "127.0.0.1"
        address = ipaddress.ip_address(host)
        if not address.is_loopback:
            raise ValueError
        host = f"[{address}]" if address.version == 6 else str(address)
        path = parts.path
        if "//" in path:
            raise ValueError
        path = path.rstrip("/")
        if path and (
            not path.startswith("/")
            or any(
                segment in (".", "..")
                or re.fullmatch(r"[A-Za-z0-9._~-]+", segment) is None
                for segment in path[1:].split("/")
            )
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "server_url must have a loopback host, port and safe base path"
        ) from None
    return f"http://{host}:{port}{path}"
