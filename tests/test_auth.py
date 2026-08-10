import importlib
import sys

import pytest


def test_secret_key_is_required_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    sys.modules.pop("backend.api.auth", None)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        importlib.import_module("backend.api.auth")
