"""B.2 skeleton tests.

Verify every Phase B.2 package imports cleanly and the placeholder
constants/classes exist. Real behavior tests land alongside the
features they cover (B.3 onward).
"""

import importlib

import pytest

PACKAGES = [
    "app",
    "app.api",
    "app.api.main",
    "app.api.routes",
    "app.domain",
    "app.storage",
    "app.schemas",
    "app.config",
    "app.config.settings",
    "app.audit",
]


@pytest.mark.parametrize("package", PACKAGES)
def test_package_imports(package: str) -> None:
    importlib.import_module(package)


def test_app_version_is_string() -> None:
    import app

    assert isinstance(app.__version__, str)
    assert len(app.__version__) > 0


def test_api_prefix_constant() -> None:
    from app.api.main import API_PREFIX, API_VERSION

    assert API_VERSION == "v1"
    assert API_PREFIX == "/api/v1"


def test_settings_instantiates() -> None:
    from app.config.settings import get_settings

    settings = get_settings()
    assert settings is not None
