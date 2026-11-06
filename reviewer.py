import os
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import streamlit as st
from google import genai
from streamlit.errors import StreamlitSecretNotFoundError

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
except ImportError:
    APIConnectionError = APIStatusError = APITimeoutError = OpenAI = None

from complexity import analyze_complexity
from local_checks import run_local_checks
from static_analysis import analyze_static
from syntax_checker import check_syntax
from utils import safe_json_parse

MODEL_NAME = "gemini-2.5-flash"
DEEPSEEK_MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MAX_SOURCE_CHARACTERS = 40_000
LOGGER = logging.getLogger(__name__)


class MissingAIConfigurationError(EnvironmentError):
    """Raised when a selected provider has no API credential."""


def get_secret(name: str) -> str | None:
    """Read a named Streamlit secret without propagating missing-secrets errors."""
    try:
        value = st.secrets.get(name)
    except (KeyError, StreamlitSecretNotFoundError, AttributeError, FileNotFoundError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None

SYSTEM_PROMPT = """
You are an experienced senior software engineer and security-focused code reviewer.

You ALWAYS respond with ONLY ONE VALID JSON OBJECT.
Never return markdown.
Analyze the complete source code before identifying any finding.
Report only evidence-based bugs, vulnerabilities, edge cases, performance issues,
maintainability problems, and practical improvements.
Do not invent line numbers, vulnerabilities, or problems that are unsupported by the code.
Explain every finding in beginner-friendly language and provide a technically correct fix.
For each issue in bugs or improvements, use the fields:
"title", "severity" (Critical/High/Medium/Low), "category", "file",
"line", "explanation", "why_it_matters", "suggested_solution", "corrected_code".

Schema:

{
  "summary":"",
  "bugs":[
    {
      "line":"",
      "severity":"",
      "description":""
    }
  ],
  "improvements":[
    {
      "title":"",
      "detail":""
    }
  ],
  "complexity_notes":"",
  "improved_code":"",
  "overall_score":8
}

Rules
- Return JSON only.
- improved_code should contain COMPLETE runnable code when a correction is useful.
- bugs may include security vulnerabilities only when evidence is present.
- Line numbers must refer to the supplied source. Use "N/A" when unavailable.
- Keep "overall_score" and "complexity_notes" transparent and evidence-based.
- Keep suggestions practical and educational.
- Don't invent bugs.
"""
def get_client() -> genai.Client:
    """Create a Gemini client using environment or Streamlit credentials."""
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        api_key = get_secret("GEMINI_API_KEY")

    if not api_key:
        raise MissingAIConfigurationError(
            "GEMINI_API_KEY not found. Set it as an environment variable "
            "or in Streamlit secrets."
        )

    return genai.Client(api_key=api_key)


def get_deepseek_client() -> Any:
    """Create an OpenAI-compatible client configured for DeepSeek."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        api_key = get_secret("DEEPSEEK_API_KEY")
    if not api_key:
        raise MissingAIConfigurationError(
            "DEEPSEEK_API_KEY not found. Set it as an environment variable "
            "or in Streamlit secrets."
        )
    if OpenAI is None:
        raise ImportError("The openai package is required for DeepSeek reviews.")

    return OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        timeout=60.0,
        max_retries=1,
    )


def _selected_ai_provider() -> str:
    """Select an explicitly configured provider, defaulting to the available key."""
    configured = os.getenv("AI_PROVIDER", "").strip().lower()
    if configured in {"deepseek", "gemini"}:
        return configured
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if get_secret("DEEPSEEK_API_KEY"):
        return "deepseek"
    return "gemini"


def _safe_diagnostic(exc: Exception) -> str:
    """Return exception text with credentials and authorization headers removed."""
    text = "{}: {}".format(type(exc).__name__, exc)
    text = re.sub(r"(?i)(api[_ -]?key|authorization|bearer)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1<redacted>", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "<redacted>", text)
    return text[:500]


def _provider_error_message(exc: Exception, provider: str) -> tuple[str, str]:
    """Return a safe provider name, status, and message without exposing credentials."""
    text = "{} {}".format(type(exc).__name__, exc)
    lowered = text.lower()
    provider_name = "DeepSeek" if provider == "deepseek" else "Gemini"
    status_code = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    status = str(status_code or code or "")
    diagnostic = _safe_diagnostic(exc)
    LOGGER.warning("%s provider error: %s", provider_name, diagnostic)

    if isinstance(exc, MissingAIConfigurationError) or (
        ("api key" in lowered or "api_key" in lowered)
        and "not found" in lowered
    ):
        return (
            "{} API key is not configured in the environment or Streamlit secrets. "
            "Static analysis is still available.".format(provider_name),
            "missing_configuration",
        )

    if (
        "429" in text
        or status == "429"
        or "resource_exhausted" in lowered
        or "rate limit" in lowered
        or "quota" in lowered
    ):
        return (
            "{} rate limit or quota reached. Static analysis is still available.".format(provider_name),
            "rate_limited",
        )
    if "insufficient balance" in lowered or "credit balance is not enough" in lowered:
        return (
            "{} account has insufficient balance. Add account credit or use another configured provider.".format(provider_name),
            "insufficient_balance",
        )
    invalid_response = (
        ("empty" in lowered and "response" in lowered)
        or "incomplete response" in lowered
        or "could not parse model response" in lowered
    )
    if invalid_response:
        return (
            "{} returned an invalid or incomplete response. Static analysis is still available.".format(provider_name),
            "invalid_response",
        )
    if "invalid api key" in lowered:
        return (
            "The configured {} API key is invalid. Static analysis is still available.".format(provider_name),
            "invalid_api_key",
        )
    if (
        "401" in text
        or "403" in text
        or status in {"401", "403", "PERMISSION_DENIED"}
        or "permission_denied" in lowered
        or "authentication" in lowered
        or "incorrect api key" in lowered
    ):
        return (
            "{} access was denied. Check the API key and account permissions.".format(provider_name),
            "permission_denied",
        )
    is_timeout = (
        APITimeoutError is not None and isinstance(exc, APITimeoutError)
    ) or isinstance(exc, TimeoutError)
    if "timeout" in lowered or "timed out" in lowered or is_timeout:
        return (
            "{} timed out while generating the review. Static analysis is still available.".format(provider_name),
            "timeout",
        )
    is_connection_error = (
        APIConnectionError is not None
        and isinstance(exc, APIConnectionError)
    )
    if isinstance(exc, ConnectionError) or is_connection_error:
        return (
            "Could not connect to {}. Static analysis is still available.".format(provider_name),
            "network_error",
        )
    return (
        "{} review is currently unavailable. Static analysis is still available.".format(provider_name),
        "unavailable",
    )


def _call_ai(code: str, language: str, provider: str, file_name: str = "<input>") -> str:
    """Call the selected AI provider and return its response text."""
    prompt = build_user_prompt(code, language, file_name)
    if provider == "deepseek":
        client = get_deepseek_client()
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=DEEPSEEK_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=4000,
                    response_format={"type": "json_object"},
                )
                break
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                transient = status in {408, 409, 429, 500, 502, 503, 504}
                if not transient or attempt == 2:
                    raise
                time.sleep(0.5 * (2 ** attempt))
        try:
            return response.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError):
            raise ValueError("DeepSeek returned an empty or incomplete response.")

    client = get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )
    return getattr(response, "text", None) or ""


def probe_deepseek_connectivity() -> dict[str, Any]:
    """Make a real, minimal DeepSeek API request and return non-secret status data."""
    try:
        client = get_deepseek_client()
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL_NAME,
            messages=[
                {"role": "system", "content": "Return one valid JSON object only."},
                {"role": "user", "content": '{"status":"connected"}'},
            ],
            max_tokens=100,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek returned an empty connectivity response.")
        parsed = safe_json_parse(content)
        if parsed.get("error"):
            raise ValueError(parsed["summary"])
        return {
            "connected": True,
            "provider": "DeepSeek",
            "model": DEEPSEEK_MODEL_NAME,
            "base_url": DEEPSEEK_BASE_URL,
            "response": parsed,
        }
    except Exception as exc:
        LOGGER.warning("DeepSeek connectivity test failed: %s", _safe_diagnostic(exc))
        error, status = _provider_error_message(exc, "deepseek")
        return {
            "connected": False,
            "provider": "DeepSeek",
            "model": DEEPSEEK_MODEL_NAME,
            "base_url": DEEPSEEK_BASE_URL,
            "status": status,
            "error": error,
        }


def build_user_prompt(code: str, language: str, file_name: str = "<input>") -> str:
    """Build the provider-neutral source-review prompt."""
    source = code
    if len(source) > MAX_SOURCE_CHARACTERS:
        source = (
            source[:MAX_SOURCE_CHARACTERS]
            + "\n\n[TRUNCATED: source exceeded the review input limit of 40,000 characters]"
        )
    return f"""
Review this {language} source file carefully.

File name: {file_name}

Code:

```{language.lower()}
{source}
```

Return your review strictly as the JSON schema described in your instructions."""


def review_code(
    code: str,
    language: str,
    file_name: str = "<input>",
    provider: str | None = None,
) -> dict[str, Any]:
    """Run syntax, static, and Gemini review analysis for one code sample."""
    if not code or not code.strip():
        return {
            "bugs": [],
            "improvements": [],
            "complexity_notes": "N/A",
            "overall_score": 0,
            "improved_code": "",
            "summary": "No code was provided to review.",
            "error": True,
            "analysis_status": {"static": "failed", "ai": "not_run"},
        }

    syntax_result = check_syntax(code, language)
    if not syntax_result.get("valid", True):
        syntax_bugs = syntax_result.get("bugs", [])
        if isinstance(syntax_bugs, dict):
            syntax_bugs = [syntax_bugs]
        return {
            "summary": "Syntax error detected.",
            "bugs": syntax_bugs,
            "improvements": [],
            "complexity_notes": "Fix syntax errors before reviewing.",
            "improved_code": "",
            "overall_score": 1,
            "static_analysis": {"syntax": syntax_result, "findings": syntax_bugs},
            "complexity_notes": "Fix syntax errors before reviewing.",
            "analysis_status": {"static": "completed_with_errors", "ai": "not_run"},
        }

    static_bugs = sorted(
        analyze_static(code, language) + run_local_checks(code, language),
        key=lambda item: item["line"] if isinstance(item.get("line"), int) else 0,
    )
    complexity = analyze_complexity(code, language)

    provider = provider or _selected_ai_provider()
    provider_name = "DeepSeek" if provider == "deepseek" else "Gemini"

    # Provider failures are kept separate from static analysis so deterministic
    # findings remain available even when the AI service is unavailable.
    try:
        response_text = _call_ai(code, language, provider, file_name)
        if not response_text:
            raise ValueError("{} returned an empty or incomplete response.".format(provider_name))
        ai_result = safe_json_parse(response_text)
        if ai_result.get("error"):
            raise ValueError(ai_result["summary"])
        _validate_ai_result(ai_result, file_name)
        result = ai_result
    except Exception as exc:
        if (
            provider == "deepseek"
            and os.getenv("AUTO_AI_FALLBACK", "").strip().lower() in {"1", "true", "yes"}
        ):
            try:
                gemini_key = os.getenv("GEMINI_API_KEY")
                if not gemini_key:
                    try:
                        gemini_key = st.secrets.get("GEMINI_API_KEY")
                    except (KeyError, StreamlitSecretNotFoundError, AttributeError):
                        gemini_key = None
                if gemini_key:
                    response_text = _call_ai(code, language, "gemini", file_name)
                    if not response_text:
                        raise ValueError("Gemini returned an empty or incomplete response.")
                    ai_result = safe_json_parse(response_text)
                    if ai_result.get("error"):
                        raise ValueError(ai_result["summary"])
                    _validate_ai_result(ai_result, file_name)
                    result = ai_result
                    result["provider_used"] = "Gemini fallback"
                    result["primary_provider_error"] = _safe_diagnostic(exc)
                    result["static_analysis"] = {"syntax": syntax_result, "findings": static_bugs}
                    result["complexity"] = complexity
                    result["analysis_status"] = {"static": "completed", "ai": "completed"}
                    result["ai_findings"] = list(result.get("bugs", []))
                    result["bugs"] = static_bugs + result.get("bugs", [])
                    return result
            except Exception as fallback_exc:
                LOGGER.warning(
                    "Gemini fallback failed after DeepSeek error: %s",
                    _safe_diagnostic(fallback_exc),
                )
        message, ai_status = _provider_error_message(exc, provider)
        return {
            "bugs": static_bugs,
            "improvements": [],
            "complexity_notes": "N/A",
            "overall_score": 0,
            "improved_code": "",
            "summary": "AI Review Unavailable — {}".format(message),
            "error": True,
            "static_analysis": {"syntax": syntax_result, "findings": static_bugs},
            "complexity": complexity,
            "analysis_status": {"static": "completed", "ai": ai_status},
            "ai_findings": [],
        }

    result["ai_findings"] = list(result.get("bugs", []))
    result["bugs"] = static_bugs + result.get("bugs", [])
    result["static_analysis"] = {"syntax": syntax_result, "findings": static_bugs}
    result["complexity"] = complexity
    result["analysis_status"] = {"static": "completed", "ai": "completed"}
    return result


def _validate_ai_result(result: dict[str, Any], file_name: str) -> None:
    """Validate provider-neutral review fields without changing the public schema."""
    required = {
        "summary",
        "bugs",
        "improvements",
        "complexity_notes",
        "improved_code",
        "overall_score",
    }
    missing = required.difference(result)
    if missing:
        raise ValueError("AI response is missing required fields: {}".format(", ".join(sorted(missing))))
    if not isinstance(result["summary"], str) or not isinstance(result["complexity_notes"], str):
        raise ValueError("AI response contains invalid text fields.")
    if not isinstance(result["bugs"], list) or not isinstance(result["improvements"], list):
        raise ValueError("AI response bugs and improvements must be arrays.")
    if not isinstance(result["improved_code"], str):
        raise ValueError("AI response improved_code must be text.")
    try:
        score = float(result["overall_score"])
    except (TypeError, ValueError) as exc:
        raise ValueError("AI response overall_score must be numeric.") from exc
    if not 0 <= score <= 10:
        raise ValueError("AI response overall_score must be between 0 and 10.")

    for finding in result["bugs"] + result["improvements"]:
        if not isinstance(finding, dict):
            raise ValueError("AI findings must be objects.")
        severity = finding.get("severity")
        if severity is not None:
            legacy_severity = str(severity).strip().lower()
            normalized = {
                "warning": "Medium",
                "info": "Low",
                "critical": "Critical",
                "high": "High",
                "medium": "Medium",
                "low": "Low",
            }.get(legacy_severity, legacy_severity.title())
            if normalized.lower() not in {
            "critical", "high", "medium", "low"
            }:
                raise ValueError("AI finding contains an invalid severity.")
            finding["severity"] = normalized
        finding.setdefault("file", file_name)
        finding.setdefault("line", "N/A")


def review_repo_files(
    files: list[dict[str, Any]],
    progress_callback: Callable[[int, int, str], None] | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Review fetched files individually, reusing ``review_code`` for each.

    ``files`` is a sequence of dictionaries with path, language, and content.
    The optional callback receives (completed, total, current_path).
    """
    total = len(files)
    results = []
    score_values = []
    critical_count = 0
    warning_count = 0
    improvement_count = 0
    failed_count = 0
    ai_failed_count = 0

    for index, file_info in enumerate(files, start=1):
        path = file_info.get("path", "<unknown>")
        language = file_info.get("language", "")
        code = file_info.get("content", "")
        try:
            review = review_code(code, language, path, provider)
            if not isinstance(review, dict):
                raise TypeError("The reviewer returned an invalid result.")
        except Exception as exc:
            review = {
                "summary": "Review failed: {}".format(exc),
                "bugs": [],
                "improvements": [],
                "complexity_notes": "Not available because the file review failed.",
                "overall_score": 0,
                "improved_code": "",
                "error": True,
                "analysis_status": {"static": "failed", "ai": "not_run"},
            }

        bugs = review.get("bugs", [])
        if isinstance(bugs, dict):
            bugs = [bugs]
        if not isinstance(bugs, list):
            bugs = []
        review["bugs"] = bugs

        complexity = None
        if language == "Python":
            try:
                complexity = analyze_complexity(code, language)
            except Exception as exc:
                complexity = {"error": "Complexity analysis failed: {}".format(exc)}

        for bug in bugs:
            severity = str(bug.get("severity", "info")).lower() if isinstance(bug, dict) else "info"
            if severity in {"critical", "high"}:
                critical_count += 1
            elif severity in {"warning", "medium"}:
                warning_count += 1
        improvements = review.get("improvements", [])
        if isinstance(improvements, list):
            improvement_count += len(improvements)

        is_error = bool(review.get("error"))
        if is_error:
            ai_status = review.get("analysis_status", {}).get("ai")
            if ai_status not in {None, "not_run"}:
                ai_failed_count += 1
            else:
                failed_count += 1
        else:
            try:
                score_values.append(float(review.get("overall_score", 0)))
            except (TypeError, ValueError):
                pass

        results.append({
            "path": path,
            "language": language,
            "content": code,
            "review": review,
            "complexity": complexity,
        })
        if progress_callback:
            progress_callback(index, total, path)

    return {
        "files_reviewed": len(results),
        "critical_bugs": critical_count,
        "warnings": warning_count,
        "improvement_count": improvement_count,
        "failed_files": failed_count,
        "ai_failed_files": ai_failed_count,
        "overall_score": round(sum(score_values) / len(score_values), 1) if score_values else None,
        "file_results": results,
    }
