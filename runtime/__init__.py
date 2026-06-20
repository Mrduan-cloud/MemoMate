"""Shared transport runtime for all MemoMate MCP servers.

Servers call :func:`run_server` from their ``main()`` to gain a uniform,
config-driven choice of MCP transport (stdio by default; Streamable HTTP or SSE
for remote / multi-client access).
"""

from runtime.transport import (
    TransportConfig,
    apply_transport_config,
    resolve_transport_config,
    run_server,
)

__all__ = [
    "TransportConfig",
    "apply_transport_config",
    "resolve_transport_config",
    "run_server",
]
