import ast
from typing import Any


def check_syntax(code: str, language: str) -> dict[str, Any]:
    """Check Python syntax and return review-compatible bug data."""
    if language != "Python":
        return {
            "valid": True,
            "bugs": [],
        }
    
    try:
        ast.parse(code)
        return {
            "valid": True,
            "bugs": [],
        }
    except SyntaxError as error:
        return {
            "valid": False,
            "bugs": [
                {
                    "line": error.lineno,
                    "column": error.offset,
                    "severity": "critical",
                    "description": f"SyntaxError: {error.msg}",
                }
            ],
        }