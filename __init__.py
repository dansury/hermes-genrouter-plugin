"""GenRouter.ru provider profile for Hermes Agent."""

from providers import register_provider
from providers.base import ProviderProfile


def observe_error(error, **context):
    """Native Hermes inference failures: capture metadata, leave classification to Hermes."""
    try:
        from .account.reports import safe_capture
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", {})
        metadata = {"status": context.get("status_code"),
                    "error_code": context.get("error_code"),
                    "request_id": headers.get("x-request-id"),
                    "retry_after": headers.get("retry-after"),
                    "model": context.get("model"), "endpoint": "/v1"}
        # SDK exception strings can include prompts/provider bodies; use metadata only.
        report = safe_capture(error, action="inference", metadata=metadata,
                              message_override=type(error).__name__ + ": GenRouter inference failed")
        if report:
            import logging
            logging.getLogger("genrouter").warning("GenRouter error recorded. Help improve the product: "
                                                  "hermes genrouter report send --id %s (preview and consent required)",
                                                  report["fingerprint"])
    except Exception:
        pass
    return None


register_provider(
    ProviderProfile(
        name="genrouter-ru",
        aliases=("genrouter.ru",),
        api_mode="chat_completions",
        classify_api_error=observe_error,
        display_name="GenRouter",
        description="GenRouter.ru - OpenAI-compatible inference",
        signup_url="https://genrouter.ru/",
        env_vars=("GENROUTER_API_KEY",),
        base_url="https://api.genrouter.ru/v1",
        auth_type="api_key",
        fallback_models=("anthropic/claude-opus-5",),
    )
)
