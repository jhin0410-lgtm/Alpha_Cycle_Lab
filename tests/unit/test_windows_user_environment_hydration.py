"""Regression tests for direct Python runs from stale Windows shells."""

from __future__ import annotations

from alpha_cycle import _hydrate_windows_user_environment
from alpha_cycle.providers.ecos import EcosCredentials
from alpha_cycle.providers.opendart import OpenDartCredentials
from alpha_cycle.providers.tossinvest import TossInvestCredentials


def test_saved_user_credentials_hydrate_a_direct_python_process() -> None:
    saved = {
        "TOSSINVEST_CLIENT_ID": "saved-client",
        "TOSSINVEST_CLIENT_SECRET": "saved-secret",
        "OPENDART_API_KEY": "saved-dart",
        "BOK_ECOS_API_KEY": "saved-bok",
    }
    environ: dict[str, str] = {}

    _hydrate_windows_user_environment(environ, reader=saved.get)

    assert TossInvestCredentials.from_env(environ).client_id == "saved-client"
    assert TossInvestCredentials.from_env(environ).client_secret == "saved-secret"
    assert OpenDartCredentials.from_env(environ).api_key == "saved-dart"
    assert EcosCredentials.from_env(environ).api_key == "saved-bok"
    assert environ["ECOS_API_KEY"] == "saved-bok"


def test_process_credentials_override_saved_user_values() -> None:
    environ = {
        "TOSSINVEST_CLIENT_ID": "process-client",
        "TOSSINVEST_CLIENT_SECRET": "process-secret",
        "OPENDART_API_KEY": "process-dart",
        "BOK_ECOS_API_KEY": "process-bok",
        "ECOS_API_KEY": "explicit-ecos",
    }
    saved = {name: f"saved-{name}" for name in environ}

    _hydrate_windows_user_environment(environ, reader=saved.get)

    assert environ["TOSSINVEST_CLIENT_ID"] == "process-client"
    assert environ["TOSSINVEST_CLIENT_SECRET"] == "process-secret"
    assert environ["OPENDART_API_KEY"] == "process-dart"
    assert environ["BOK_ECOS_API_KEY"] == "process-bok"
    assert environ["ECOS_API_KEY"] == "explicit-ecos"
