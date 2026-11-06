import json
import re

LANGUAGE_CONFIG = {
    "Python": {"ace_mode": "python", "ext": ".py", "supports_radon": True},
    "C++": {"ace_mode": "c_cpp", "ext": ".cpp", "supports_radon": False},
    "Java": {"ace_mode": "java", "ext": ".java", "supports_radon": False},
    "JavaScript": {"ace_mode": "javascript", "ext": ".js", "supports_radon": False},
    "JSX": {"ace_mode": "jsx", "ext": ".jsx", "supports_radon": False},
    "TypeScript": {"ace_mode": "typescript", "ext": ".ts", "supports_radon": False},
    "TSX": {"ace_mode": "tsx", "ext": ".tsx", "supports_radon": False},
    "HTML": {"ace_mode": "html", "ext": ".html", "supports_radon": False},
    "CSS": {"ace_mode": "css", "ext": ".css", "supports_radon": False},
    "SCSS": {"ace_mode": "scss", "ext": ".scss", "supports_radon": False},
}

SEVERITY_STYLE={
    "critical": {"emoji": "🔴", "label": "Critical"},
    "high":     {"emoji": "🟠", "label": "High"},
    "warning":  {"emoji": "🟡", "label": "Warning"},
    "medium":   {"emoji": "🟡", "label": "Medium"},
    "low":      {"emoji": "🔵", "label": "Low"},
    "info":     {"emoji": "🔵", "label": "Info"},
}

def safe_json_parse(raw_text: str) -> dict:
    if not raw_text:
        return _fallback_response("Empty response from model.")

    cleaned = raw_text.strip()

    cleaned = re.sub(r"^```(?:[A-Za-z0-9_-]+)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("Model response JSON must be an object.")
        return _normalize_response(data)
    except (json.JSONDecodeError, ValueError) as direct_error:
        decoder = json.JSONDecoder()
        for index, character in enumerate(cleaned):
            if character not in "{[":
                continue
            try:
                data, _ = decoder.raw_decode(cleaned[index:])
                if isinstance(data, dict):
                    return _normalize_response(data)
            except json.JSONDecodeError:
                continue
        return _fallback_response(
            f"Could not parse model response: {direct_error}"
        )


def _normalize_response(data: dict) -> dict:
    """Ensure every expected key exists so app.py never KeyErrors."""
    if not isinstance(data, dict):
        raise ValueError("Model response JSON must be an object.")
    data.setdefault("bugs", [])
    data.setdefault("improvements", [])
    data.setdefault("complexity_notes", "No complexity notes provided.")
    data.setdefault("overall_score", 5)
    data.setdefault("improved_code", "")
    data.setdefault("summary", "")

    if not isinstance(data.get("bugs"), list):
        data["bugs"] = []
    if not isinstance(data.get("improvements"), list):
        data["improvements"] = []

    # Clamp score into 1-10 range defensively
    try:
        score = float(data["overall_score"])
        if score != score:
            raise ValueError
        data["overall_score"] = max(0, min(10, score))
    except (TypeError, ValueError):
        data["overall_score"] = 5

    return data


def _fallback_response(error_message: str) -> dict:
    return {
        "bugs": [],
        "improvements": [],
        "complexity_notes": "N/A",
        "overall_score": 0,
        "improved_code": "",
        "summary": error_message,
        "error": True,
    }


def score_color(score: float) -> str:
    """Return a color for progress bars / metrics based on score."""
    if score >= 8:
        return "green"
    if score >= 5:
        return "orange"
    return "red"


def score_label(score: float) -> str:
    if score >= 8:
        return "Excellent"
    if score >= 6:
        return "Good"
    if score >= 4:
        return "Needs Work"
    return "Poor"


def format_bug_entry(bug: dict) -> str:
    """Render a single bug dict into a readable markdown string."""
    severity = str(bug.get("severity", "info")).lower()
    style = SEVERITY_STYLE.get(severity, SEVERITY_STYLE["info"])
    line = bug.get("line", "N/A")
    desc = bug.get("description", "No description provided.")
    return f"{style['emoji']} **{style['label']}** (Line {line}): {desc}"


def format_improvement_entry(item: dict) -> str:
    title = item.get("title", "Suggestion")
    detail = item.get("detail", "")
    return f"💡 **{title}**\n\n{detail}"