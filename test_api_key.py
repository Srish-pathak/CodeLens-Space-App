from reviewer import get_client, get_deepseek_client
import pytest
from unittest.mock import patch


def test_get_client_requires_key_when_env_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="GEMINI_API_KEY not found"):
        get_client()


def test_get_client_uses_environment_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "environment-key")

    with patch("reviewer.genai.Client") as client:
        get_client()

    client.assert_called_once_with(api_key="environment-key")


def test_get_client_uses_streamlit_secret(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("reviewer.st.secrets", {"GEMINI_API_KEY": "secret-key"})

    with patch("reviewer.genai.Client") as client:
        get_client()

    client.assert_called_once_with(api_key="secret-key")


def test_get_deepseek_client_requires_key_when_env_missing(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with patch("reviewer.st.secrets", {}), pytest.raises(
        EnvironmentError,
        match="DEEPSEEK_API_KEY not found",
    ):
        get_deepseek_client()


def test_get_deepseek_client_uses_environment_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-deepseek-key")

    with patch("reviewer.OpenAI") as client:
        get_deepseek_client()

    client.assert_called_once_with(
        api_key="environment-deepseek-key",
        base_url="https://api.deepseek.com",
        timeout=60.0,
        max_retries=1,
    )


def test_get_deepseek_client_uses_streamlit_secret(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with patch("reviewer.st.secrets", {"DEEPSEEK_API_KEY": "secret-deepseek-key"}):
        with patch("reviewer.OpenAI") as client:
            get_deepseek_client()

    client.assert_called_once_with(
        api_key="secret-deepseek-key",
        base_url="https://api.deepseek.com",
        timeout=60.0,
        max_retries=1,
    )
