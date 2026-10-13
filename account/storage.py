"""Profile-scoped credential storage; Windows secrets use current-user DPAPI."""

import base64
import ctypes
import json
import os
from pathlib import Path
import tempfile


def hermes_home():
    """Use the public plugin storage helper inside Hermes, portable defaults otherwise."""
    try:
        from plugins.plugin_storage import plugin_data_dir
    except ImportError:
        if os.environ.get("HERMES_HOME"):
            return Path(os.environ["HERMES_HOME"]).expanduser()
        if os.name == "nt":
            return Path(os.environ["LOCALAPPDATA"]) / "hermes"
        return Path.home() / ".hermes"
    return plugin_data_dir("genrouter-account").parent.parent


def _dpapi(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                          ctypes.POINTER(Blob)]
    operation.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError(ctypes.get_last_error(), "Windows credential protection failed")
    try:
        return ctypes.string_at(result.data, result.length)
    finally:
        kernel.LocalFree(result.data)


def private_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)
    handle, temporary = tempfile.mkstemp(prefix=".genrouter-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SecretStore:
    def __init__(self, home=None):
        self.home = Path(home) if home else hermes_home()
        self.path = self.home / "plugin-data" / "genrouter-account" / "credentials.secrets"

    def load(self):
        if not self.path.exists():
            return {"cookies": [], "keys": {}}
        wrapper = json.loads(self.path.read_text(encoding="utf-8"))
        data = base64.b64decode(wrapper["payload"])
        if wrapper["format"] == "dpapi-v1":
            if os.name != "nt":
                raise ValueError("This credential store belongs to a Windows user")
            data = _dpapi(data, decrypt=True)
        elif wrapper["format"] != "private-file-v1":
            raise ValueError("Unsupported credential-store format")
        return json.loads(data)

    def save(self, state):
        data = json.dumps(state).encode("utf-8")
        kind = "private-file-v1"
        if os.name == "nt":
            data = _dpapi(data)
            kind = "dpapi-v1"
        wrapper = {"format": kind, "payload": base64.b64encode(data).decode("ascii")}
        private_write(self.path, json.dumps(wrapper).encode("utf-8"))

    def install_key(self, value):
        """Change only this provider's variable; preserve every unrelated .env line."""
        if not isinstance(value, str) or not value or any(c in value for c in "\r\n\x00"):
            raise ValueError("Invalid API key")
        path = self.home / ".env"
        original = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        lines = original.splitlines()
        replacement = "GENROUTER_API_KEY=" + json.dumps(value)
        found = False
        updated = []
        for line in lines:
            if line.strip().startswith("GENROUTER_API_KEY="):
                if not found:
                    updated.append(replacement)
                    found = True
            else:
                updated.append(line)
        if not found:
            updated.append(replacement)
        private_write(path, ("\n".join(updated) + "\n").encode("utf-8"))
        os.environ["GENROUTER_API_KEY"] = value
