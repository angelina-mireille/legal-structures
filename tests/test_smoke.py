"""Smoke test: the three top-level packages import."""

import importlib

import pytest


@pytest.mark.parametrize("name", ["core", "perimeter", "downstream"])
def test_package_imports(name: str) -> None:
    """Each package can be imported."""
    assert importlib.import_module(name) is not None
