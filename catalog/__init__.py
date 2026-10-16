"""Catalog-safe GenRouter provider profile for Hermes Agent.

Credentials are resolved by Hermes from the declared provider environment
variable; this package neither reads nor stores them itself.
"""

from providers import register_provider
from providers.base import ProviderProfile


register_provider(
    ProviderProfile(
        name="genrouter-ru",
        aliases=("genrouter.ru",),
        api_mode="chat_completions",
        display_name="GenRouter",
        description="GenRouter.ru - OpenAI-compatible inference",
        signup_url="https://genrouter.ru/",
        env_vars=("GENROUTER_API_KEY",),
        base_url="https://api.genrouter.ru/v1",
        auth_type="api_key",
        fallback_models=("anthropic/claude-opus-5",),
    )
)
