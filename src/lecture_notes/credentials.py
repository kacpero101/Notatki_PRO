"""API key storage: a file only your user account can read, env var as fallback.

The key is kept in ``~/.config/lecture-notes/<provider>-api-key`` with permissions
600 (like ``~/.netrc`` or ``~/.aws/credentials``). Finder Quick Actions do not see
variables from the shell profile, so the environment variable is only a fallback
for the terminal.

Versions up to 0.1.0 kept the key in the macOS Keychain; the helpers at the end
let ``lecture-notes setup`` remove that old entry with the system ``security`` tool.
"""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

ENV_VARS = {"anthropic": "ANTHROPIC_API_KEY"}


def key_path(provider: str) -> Path:
    return config.CONFIG_DIR / f"{provider}-api-key"


def stored_api_key(provider: str) -> str | None:
    """The key saved by ``lecture-notes setup``, or None."""
    path = key_path(provider)
    try:
        key = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as e:
        log.warning("Cannot read %s: %s", path, e)
        return None
    if not key:
        return None
    _restrict_permissions(path)
    return key


def get_api_key(provider: str) -> str | None:
    key = stored_api_key(provider)
    if key:
        return key
    env = ENV_VARS.get(provider)
    return (os.environ.get(env) or None) if env else None


def set_api_key(provider: str, key: str) -> Path:
    path = key_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates the file with permissions 600, so the key is never readable by
    # others, not even for a moment; the rename keeps the old key if writing fails
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-key-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key.strip() + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def _restrict_permissions(path: Path) -> None:
    """Make a hand-made key file private (e.g. created with an editor as 644)."""
    try:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            path.chmod(0o600)
            log.warning("%s was readable by other users; permissions changed to 600", path)
    except OSError as e:
        log.warning("Cannot check permissions of %s: %s", path, e)


# --------------------------------------------------- old Keychain entry (≤ 0.1.0)

_SECURITY = Path("/usr/bin/security")
_KEYCHAIN_SERVICE = "lecture-notes"


def _keychain(command: str, provider: str) -> bool:
    if not _SECURITY.exists():
        return False
    args = [str(_SECURITY), command, "-s", _KEYCHAIN_SERVICE, "-a", f"{provider}-api-key"]
    try:
        return subprocess.run(args, capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def old_keychain_entry_exists(provider: str) -> bool:
    # without -g/-w the secret itself is not read, so macOS does not ask for a password
    return _keychain("find-generic-password", provider)


def delete_old_keychain_entry(provider: str) -> bool:
    return _keychain("delete-generic-password", provider)
