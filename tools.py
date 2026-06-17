"""The MCP tools this server exposes.

Two examples:

  1. ``roll_dice``     - a plain, ordinary tool that returns text.
  2. ``greeting_card`` - an "MCP App": a tool that also returns a small HTML UI
                         which the Connext platform renders inline in the chat.

Both run *as the authenticated user*. Because we stamped the username onto the
access token in ``auth.py``, any tool can read it with ``get_access_token()``.
"""

from __future__ import annotations

import secrets

from mcp.types import EmbeddedResource, TextContent, TextResourceContents

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools.tool import ToolResult

# An MCP App is just a tool whose result includes a `ui://` resource carrying
# HTML with this special media type. The platform renders it in a sandboxed
# iframe. (This matches Connext's MCP Apps / SEP-1865 support.)
CARD_URI = "ui://acme/greeting-card"
CARD_MIME = "text/html;profile=mcp-app"


def _current_user() -> str:
    """Return the username on the current access token (or 'guest')."""
    token = get_access_token()
    return token.subject if (token and token.subject) else "guest"


def _render_card(username: str, message: str) -> str:
    """Build the self-contained HTML for the greeting card.

    Notes for the iframe sandbox:
      * Everything is inline (no external scripts/styles) so it renders under a
        strict Content-Security-Policy.
      * The ``var(--mcp-color-*, ...)`` fallbacks let the card pick up the
        host's light/dark theme automatically, with sane defaults standalone.
    """
    # Escape the few values we interpolate into HTML.
    safe_user = username.replace("<", "&lt;").replace("&", "&amp;")
    safe_msg = message.replace("<", "&lt;").replace("&", "&amp;")
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body {{ font-family: system-ui, sans-serif; margin: 0; }}
      .card {{
        margin: 1rem; padding: 1.25rem 1.5rem; border-radius: 12px;
        border: 1px solid var(--mcp-color-border, #e3e3e8);
        background: var(--mcp-color-surface, #ffffff);
        color: var(--mcp-color-text, #1a1a1a);
      }}
      .label {{ font-size: .7rem; letter-spacing: .05em; text-transform: uppercase; opacity: .55; }}
      .hello {{ font-size: 1.4rem; font-weight: 600; margin: .3rem 0 .1rem; }}
      .msg {{ font-size: 1rem; opacity: .85; }}
    </style>
  </head>
  <body>
    <div class="card">
      <div class="label">Acme greeting</div>
      <div class="hello">Hello, {safe_user}! 👋</div>
      <div class="msg">{safe_msg}</div>
    </div>
  </body>
</html>"""


def register_tools(mcp: FastMCP) -> None:
    """Register all tools and UI resources on the FastMCP app."""

    # --- 1. A plain tool -------------------------------------------------
    @mcp.tool(
        name="roll_dice",
        description="Roll an n-sided dice and return the result.",
    )
    async def roll_dice(sides: int = 6) -> str:
        sides = max(2, sides)
        result = secrets.randbelow(sides) + 1
        return f"{_current_user()} rolled a {result} (1–{sides})."

    # --- 2. An MCP App: a tool that returns an HTML UI -------------------
    # The `meta.ui` block on the tool DEFINITION tells the host this tool has a
    # UI and where its template lives. `visibility` is advisory — the Connext
    # admin still has to allow UI for this server.
    @mcp.tool(
        name="greeting_card",
        description="Greet the signed-in user with a small interactive card.",
        meta={"ui": {"resourceUri": CARD_URI, "visibility": ["model", "app"]}},
    )
    async def greeting_card(message: str = "Welcome to the Acme MCP server.") -> ToolResult:
        user = _current_user()
        html = _render_card(user, message)
        # The result carries BOTH a normal text part (what the model reads) AND
        # an embedded `ui://` resource with the HTML (what the user sees).
        ui_resource = EmbeddedResource(
            type="resource",
            resource=TextResourceContents(uri=CARD_URI, mimeType=CARD_MIME, text=html),
        )
        return ToolResult(
            content=[
                TextContent(type="text", text=f"Showed a greeting card to {user}."),
                ui_resource,
            ],
            # Free-form data a richer UI could read over the host bridge.
            structured_content={"username": user, "message": message},
        )

    # The UI template, also served via resources/read. `meta.ui.csp` lets the
    # host widen the iframe's Content-Security-Policy if your UI needs to reach
    # external domains (none here).
    @mcp.resource(
        CARD_URI,
        name="greeting-card",
        mime_type=CARD_MIME,
        meta={"ui": {"csp": {"connectDomains": [], "resourceDomains": []}, "prefersBorder": True}},
    )
    async def greeting_card_template() -> str:
        return _render_card("there", "This card is filled in when the tool runs.")
