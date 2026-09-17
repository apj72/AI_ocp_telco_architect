import pytest

from tps.architect.config import ArchitectConfig, provider_catalog
from tps.architect.service import backend_for
from tps.architect.claude_backend import ClaudeBackend
from tps.architect.openai_backend import OpenAIBackend


def test_provider_config_defaults_to_openai(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    config = ArchitectConfig.from_env()
    assert config.provider == "openai"
    assert config.model == "test-model"


def test_provider_config_supports_claude(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-test")
    config = ArchitectConfig.from_env(provider="claude")
    assert config.model == "claude-test"
    assert isinstance(backend_for(config), ClaudeBackend)


def test_provider_config_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        ArchitectConfig.from_env(provider="unknown")


def test_openai_backend_selected():
    config = ArchitectConfig.from_env(provider="openai")
    assert isinstance(backend_for(config), OpenAIBackend)


def test_provider_catalog_does_not_expose_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-value")
    rows = provider_catalog()
    assert {row["id"] for row in rows} == {"openai", "claude"}
    assert all("secret-test-value" not in str(row) for row in rows)
