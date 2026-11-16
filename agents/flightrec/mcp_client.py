"""Minimal MCP (streamable HTTP) client for the read-only `relate serve`.

Only what the post-mortem needs: JSON-RPC handshake, tools/list, and calling
the `read_cypher` tool. A read-only serve does not list `write_cypher`, so
this client structurally cannot mutate the graph.
"""
import json

import httpx

# MCP over streamable HTTP wants both content types in Accept.
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _parse(resp: httpx.Response) -> dict:
    """Unwrap a JSON body or a single-data SSE event into a dict."""
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise RuntimeError("empty event stream")
    return resp.json()


class McpClient:
    """Tiny JSON-RPC session against the MCP endpoint, with basic auth."""

    def __init__(self, url: str, auth: str):
        user, _, password = auth.partition(":")
        self.url = url
        self.client = httpx.Client(auth=(user, password), headers=dict(HEADERS), timeout=60)
        self._id = 0
        self._initialized = False

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False) -> dict | None:
        """Send one JSON-RPC call (or notification); return `result`, if any."""
        body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self._id += 1
            body["id"] = self._id
        r = self.client.post(self.url, json=body)
        r.raise_for_status()
        # The server assigns a session id on initialize; echo it from then on.
        sid = r.headers.get("mcp-session-id")
        if sid:
            self.client.headers["mcp-session-id"] = sid
        if notify or not r.content:
            return None
        msg = _parse(r)
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg["result"]

    def _init(self) -> None:
        """MCP handshake (once per client): initialize + initialized notification."""
        if self._initialized:
            return
        self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "blackbox-postmortem", "version": "0.1"},
        })
        self._rpc("notifications/initialized", notify=True)
        self._initialized = True

    def tools(self) -> list[str]:
        """List the tools the server offers (diagnostics; should be read-only ones)."""
        self._init()
        return [t["name"] for t in self._rpc("tools/list")["tools"]]

    def read_cypher(self, statement: str, parameters: dict | None = None) -> list[dict]:
        """Run a read-only Cypher query via the `read_cypher` tool; return rows.

        Raises with the server's message on query errors (isError flag or an
        error field in the envelope) instead of misparsing the body as JSON.
        """
        self._init()
        res = self._rpc("tools/call", {
            "name": "read_cypher",
            "arguments": {"statement": statement, "parameters": parameters or {}},
        })
        text = res["content"][0]["text"]
        if res.get("isError"):
            raise RuntimeError(text)
        payload = json.loads(text)
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        return payload["rows"]
