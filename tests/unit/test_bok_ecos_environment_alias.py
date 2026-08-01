"""Regression tests for the established Bank of Korea ECOS key name."""

from __future__ import annotations

import importlib

import pytest

import alpha_cycle
from alpha_cycle.providers.ecos import EcosCredentials


def test_bok_ecos_key_populates_process_compatibility_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    monkeypatch.setenv("BOK_ECOS_API_KEY", "bok-secret")

    importlib.reload(alpha_cycle)

    credentials = EcosCredentials.from_env()
    assert credentials.api_key == "bok-secret"


def test_existing_ecos_alias_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ECOS_API_KEY", "explicit-secret")
    monkeypatch.setenv("BOK_ECOS_API_KEY", "bok-secret")

    importlib.reload(alpha_cycle)

    credentials = EcosCredentials.from_env()
    assert credentials.api_key == "explicit-secret"
