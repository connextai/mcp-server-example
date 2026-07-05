"""Entry point: build the FastMCP server, wire up auth + tools, and run it.

    python server.py

Configuration (all optional) comes from the environment — see .env.example:

    PUBLIC_URL   the URL the Connext platform uses to reach this server
                 (default http://localhost:8000). Everything in the OAuth
                 discovery documents is derived from this, so it must be correct
                 and publicly reachable in a real deployment.
    HOST / PORT  the address uvicorn binds to (default 127.0.0.1:8000).
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from fastmcp import FastMCP

from auth import DEMO_USERS, LoginOAuthProvider, register_login_routes
from tools import register_tools

PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# Scopes this server understands. Keep it to one for the example.
SCOPES = ["read"]

# The OAuth provider (authorization server) — see auth.py.
provider = LoginOAuthProvider(public_url=PUBLIC_URL, users=DEMO_USERS, scopes=SCOPES)

# The MCP server itself. Passing `auth=provider` makes FastMCP:
#   * require a valid bearer token on the /mcp endpoint, and
#   * serve the OAuth discovery + /authorize + /token + /register endpoints.
mcp = FastMCP("Acme MCP Example", auth=provider)

# Add our custom login page and register the example tools.
register_login_routes(mcp, provider)
register_tools(mcp)


# An unauthenticated liveness/readiness probe. The GKE Ingress BackendConfig and
# the Kubernetes probes hit GET /health; it must NOT require a bearer token, so
# it is a plain custom route outside the MCP auth surface.
@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


if __name__ == "__main__":
    # Streamable-HTTP transport; the MCP endpoint is served at <PUBLIC_URL>/mcp/
    mcp.run(transport="http", host=HOST, port=PORT)
