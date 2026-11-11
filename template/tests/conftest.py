"""Isolation must happen before application imports during test collection."""

import os

os.environ["HARNESS_NO_DOTENV"] = "1"
os.environ.pop("EXAMPLE_SETTING", None)

import pytest


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text("{}")
    monkeypatch.setenv("APP_CONFIG_PATH", str(path))
    return path
