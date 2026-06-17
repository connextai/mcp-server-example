# mcp-server-example

A **minimal, well-commented MCP server** that connects to the Connext platform.

It demonstrates everything you need to build your own MCP server that your users
can connect to from Connext:

- 🔐 **Its own login & OAuth** — the server is its own OAuth 2.1 provider, with a
  simple username/password login page. A Connext user clicks "Connect", signs in
  to *your* server, and Connext receives an access token on their behalf.
- 🛠️ **An example tool** (`roll_dice`) — an ordinary tool that returns text.
- 🎨 **An example MCP App** (`greeting_card`) — a tool that returns a small HTML
  UI which Connext renders inline in the chat.
- 👤 **Per-user identity** — tools know *which* of your users is calling.

It is built on [FastMCP](https://gofastmcp.com), which handles the MCP protocol
and the standard OAuth plumbing, so the only code you have to understand is the
~150 lines that are specific to *your* application: your users, your login page,
and your tools.

---

## How it works

When a user connects this server in Connext, this is the flow (all standard
OAuth 2.1 — Connext drives it automatically):

```
  Connext platform                         This MCP server
  ────────────────                         ───────────────
  1. discover ─────────────────────────▶  GET /.well-known/oauth-protected-resource/mcp
                                           GET /.well-known/oauth-authorization-server
  2. register (RFC 7591) ──────────────▶  POST /register            ← no manual client setup
  3. send user to log in ──────────────▶  GET  /authorize
                                           └▶ redirects the user's browser to:
  4. user signs in ────────────────────▶  GET/POST /login           ← YOUR login page
  5. get a token ──────────────────────▶  POST /token
  6. call tools (Authorization: Bearer)▶  POST /mcp                  ← your tools run
```

You only write step 4 (the login page) and step 6 (the tools). FastMCP gives you
1, 2, 3 and 5 for free.

---

## Quick start

Requires Python 3.11+.

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. run the server
python server.py
# -> serving on http://localhost:8000  (MCP endpoint: http://localhost:8000/mcp/)

# 3. in another terminal, connect to it like a real client would
python examples/connect_with_client.py
# -> opens your browser to the login page; sign in as  alice / password123
```

Demo users live in `auth.py`:

| username | password      |
| -------- | ------------- |
| `alice`  | `password123` |
| `bob`    | `hunter2`     |

---

## Connecting it to Connext

1. **Expose the server on a public HTTPS URL.** Connext must be able to reach
   your server's OAuth discovery endpoints, and for security it **rejects
   private/loopback addresses** for those endpoints. For a quick test, tunnel
   your local server:

   ```bash
   # example with cloudflared / ngrok — any tunnel works
   ngrok http 8000
   ```

   Then run the server with `PUBLIC_URL` set to the tunnel URL, because every
   OAuth endpoint it advertises is built from `PUBLIC_URL`:

   ```bash
   PUBLIC_URL=https://your-tunnel.example.com python server.py
   ```

2. **Register it in Connext** (Admin → MCP Servers → Add):
   - **URL:** `https://your-tunnel.example.com/mcp`
   - **Transport:** `HTTP`
   - **Auth:** `OAuth`
   - Leave client id/secret **blank** — this server supports Dynamic Client
     Registration, so Connext registers itself automatically.
   - To let the `greeting_card` MCP App render, enable **Allow UI** on the server.

3. **Connect as a user.** Each user clicks **Connect**, signs in on your login
   page, and Connext stores their token. Now the agent can call `roll_dice` and
   `greeting_card` *as that user*.

---

## The files

| File | What it does |
| ---- | ------------ |
| `server.py` | Entry point. Reads config, builds the FastMCP server, wires in auth + tools, runs it. |
| `auth.py` | The OAuth provider. Subclasses FastMCP's in-memory provider and adds **one** thing: a real login page (`authorize()` → `/login`). Contains the demo user store. |
| `tools.py` | The two example tools and the `ui://` resource for the MCP App. |
| `examples/connect_with_client.py` | A standalone client that runs the same OAuth flow Connext does — handy for testing. |
| `.env.example` | Configuration (`PUBLIC_URL`, `HOST`, `PORT`). |

---

## What an MCP App is

An MCP App is just a tool whose result includes a `ui://` **resource** carrying
HTML. Connext renders that HTML in a sandboxed iframe inside the chat. The two
pieces (see `tools.py`):

```python
# 1. mark the tool as having a UI
@mcp.tool(meta={"ui": {"resourceUri": "ui://acme/greeting-card", ...}})
async def greeting_card(message: str) -> ToolResult:
    return ToolResult(
        content=[
            TextContent(text="..."),                         # what the model reads
            EmbeddedResource(resource=TextResourceContents(  # what the user sees
                uri="ui://acme/greeting-card",
                mimeType="text/html;profile=mcp-app",
                text="<!doctype html>...")),
        ],
        structured_content={"username": ..., "message": ...},
    )

# 2. also serve the template via resources/read
@mcp.resource("ui://acme/greeting-card", mime_type="text/html;profile=mcp-app", ...)
async def greeting_card_template() -> str:
    return "<!doctype html>..."
```

Keep the HTML self-contained (inline CSS, no external scripts) so it works under
the iframe's strict Content-Security-Policy. Use the `var(--mcp-color-*)` CSS
variables to match the host's light/dark theme.

---

## Taking it to production

This example keeps everything in memory so it's easy to read. For a real server:

- **Users:** replace the `DEMO_USERS` dict in `auth.py` with your real user
  database, and store **hashed** passwords (bcrypt/argon2) — or delegate to your
  existing SSO/identity provider.
- **Tokens:** `InMemoryOAuthProvider` keeps tokens in memory, so they are lost on
  restart (users would re-connect). For production, persist them or issue signed
  JWTs (`fastmcp.server.auth.providers.jwt`).
- **HTTPS:** terminate TLS in front of the server and set `PUBLIC_URL` to the
  `https://` URL.
- **Scopes:** this example uses a single `read` scope. Add scopes and enforce
  them per-tool via FastMCP's `required_scopes` / `auth` options.

---

## Verified flow

This example was tested end-to-end: dynamic client registration → login (wrong
password rejected, correct password accepted) → token exchange → authenticated
`tools/list` and `tools/call` → token refresh → rejection of unauthenticated
calls. Tools correctly see the signed-in user via `get_access_token().subject`.
