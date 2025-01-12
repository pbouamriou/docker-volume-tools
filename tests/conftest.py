"""Configuration for pytest."""

import os
import pytest

@pytest.fixture(autouse=True)
def mock_env_home(monkeypatch, tmp_path):
    """Mock HOME environment to avoid touching real home directory."""
    monkeypatch.setenv("HOME", str(tmp_path)) 