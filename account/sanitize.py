"""Sanitize diagnostics before storage, preview and publication."""
import os
import re


def sanitize(value, secrets=()):
    text = str(value)
    values = list(secrets) + [v for k, v in os.environ.items()
                              if re.search(r"key|token|secret|password|cookie|authorization", k, re.I)]
    for secret in sorted((s for s in values if isinstance(s, str) and len(s) >= 4), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+|sk-[A-Za-z0-9_.-]+", "[redacted]", text)
    text = re.sub(r"(?i)(Bearer\s+)[^\s\"',;]+", r"\1[redacted]", text)
    text = re.sub(r'''(?im)(["']?(?:password|passwd|api[_-]?key|key|token|secret|code|cookie|set-cookie|authorization|genrouter_session)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\n,;}]+)''', r"\1[redacted]", text)
    text = re.sub(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"\b[0-9]{6}\b", "[code]", text)
    for path in (os.environ.get("USERPROFILE"), os.environ.get("HOME")):
        if path:
            text = text.replace(path, "[home]")
    return text
