from types import SimpleNamespace
from unittest.mock import patch

import pytest

from complexity import analyze_complexity
from reviewer import review_code, review_repo_files, probe_deepseek_connectivity
from static_analysis import analyze_static
from syntax_checker import check_syntax
from utils import safe_json_parse


@pytest.fixture(autouse=True)
def clear_ai_provider_environment(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)


def _successful_client(content):
    client = SimpleNamespace()
    client.models = SimpleNamespace(
        generate_content=lambda **kwargs: SimpleNamespace(text=content)
    )
    return client


def _successful_deepseek_client(content):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[choice]))
        )
    )


def test_valid_python_source_keeps_static_analysis_successful():
    with patch("reviewer.get_client", return_value=_successful_client(
        '{"summary":"Looks good","bugs":[],"improvements":[],"complexity_notes":"","overall_score":8,"improved_code":""}'
    )):
        result = review_code("def add(a, b):\n    return a + b\n", "Python")

    assert result["analysis_status"]["static"] == "completed"
    assert result["analysis_status"]["ai"] == "completed"
    assert result["bugs"] == []


def test_invalid_python_syntax_skips_gemini():
    with patch("reviewer.get_client") as client:
        result = review_code("def broken(:\n    pass\n", "Python")

    client.assert_not_called()
    assert result["analysis_status"]["static"] == "completed_with_errors"
    assert result["analysis_status"]["ai"] == "not_run"
    assert result["bugs"][0]["severity"] == "critical"


def test_empty_source_is_not_analyzed():
    result = review_code("   \n", "Python")
    assert result["error"] is True
    assert result["analysis_status"]["static"] == "failed"


def test_high_complexity_python_is_measured():
    code = """def complex_function(value):
    if value > 0:
        if value > 10:
            return 3
        return 2
    return 1
"""
    result = analyze_complexity(code, "Python")
    assert result["details"][0]["name"] == "complex_function"
    assert result["details"][0]["complexity"] >= 3


def test_static_analysis_accepts_default_and_keyword_arguments():
    code = """def greet(name, punctuation="!"):
    return name + punctuation

greet("Ada")
greet(name="Ada", punctuation="?")
"""
    assert analyze_static(code, "Python") == []


def test_syntax_error_is_returned_as_a_bug_list():
    result = check_syntax("def broken(:\n", "Python")
    assert isinstance(result["bugs"], list)
    assert result["bugs"][0]["severity"] == "critical"


def test_model_json_is_extracted_from_fenced_response():
    result = safe_json_parse(
        'Response:\n```json\n{"summary":"Valid","bugs":[],"improvements":[],"overall_score":8}\n```\n'
    )
    assert result["summary"] == "Valid"


def test_non_python_complexity_is_explicitly_unsupported():
    result = analyze_complexity("const value = 1;", "JavaScript")
    assert result["status"] == "unsupported"


def test_static_analysis_respects_positional_only_and_variadic_arguments():
    code = """def collect(first, /, second=0, *extra, required, **options):
    return first

collect(1, required=2)
collect(1, 2, 3, required=4, mode="fast")
"""
    assert analyze_static(code, "Python") == []

    invalid = """def collect(first, /, required):
    return first

collect(required=1)
collect(1, 2, 3)
"""
    assert analyze_static(invalid, "Python")


@pytest.mark.parametrize(
    ("error_text", "expected_status"),
    [
        ("429 RESOURCE_EXHAUSTED", "rate_limited"),
        ("403 PERMISSION_DENIED", "permission_denied"),
    ],
)
def test_gemini_permission_and_quota_errors_are_isolated(error_text, expected_status):
    def fail(**kwargs):
        raise RuntimeError(error_text)

    client = SimpleNamespace(models=SimpleNamespace(generate_content=fail))
    with patch("reviewer.get_client", return_value=client):
        result = review_code("print('hello')\n", "Python")

    assert result["analysis_status"]["static"] == "completed"
    assert result["analysis_status"]["ai"] == expected_status
    assert result["summary"].startswith("AI Review Unavailable")
    assert result["overall_score"] == 0


def test_invalid_gemini_response_is_unavailable():
    with patch("reviewer.get_client", return_value=_successful_client("not json")):
        result = review_code("print('hello')\n", "Python")

    assert result["analysis_status"]["ai"] == "invalid_response"


def test_successful_ai_review_is_preserved():
    content = (
        '{"summary":"Potential issue","bugs":[{"line":1,"severity":"warning",'
        '"description":"Check this value"}],"improvements":[],"complexity_notes":"Simple",'
        '"overall_score":7,"improved_code":"print(1)"}'
    )
    with patch("reviewer.get_client", return_value=_successful_client(content)):
        result = review_code("print(value)\n", "Python")

    assert result["summary"] == "Potential issue"
    assert result["overall_score"] == 7
    assert result["improved_code"] == "print(1)"


def test_partial_repository_review_counts_ai_failure_separately():
    files = [
        {"path": "good.py", "language": "Python", "content": "print('ok')\n"},
        {"path": "bad.py", "language": "Python", "content": "print('ok')\n"},
    ]

    successful = {
        "summary": "Review complete",
        "bugs": [],
        "improvements": [],
        "overall_score": 8,
        "improved_code": "",
        "analysis_status": {"static": "completed", "ai": "completed"},
    }
    unavailable = {
        "summary": "AI Review Unavailable",
        "bugs": [],
        "improvements": [],
        "overall_score": 0,
        "improved_code": "",
        "error": True,
        "analysis_status": {"static": "completed", "ai": "rate_limited"},
    }
    with patch("reviewer.review_code", side_effect=[successful, unavailable]):
        result = review_repo_files(files)

    assert result["files_reviewed"] == 2
    assert result["failed_files"] == 0
    assert result["ai_failed_files"] == 1
    assert result["overall_score"] == 8.0


def test_successful_deepseek_review(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    content = (
        '{"summary":"DeepSeek review","bugs":[],"improvements":[],"complexity_notes":"Simple",'
        '"overall_score":8,"improved_code":"print(1)"}'
    )
    with patch("reviewer.get_deepseek_client", return_value=_successful_deepseek_client(content)):
        result = review_code("print(1)\n", "Python")

    assert result["summary"] == "DeepSeek review"
    assert result["overall_score"] == 8
    assert result["analysis_status"]["ai"] == "completed"


def test_deepseek_missing_key_is_unavailable(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    with patch("reviewer.st.secrets", {}):
        result = review_code("print(1)\n", "Python")

    assert result["analysis_status"]["static"] == "completed"
    assert result["analysis_status"]["ai"] == "missing_configuration"
    assert result["summary"].startswith("AI Review Unavailable")


def test_deepseek_malformed_json_is_unavailable(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    with patch(
        "reviewer.get_deepseek_client",
        return_value=_successful_deepseek_client("not json"),
    ):
        result = review_code("print(1)\n", "Python")

    assert result["analysis_status"]["ai"] == "invalid_response"


def test_deepseek_invalid_api_key_is_unavailable(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    def fail(**kwargs):
        raise RuntimeError("401 invalid api key")

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fail)
        )
    )
    with patch("reviewer.get_deepseek_client", return_value=client):
        result = review_code("print(1)\n", "Python")

    assert result["analysis_status"]["ai"] == "invalid_api_key"


def test_deepseek_request_parameters_and_response_schema(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        content = (
            '{"summary":"Reviewed","bugs":[{"line":1,"severity":"warning",'
            '"description":"Improve it"}],"improvements":[{"title":"Rename",'
            '"detail":"Use a clearer name"}],"complexity_notes":"Low complexity",'
            '"overall_score":7,"improved_code":"print(2)"}'
        )
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    with patch("reviewer.get_deepseek_client", return_value=client):
        result = review_code("print(1)\n", "Python")

    assert calls["model"] == "deepseek-flash"
    assert calls["response_format"] == {"type": "json_object"}
    assert calls["max_tokens"] == 4000
    assert result["summary"] == "Reviewed"
    assert result["bugs"]
    assert result["improvements"]
    assert result["complexity_notes"] == "Low complexity"
    assert result["overall_score"] == 7
    assert result["improved_code"] == "print(2)"


def test_deepseek_insufficient_balance_is_distinct(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    def fail(**kwargs):
        raise RuntimeError("402 insufficient balance")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fail))
    )
    with patch("reviewer.get_deepseek_client", return_value=client):
        result = review_code("print(1)\n", "Python")

    assert result["analysis_status"]["ai"] == "insufficient_balance"


def test_deepseek_timeout_is_distinct(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    def fail(**kwargs):
        raise TimeoutError("DeepSeek request timed out")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fail))
    )
    with patch("reviewer.get_deepseek_client", return_value=client):
        result = review_code("print(1)\n", "Python")

    assert result["analysis_status"]["ai"] == "timeout"


def test_explicit_gemini_fallback(monkeypatch):
    monkeypatch.setenv("AUTO_AI_FALLBACK", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    gemini_result = (
        '{"summary":"Gemini fallback","bugs":[],"improvements":[],"complexity_notes":"Simple",'
        '"overall_score":8,"improved_code":"print(1)"}'
    )

    with patch("reviewer._call_ai", side_effect=["", gemini_result]):
        result = review_code("print(1)\n", "Python", provider="deepseek")

    assert result["provider_used"] == "Gemini fallback"
    assert result["summary"] == "Gemini fallback"


def test_repository_review_uses_selected_provider(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    files = [{"path": "main.py", "language": "Python", "content": "print(1)\n"}]

    with patch("reviewer.review_code", return_value={
        "summary": "DeepSeek reviewed",
        "bugs": [],
        "improvements": [],
        "overall_score": 8,
        "improved_code": "",
        "analysis_status": {"static": "completed", "ai": "completed"},
    }) as review:
        review_repo_files(files, provider="deepseek")

    review.assert_called_once_with("print(1)\n", "Python", "main.py", "deepseek")


def test_deepseek_connectivity_response_shape(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    client = _successful_deepseek_client('{"status":"connected"}')

    with patch("reviewer.get_deepseek_client", return_value=client):
        result = probe_deepseek_connectivity()

    assert result["connected"] is True
    assert result["provider"] == "DeepSeek"
    assert result["model"] == "deepseek-flash"
    assert result["response"]["status"] == "connected"


@pytest.mark.parametrize(
    ("error_text", "expected_status"),
    [
        ("429 insufficient balance", "rate_limited"),
        ("403 Permission denied", "permission_denied"),
    ],
)
def test_deepseek_api_errors_are_isolated(monkeypatch, error_text, expected_status):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    def fail(**kwargs):
        raise RuntimeError(error_text)

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fail)
        )
    )
    with patch("reviewer.get_deepseek_client", return_value=client):
        result = review_code("print(1)\n", "Python")

    assert result["analysis_status"]["static"] == "completed"
    assert result["analysis_status"]["ai"] == expected_status
