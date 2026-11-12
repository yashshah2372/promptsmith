# PromptSmith

Type a rough line like *"LinkedIn post about my launch, keep it short"* and get back a complete,
expert-level prompt built from your saved profile and a curated prompt library.

It works in two places from one backend:

- **Any MCP client** (Claude Code, Claude connectors, ChatGPT apps, MCP Inspector) through a
  **remote MCP server** over streamable HTTP.
- **ChatGPT, Claude and Gemini in Chrome** through a **Chrome extension** that adds a
  **✦ Enhance** button above the chat box.

Prompts are generated with **Claude Haiku** (`claude-haiku-5-5`) via the Anthropic API.

```
 Chrome extension ──REST /v1/enhance──┐
                                      ├──► PromptSmith server ──► Claude Haiku
 MCP clients ─────MCP /mcp (Bearer)───┘     │  profiles · library · daily quotas
                                            └── SQLite
```

## Features

- **MCP tools:** `enhance_prompt`, `save_profile`, `get_profile`, `list_templates`, each with a
  typed output schema.
- **Profiles:** business, audience, voice and goals, saved once and used on every request.
- **Prompt library:** expert guidance per request type (LinkedIn post, cold email, Instagram
  caption, product copy, blog post, general), matched by keyword or picked explicitly.
- **Plans and quotas:** a free plan with a daily limit (20/day) and a `pro` plan. `Store.set_plan`
  is the hook a Stripe webhook calls to upgrade a user.
- **Auth:** bearer API keys, stored as SHA-256 hashes, checked through the MCP SDK's
  `TokenVerifier` interface. The server publishes RFC 9728 protected-resource metadata, and
  unauthenticated MCP calls get a `401` with a `WWW-Authenticate` pointer.
- **Prompt-injection guard:** the rough request is passed to the model as data inside tags, and the
  system prompt tells the model to only rewrite it.
- **Extension:**
  - Works with ChatGPT's and Claude's ProseMirror editors, Gemini's Quill editor, and plain
    textareas.
  - Writes text through `insertText`, so each site's own editor state and Send button update.
  - Shows an Undo toast after each rewrite.
  - Keeps the API key in the background worker, never in the page.
  - Asks for host access only to the one server you configure.

## Run it locally

```bash
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
uv run promptsmith            # serves http://localhost:8000  (MCP at /mcp)
```

**Create a key:**

```bash
curl -X POST http://localhost:8000/v1/keys
```

**Connect Claude Code:**

```bash
claude mcp add --transport http promptsmith http://localhost:8000/mcp \
  --header "Authorization: Bearer ps_..."
```

**Load the extension:**
1. Open `chrome://extensions` and turn on Developer mode.
2. Click **Load unpacked** and choose `extension/`.
3. Open the extension's settings.
4. Click **Create a free key** and fill in your profile.

## REST API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/v1/keys` | none | Create a free account; returns the API key once |
| GET/PUT | `/v1/profile` | Bearer | Read or save the profile |
| POST | `/v1/enhance` | Bearer | `{"request": "..."}` → `{"prompt", "template", "remaining_today"}` |
| GET | `/health` | none | Liveness |

## Tests

```bash
uv run pytest
```

The tests cover:
- template matching
- auth
- profile isolation between users
- quotas and plan upgrades
- input limits
- a real MCP client calling every tool over HTTP against a live server

A fake Claude client stands in for the API, so the tests need no key.

## Deploy

```bash
docker build -t promptsmith .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... -e PUBLIC_URL=https://your.domain \
  -v promptsmith-data:/data promptsmith
```

This works on any host that runs a container (Fly.io, Render, Railway, ECS). Mount `/data` as a
volume so the SQLite database survives redeploys.

## Roadmap

- **OAuth 2.1 authorization server** (`OAuthAuthorizationServerProvider` in the MCP SDK). Claude.ai
  custom connectors and ChatGPT apps sign users in this way. Only `ApiKeyVerifier` changes; the
  tools stay the same.
- **Stripe Checkout and webhook**, calling `Store.set_plan`.
- **Postgres** in place of SQLite for multiple replicas.
