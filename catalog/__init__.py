"""Catalog-safe GenRouter provider; live discovery uses only Hermes-supplied credentials."""
import json
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from providers import register_provider
from providers.base import ProviderProfile


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GenRouterProvider(ProviderProfile):
    """Keep catalog parsing independent of Hermes internal catalog helpers."""

    def fetch_models(self, *, api_key=None, base_url=None, timeout=8.0, **context):
        """Return live chat model IDs, or None so Hermes can use its offline fallback."""
        if not api_key:
            return None
        endpoint = (base_url or self.base_url).rstrip("/") + "/models"
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        request = Request(endpoint, headers={
            "Authorization": "Bearer " + api_key,
            "Accept": "application/json",
            "User-Agent": "hermes-genrouter-plugin/0.3.2",
        })
        try:
            with build_opener(_NoRedirects()).open(request, timeout=timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return None
            payload = json.loads(raw)
            rows = payload if isinstance(payload, list) else payload.get("data", payload.get("models"))
            if not isinstance(rows, list):
                return None
            result = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                model_id = row.get("id")
                if isinstance(model_id, str) and model_id.strip() and model_id not in result:
                    result.append(model_id)
            return result or None
        except (OSError, ValueError, TypeError, AttributeError):
            return None


profile = GenRouterProvider(
    name="genrouter-ru",
    aliases=("genrouter.ru",),
    api_mode="chat_completions",
    display_name="GenRouter",
    description="GenRouter.ru - OpenAI-compatible inference",
    signup_url="https://genrouter.ru/?ref=d97a170843",
    env_vars=("GENROUTER_API_KEY",),
    base_url="https://api.genrouter.ru/v1",
    auth_type="api_key",
    fallback_models=("anthropic/claude-opus-5",),
)
register_provider(profile)
