"""API key storage in the macOS Keychain (via ``keyring``), env var as fallback."""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

SERVICE = "lecture-notes"
ENV_VARS = {"anthropic": "ANTHROPIC_API_KEY"}


def _account(provider: str) -> str:
    return f"{provider}-api-key"


def get_api_key(provider: str) -> str | None:
    try:
        key = keyring.get_password(SERVICE, _account(provider))
    except KeyringError:
        key = None
    if key:
        return key
    env = ENV_VARS.get(provider)
    return os.environ.get(env) if env else None


def set_api_key(provider: str, key: str) -> None:
    keyring.set_password(SERVICE, _account(provider), key)
