from typing import Any
from radon.complexity import cc_visit
from radon.metrics import mi_visit

def analyze_complexity(code: str, language: str) -> dict[str, Any] | None:
    """Analyze complexity for languages supported by the project."""
    if language == "Python":
        return _analyze_python(code)
    return {
        "method": "unsupported",
        "status": "unsupported",
        "supported": False,
        "language": language,
        "average_complexity": None,
        "rating": "N/A",
        "details": [],
        "maintainability_index": None,
        "error": f"Complexity analysis is not supported for {language} code.",
    }

def _analyze_python(code: str) -> dict[str, Any]:
    """Calculate Python cyclomatic complexity and maintainability."""
    if not code or not code.strip():
        return {
            "method": "radon",
            "status": "completed",
            "supported": True,
            "average_complexity": 0,
            "rating": "N/A",
            "details": [],
            "maintainability_index": 0.0,
            "error": "No source code was provided.",
        }
    try:
        blocks = cc_visit(code)
    except SyntaxError as e:
        return {
            "method": "radon",
            "status": "completed_with_errors",
            "supported": True,
            "average_complexity": 0,
            "rating": "N/A",
            "details": [],
            "maintainability_index": None,
            "error": f"Syntax error, could not analyze: {e}",
        }
    if not blocks:
        return {
            "method": "radon",
            "status": "completed",
            "supported": True,
            "average_complexity": 1,
            "rating": "A",
            "details": [],
            "maintainability_index": _safe_mi(code),
        }
    details = [
        {"name": b.name, "complexity": b.complexity, "rank": _rank_letter(b.complexity)}
        for b in blocks
    ]
    average_complexity = sum(
        block.complexity for block in blocks
    ) / len(blocks)

    return {
        "method": "radon",
        "status": "completed",
        "supported": True,
        "average_complexity": round(average_complexity, 2),
        "rating": _rank_letter(average_complexity),
        "details": details,
        "maintainability_index": _safe_mi(code),
    }


def _safe_mi(code: str) -> float | None:
    try:
        return round(mi_visit(code, multi=True), 2)
    except Exception:
        return None


def _rank_letter(complexity: float) -> str:
    if complexity <= 5:
        return "A"
    if complexity <= 10:
        return "B"
    if complexity <= 20:
        return "C"
    if complexity <= 30:
        return "D"
    if complexity <= 40:
        return "E"
    return "F"
