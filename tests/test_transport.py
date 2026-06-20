"""Tests for the shared transport runtime (runtime/transport.py).

The offline tests exercise the full config-resolution + apply + dispatch logic
without binding a socket. The single `@network`-marked test stands up a real
Streamable HTTP server on the loopback interface and round-trips the actual core
memory tools through the MCP client SDK — pure local evidence that the transport
layer works end to end (no external network, no model download).
"""

from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from runtime.transport import (
    TransportConfig,
    apply_transport_config,
    resolve_transport_config,
    run_server,
)


def _free_port() -> int:
    """Grab a currently-free TCP port on loopback for an ephemeral server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------------------------- #
# resolve_transport_config — defaults / precedence / validation               #
# --------------------------------------------------------------------------- #


def test_default_is_stdio_backward_compatible():
    cfg = resolve_transport_config(argv=[], env={})
    assert cfg == TransportConfig(
        transport="stdio", host="127.0.0.1", port=8000, path=None
    )


def test_env_selects_streamable_http_with_default_path():
    cfg = resolve_transport_config(argv=[], env={"MEMOMATE_TRANSPORT": "streamable-http"})
    assert cfg.transport == "streamable-http"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8000
    assert cfg.path == "/mcp"


def test_env_overrides_host_port_path():
    cfg = resolve_transport_config(
        argv=[],
        env={
            "MEMOMATE_TRANSPORT": "streamable-http",
            "MEMOMATE_HOST": "0.0.0.0",
            "MEMOMATE_PORT": "9001",
            "MEMOMATE_HTTP_PATH": "/memory",
        },
    )
    assert cfg == TransportConfig(
        transport="streamable-http", host="0.0.0.0", port=9001, path="/memory"
    )


def test_cli_flags_win_over_env():
    cfg = resolve_transport_config(
        argv=["--transport", "streamable-http", "--host", "1.2.3.4", "--port", "7000", "--path", "/x"],
        env={
            "MEMOMATE_TRANSPORT": "sse",
            "MEMOMATE_HOST": "0.0.0.0",
            "MEMOMATE_PORT": "9001",
            "MEMOMATE_HTTP_PATH": "/memory",
        },
    )
    assert cfg == TransportConfig(
        transport="streamable-http", host="1.2.3.4", port=7000, path="/x"
    )


def test_sse_uses_its_own_default_path():
    cfg = resolve_transport_config(argv=["--transport", "sse"], env={})
    assert cfg.transport == "sse"
    assert cfg.path == "/sse"


def test_stdio_ignores_any_configured_path():
    # stdio has no URL surface — a path from env must not leak through.
    cfg = resolve_transport_config(argv=[], env={"MEMOMATE_HTTP_PATH": "/whatever"})
    assert cfg.transport == "stdio"
    assert cfg.path is None


def test_empty_env_value_is_treated_as_unset():
    cfg = resolve_transport_config(
        argv=[], env={"MEMOMATE_TRANSPORT": "", "MEMOMATE_HOST": "   "}
    )
    assert cfg.transport == "stdio"
    assert cfg.host == "127.0.0.1"


def test_path_is_normalized_leading_slash_no_trailing():
    cfg = resolve_transport_config(
        argv=["--transport", "streamable-http", "--path", "memory/"], env={}
    )
    assert cfg.path == "/memory"


def test_unknown_env_transport_raises():
    with pytest.raises(ValueError, match="Unknown transport"):
        resolve_transport_config(argv=[], env={"MEMOMATE_TRANSPORT": "carrier-pigeon"})


def test_non_integer_env_port_raises():
    with pytest.raises(ValueError, match="must be an integer"):
        resolve_transport_config(argv=[], env={"MEMOMATE_PORT": "not-a-port"})


def test_out_of_range_env_port_raises():
    with pytest.raises(ValueError, match="1..65535"):
        resolve_transport_config(argv=[], env={"MEMOMATE_PORT": "70000"})


def test_invalid_cli_transport_choice_exits():
    # argparse rejects an out-of-choice value with SystemExit (exit code 2).
    with pytest.raises(SystemExit):
        resolve_transport_config(argv=["--transport", "smoke-signals"], env={})


# --------------------------------------------------------------------------- #
# apply_transport_config — settings mutation                                  #
# --------------------------------------------------------------------------- #


def _fake_mcp():
    return SimpleNamespace(
        settings=SimpleNamespace(
            host="127.0.0.1",
            port=8000,
            streamable_http_path="/mcp",
            sse_path="/sse",
        )
    )


def test_apply_streamable_http_sets_host_port_and_sh_path():
    mcp = _fake_mcp()
    apply_transport_config(
        mcp,
        TransportConfig(transport="streamable-http", host="0.0.0.0", port=9000, path="/memory"),
    )
    assert mcp.settings.host == "0.0.0.0"
    assert mcp.settings.port == 9000
    assert mcp.settings.streamable_http_path == "/memory"
    assert mcp.settings.sse_path == "/sse"  # untouched


def test_apply_sse_sets_sse_path():
    mcp = _fake_mcp()
    apply_transport_config(
        mcp, TransportConfig(transport="sse", host="0.0.0.0", port=9000, path="/events")
    )
    assert mcp.settings.sse_path == "/events"
    assert mcp.settings.streamable_http_path == "/mcp"  # untouched


def test_apply_stdio_is_a_noop():
    mcp = _fake_mcp()
    apply_transport_config(
        mcp, TransportConfig(transport="stdio", host="9.9.9.9", port=1, path=None)
    )
    assert mcp.settings.host == "127.0.0.1"
    assert mcp.settings.port == 8000


# --------------------------------------------------------------------------- #
# run_server — full dispatch (resolve -> apply -> run) without a socket         #
# --------------------------------------------------------------------------- #


def test_run_server_dispatches_streamable_http():
    calls = {}

    class FakeMCP:
        def __init__(self):
            self.settings = SimpleNamespace(
                host="127.0.0.1", port=8000, streamable_http_path="/mcp", sse_path="/sse"
            )

        def run(self, transport):
            calls["transport"] = transport

    mcp = FakeMCP()
    run_server(mcp, argv=["--transport", "streamable-http", "--port", "8200"])
    assert calls["transport"] == "streamable-http"
    assert mcp.settings.port == 8200
    assert mcp.settings.streamable_http_path == "/mcp"


def test_run_server_defaults_to_stdio():
    calls = {}

    class FakeMCP:
        def __init__(self):
            self.settings = SimpleNamespace(
                host="127.0.0.1", port=8000, streamable_http_path="/mcp", sse_path="/sse"
            )

        def run(self, transport):
            calls["transport"] = transport

    run_server(FakeMCP(), argv=[])
    assert calls["transport"] == "stdio"


# --------------------------------------------------------------------------- #
# Streamable HTTP app builds with applied config (no socket bound)             #
# --------------------------------------------------------------------------- #


def test_streamable_http_app_builds_from_applied_config():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("transport-test")

    @mcp.tool()
    def ping() -> str:
        return "pong"

    cfg = resolve_transport_config(
        argv=["--transport", "streamable-http", "--port", "8123", "--path", "/mcp"], env={}
    )
    apply_transport_config(mcp, cfg)
    app = mcp.streamable_http_app()
    assert app is not None
    assert mcp.settings.port == 8123
    assert mcp.settings.streamable_http_path == "/mcp"


# --------------------------------------------------------------------------- #
# Regression: store must be usable across threads (HTTP runs tools on workers)  #
# --------------------------------------------------------------------------- #


def test_store_is_usable_across_threads(tmp_path):
    """The store connection is created in one thread but, under the HTTP
    transports, FastMCP runs sync tool handlers on worker threads. This
    reproduces that hand-off and asserts no cross-thread sqlite error.
    """
    import threading

    from core.store import MemoryStore

    store = MemoryStore(tmp_path / "cross_thread.db")  # created in the main thread
    out: dict = {}

    def worker() -> None:
        out["id"] = store.save("cross-thread fact", tags=["transport"])
        out["found"] = store.search("fact")  # plain token; FTS5 treats '-' as syntax
        out["count"] = store.count()

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert out["id"] == 1
    assert out["found"] and out["found"][0]["content"] == "cross-thread fact"
    assert out["count"] == 1
    store.close()


# --------------------------------------------------------------------------- #
# Live loopback round-trip: real core memory server over Streamable HTTP        #
# --------------------------------------------------------------------------- #


def _result_text(result) -> str:
    return "\n".join(
        c.text for c in result.content if getattr(c, "type", None) == "text"
    )


async def _client_roundtrip(url: str) -> dict:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with (
        streamablehttp_client(url) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        save = await session.call_tool(
            "save_memory",
            {"content": "MemoMate speaks Streamable HTTP", "tags": ["transport", "test"]},
        )
        recall = await session.call_tool("recall_memory", {"query": "Streamable"})
        stats = await session.call_tool("memory_stats", {})
        return {
            "tools": [t.name for t in tools.tools],
            "save": _result_text(save),
            "recall": _result_text(recall),
            "stats": _result_text(stats),
        }


@pytest.mark.network
def test_core_memory_server_over_streamable_http(tmp_path, monkeypatch):
    """The real core server, served over Streamable HTTP, round-trips via the SDK.

    Pure loopback: starts uvicorn in a background thread, points the memory store
    at an isolated temp DB, then connects with the MCP client and verifies a
    save -> recall -> stats round-trip.
    """
    import importlib
    import threading
    import time

    import anyio
    import uvicorn

    monkeypatch.setenv("MEMOMATE_DB_PATH", str(tmp_path / "mem.db"))

    import core.server

    importlib.reload(core.server)  # rebind module-level _store to the temp DB
    mcp = core.server.mcp

    port = _free_port()
    cfg = resolve_transport_config(
        argv=["--transport", "streamable-http", "--host", "127.0.0.1", "--port", str(port), "--path", "/mcp"],
        env={},
    )
    apply_transport_config(mcp, cfg)
    app = mcp.streamable_http_app()

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 15
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        assert server.started, "uvicorn server did not start in time"

        out = anyio.run(_client_roundtrip, f"http://127.0.0.1:{port}/mcp")
    finally:
        server.should_exit = True
        thread.join(timeout=15)

    assert "save_memory" in out["tools"]
    assert "recall_memory" in out["tools"]
    assert "memory_stats" in out["tools"]
    assert "saved" in out["save"]
    assert "Streamable HTTP" in out["recall"]
    assert '"total_memories": 1' in out["stats"]
