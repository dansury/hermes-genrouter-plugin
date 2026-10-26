"""GenRouter.ru provider profile for Hermes Agent."""

from .catalog import profile


def observe_error(error, **context):
    """Native Hermes inference failures: capture metadata, leave classification to Hermes."""
    try:
        from .account.reports import safe_capture
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None) or {}
        body = context.get("body") if isinstance(context.get("body"), dict) else {}
        metadata = {"status": context.get("status_code"),
                    "error_code": context.get("error_code"),
                    "request_id": headers.get("x-request-id") or body.get("request_id"),
                    "retry_after": headers.get("retry-after"),
                    "model": context.get("model"), "endpoint": "/v1"}
        # SDK exception strings can include prompts/provider bodies; use metadata only.
        report = safe_capture(error, action="inference", metadata=metadata,
                              message_override=getattr(error, "type_name", type(error).__name__) + ": GenRouter inference failed")
        if report:
            import logging
            logging.getLogger("genrouter").warning("GenRouter error recorded. Help improve the product: "
                                                  "hermes genrouter report send --id %s (preview and consent required)",
                                                  report["fingerprint"])
    except Exception:
        pass
    return None


profile.classify_api_error = observe_error
