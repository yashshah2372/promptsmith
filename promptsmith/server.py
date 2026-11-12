"""PromptSmith: a remote MCP server plus a small REST API for the Chrome extension.

One process serves:
  /mcp           MCP over streamable HTTP (Claude connectors, ChatGPT apps, any MCP client)
  /v1/keys       POST  - create a free account, returns an API key (shown once)
  /v1/profile    GET/PUT - read or save the caller's profile
  /v1/enhance    POST  - rough request in, finished prompt out (what the extension calls)
  /health        GET

Every route except /health and /v1/keys needs `Authorization: Bearer <api key>`.
"""
from __future__ import annotations

import os

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import library
from .enhancer import PROFILE_FIELDS, Enhancer
from .store import QuotaExceeded, Store, User

MAX_REQUEST_CHARS = 2000


class EnhanceResult(BaseModel):
    prompt: str
    template: str
    remaining_today: int


class Profile(BaseModel):
    business: str = ""
    audience: str = ""
    voice: str = ""
    goals: str = ""


class ProfileResult(BaseModel):
    profile: Profile


class TemplateInfo(BaseModel):
    id: str
    title: str


class TemplatesResult(BaseModel):
    templates: list[TemplateInfo]


class ApiKeyVerifier:
    """Accepts PromptSmith API keys as bearer tokens.

    It implements the MCP SDK's TokenVerifier protocol, so swapping in a full OAuth 2.1
    authorization server later changes this class and nothing else.
    """

    def __init__(self, store: Store, resource_url: str):
        self._store = store
        self._resource_url = resource_url

    async def verify_token(self, token: str) -> AccessToken | None:
        user = self._store.user_for_key(token)
        if not user:
            return None
        return AccessToken(
            token=token, client_id="promptsmith", scopes=["prompts"], subject=user.id, resource=self._resource_url
        )


def _clean_profile(raw: dict) -> dict:
    return {k: str(raw[k]).strip()[:500] for k in PROFILE_FIELDS if raw.get(k)}


def create_app(store: Store, enhancer: Enhancer, public_url: str, host: str = "127.0.0.1"):
    mcp_url = public_url.rstrip("/") + "/mcp"
    mcp = MCPServer(
        "promptsmith",
        title="PromptSmith",
        instructions=(
            "Call enhance_prompt with the user's rough request to get a complete, expert-level prompt "
            "built from their saved profile. Use save_profile once to store their business, audience, voice and goals."
        ),
        token_verifier=ApiKeyVerifier(store, mcp_url),
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=mcp_url,
            required_scopes=["prompts"],
            validate_token_resource=True,
        ),
    )

    def current_user() -> User:
        token = get_access_token()
        user = store.user_for_key(token.token) if token else None
        if not user:
            raise ToolError("Not signed in.")
        return user

    async def run_enhance(user: User, request: str, template_id: str | None) -> dict:
        request = request.strip()
        if not request:
            raise ValueError("request is empty")
        if len(request) > MAX_REQUEST_CHARS:
            raise ValueError(f"request is longer than {MAX_REQUEST_CHARS} characters")
        remaining = store.consume(user)
        result = await enhancer.enhance(request, store.get_profile(user.id), template_id)
        return {"prompt": result.prompt, "template": result.template_id, "remaining_today": remaining}

    # ---- MCP tools -------------------------------------------------------------------------

    @mcp.tool(title="Enhance a prompt")
    async def enhance_prompt(request: str, template: str | None = None) -> EnhanceResult:
        """Turn a rough request (e.g. "LinkedIn post about my launch, keep it short") into a complete,
        expert-level prompt using the user's saved profile and the prompt library. Optionally force a
        template id from list_templates."""
        try:
            return EnhanceResult(**await run_enhance(current_user(), request, template))
        except (QuotaExceeded, ValueError) as e:
            raise ToolError(str(e)) from e

    @mcp.tool(title="Save profile")
    async def save_profile(
        business: str = "", audience: str = "", voice: str = "", goals: str = ""
    ) -> ProfileResult:
        """Save the user's business, target audience, writing voice and goals. Used by every enhancement."""
        profile = _clean_profile({"business": business, "audience": audience, "voice": voice, "goals": goals})
        store.save_profile(current_user().id, profile)
        return ProfileResult(profile=Profile(**profile))

    @mcp.tool(title="Get profile")
    async def get_profile() -> ProfileResult:
        """Return the user's saved profile (empty if none yet)."""
        return ProfileResult(profile=Profile(**(store.get_profile(current_user().id) or {})))

    @mcp.tool(title="List templates")
    async def list_templates() -> TemplatesResult:
        """List the prompt library's templates (id and title)."""
        return TemplatesResult(templates=[TemplateInfo(id=t.id, title=t.title) for t in library.LIBRARY])

    # ---- REST API for the Chrome extension -------------------------------------------------
    # custom_route handlers skip the SDK's auth middleware, so each one checks the key itself.

    def rest_user(request: Request) -> User | None:
        auth = request.headers.get("authorization", "")
        return store.user_for_key(auth[7:]) if auth.lower().startswith("bearer ") else None

    def unauthorized() -> JSONResponse:
        return JSONResponse({"error": "missing or invalid API key"}, status_code=401)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @mcp.custom_route("/v1/keys", methods=["POST"])
    async def create_key(_: Request) -> JSONResponse:
        if os.environ.get("PROMPTSMITH_OPEN_SIGNUP", "1") != "1":
            return JSONResponse({"error": "sign-up is closed"}, status_code=403)
        user, key = store.create_user()
        return JSONResponse({"api_key": key, "plan": user.plan}, status_code=201)

    @mcp.custom_route("/v1/profile", methods=["GET", "PUT"])
    async def profile(request: Request) -> JSONResponse:
        user = rest_user(request)
        if not user:
            return unauthorized()
        if request.method == "PUT":
            store.save_profile(user.id, _clean_profile(await request.json()))
        return JSONResponse({"profile": store.get_profile(user.id) or {}})

    @mcp.custom_route("/v1/enhance", methods=["POST"])
    async def enhance(request: Request) -> JSONResponse:
        user = rest_user(request)
        if not user:
            return unauthorized()
        body = await request.json()
        try:
            return JSONResponse(await run_enhance(user, str(body.get("request", "")), body.get("template")))
        except QuotaExceeded as e:
            return JSONResponse({"error": str(e)}, status_code=429)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    return mcp.streamable_http_app(host=host)


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}")
    app = create_app(Store(os.environ.get("PROMPTSMITH_DB", "promptsmith.db")), Enhancer(), public_url, host=host)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
