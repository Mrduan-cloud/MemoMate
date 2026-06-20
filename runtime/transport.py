"""Config-driven transport runtime shared by every MemoMate MCP server.

Each server's ``main()`` calls :func:`run_server` instead of ``mcp.run()``.
This gives every server — the core memory store and all utility servers — a
uniform, config-driven choice of MCP transport, while keeping **stdio as the
default** so existing stdio client configurations keep working unchanged.

Why this exists
---------------
The Model Context Protocol defines several transports. Phase 1 shipped every
MemoMate server over **stdio** (one subprocess per client, no network surface).
To support *remote* and *multi-client* access, this module lets any server also
speak **Streamable HTTP** — the transport the 2025 MCP spec standardizes on — or
the older, now-deprecated **HTTP+SSE**, all selected at launch time without any
code change.

Selection precedence (highest wins)
-----------------------------------
1. CLI flags:   ``--transport`` / ``--host`` / ``--port`` / ``--path``
2. Environment: ``MEMOMATE_TRANSPORT`` / ``MEMOMATE_HOST`` / ``MEMOMATE_PORT`` /
   ``MEMOMATE_HTTP_PATH``
3. Defaults:    ``stdio``; HTTP binds ``127.0.0.1:8000``, Streamable HTTP path
   ``/mcp``, SSE path ``/sse``.

The resolve/apply steps are split out as pure, side-effect-free functions so the
whole selection logic is unit-testable offline (no socket required); only
:func:`run_server` actually binds a port.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from mcp.server.fastmcp import FastMCP

Transport = Literal["stdio", "sse", "streamable-http"]

_TRANSPORTS: tuple[Transport, ...] = ("stdio", "sse", "streamable-http")
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000
# Per-transport default URL path (mirrors FastMCP's own settings defaults).
_DEFAULT_PATH: dict[str, str] = {"streamable-http": "/mcp", "sse": "/sse"}

_ENV_TRANSPORT = "MEMOMATE_TRANSPORT"
_ENV_HOST = "MEMOMATE_HOST"
_ENV_PORT = "MEMOMATE_PORT"
_ENV_PATH = "MEMOMATE_HTTP_PATH"


@dataclass(frozen=True)
class TransportConfig:
    """A fully resolved transport choice for one server launch.

    ``path`` is ``None`` for stdio (which has no URL surface); for the HTTP
    transports it is the request path the server is mounted at.
    """

    transport: Transport
    host: str
    port: int
    path: str | None


def _env_get(env: Mapping[str, str], name: str) -> str | None:
    """Return ``env[name]`` treating an empty/whitespace value as unset."""
    val = env.get(name)
    if val is None:
        return None
    val = val.strip()
    return val or None


def _coerce_port(raw: str, *, origin: str) -> int:
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid {origin} {raw!r}: must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"Invalid {origin} {port}: must be in 1..65535")
    return port


def _normalize_path(path: str) -> str:
    """Ensure a mount path is a single leading-slash, no trailing-slash route."""
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def resolve_transport_config(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> TransportConfig:
    """Resolve a :class:`TransportConfig` from CLI args + environment.

    ``argv`` defaults to ``sys.argv[1:]`` (via argparse) and ``env`` to
    ``os.environ``. CLI flags win over environment variables, which win over the
    built-in defaults. Raises :class:`ValueError` for an unknown transport or an
    out-of-range / non-integer port, so misconfiguration fails fast rather than
    silently falling back.
    """
    env = os.environ if env is None else env

    parser = argparse.ArgumentParser(
        prog="memomate-server",
        description="Run a MemoMate MCP server over the chosen transport.",
    )
    parser.add_argument("--transport", choices=_TRANSPORTS, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--path", default=None)
    args = parser.parse_args(argv)

    transport = args.transport or _env_get(env, _ENV_TRANSPORT) or "stdio"
    if transport not in _TRANSPORTS:
        allowed = ", ".join(_TRANSPORTS)
        raise ValueError(f"Unknown transport {transport!r}; choose one of: {allowed}")

    host = args.host or _env_get(env, _ENV_HOST) or _DEFAULT_HOST

    if args.port is not None:
        port = _coerce_port(str(args.port), origin="--port")
    elif (env_port := _env_get(env, _ENV_PORT)) is not None:
        port = _coerce_port(env_port, origin=_ENV_PORT)
    else:
        port = _DEFAULT_PORT

    if transport == "stdio":
        path = None  # stdio has no URL surface; ignore any path that was set
    else:
        raw_path = args.path or _env_get(env, _ENV_PATH) or _DEFAULT_PATH[transport]
        path = _normalize_path(raw_path)

    return TransportConfig(transport=transport, host=host, port=port, path=path)


def apply_transport_config(mcp: FastMCP, config: TransportConfig) -> None:
    """Push an HTTP :class:`TransportConfig` onto a FastMCP instance's settings.

    A no-op for stdio (which ignores host/port/path). For the HTTP transports it
    sets ``host``/``port`` and the transport-appropriate mount path so the server
    binds where the config says.
    """
    if config.transport == "stdio":
        return
    mcp.settings.host = config.host
    mcp.settings.port = config.port
    if config.transport == "streamable-http":
        mcp.settings.streamable_http_path = config.path
    elif config.transport == "sse":
        mcp.settings.sse_path = config.path


def run_server(mcp: FastMCP, argv: Sequence[str] | None = None) -> None:
    """Resolve transport from CLI/env, apply it, and run ``mcp`` (blocking).

    This is the single entry point every server's ``main()`` calls in place of
    ``mcp.run()``. With no flags / env it runs stdio exactly as before, so the
    change is backward compatible for existing stdio client configs.
    """
    config = resolve_transport_config(argv)
    apply_transport_config(mcp, config)
    mcp.run(transport=config.transport)
