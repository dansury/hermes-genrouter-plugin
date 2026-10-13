"""Owner-authorized, issue-only shared reporter credential.

This is reversible obfuscation, NOT secure encryption. Its authority is
intentionally distributed with the client. Never grant it code/admin access.
Users can override it with GENROUTER_ISSUE_TOKEN; revocation uses email fallback.
"""
import os

_PACKED = [58,52,41,53,40,63,2,45,60,41,2,108,108,28,104,106,111,7,8,20,109,48,101,40,111,56,44,107,36,48,43,107,37,2,107,100,4,100,50,4,11,108,50,17,60,59,37,12,44,50,39,101,20,107,108,26,31,50,58,50,107,19,39,7,7,19,22,25,23,49,4,4,106,57,105,106,8,31,27,17,12,9,17,104,7,56,51,24,60,49,104,106,53]


def shared_token():
    return os.environ.get("GENROUTER_ISSUE_TOKEN") or "".join(chr(n ^ 93) for n in _PACKED)
