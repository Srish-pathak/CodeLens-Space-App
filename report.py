"""Build downloadable Markdown / JSON reports from review results."""

import json
from datetime import datetime
from typing import Any


def _bug_line(bug: dict[str, Any]) -> str:
    return "- **{}** (line {}): {}".format(
        str(bug.get("severity", "info")).title(),
        bug.get("line", "N/A"),
        bug.get("description") or bug.get("explanation") or bug.get("title") or "No description.",
    )


def build_markdown_report(
    result: dict[str, Any],
    complexity: dict[str, Any] | None,
    language: str,
    source: str,
) -> str:
    """Render a single-file review as Markdown."""
    status = result.get("analysis_status", {})
    lines = [
        "# CodeLens Review Report",
        "",
        "_Generated {}_".format(datetime.now().strftime("%Y-%m-%d %H:%M")),
        "",
        "- Language: {}".format(language),
        "- AI status: {}".format(status.get("ai", "unknown")),
    ]
    if status.get("ai") == "completed":
        lines.append("- Overall score: {}/10".format(result.get("overall_score", "N/A")))
    lines += ["", "## Summary", "", result.get("summary") or "No summary available.", "", "## Findings", ""]
    bugs = result.get("bugs", [])
    lines += [_bug_line(b) for b in bugs if isinstance(b, dict)] or ["No findings."]
    lines += ["", "## Improvements", ""]
    tips = [t for t in result.get("improvements", []) if isinstance(t, dict)]
    lines += ["- **{}** — {}".format(t.get("title", "Suggestion"), t.get("detail", "")) for t in tips] or ["None."]
    if complexity and complexity.get("supported", True) and not complexity.get("error"):
        lines += [
            "", "## Complexity", "",
            "- Average cyclomatic complexity: {} (rank {})".format(
                complexity.get("average_complexity"), complexity.get("rating")),
            "- Maintainability index: {}".format(complexity.get("maintainability_index")),
        ]
        lines += ["- `{}`: {} ({})".format(d["name"], d["complexity"], d["rank"]) for d in complexity.get("details", [])]
    lines += ["", "## Source", "", "```{}".format(language.lower()), source, "```"]
    if result.get("improved_code"):
        lines += ["", "## AI-improved code", "", "```{}".format(language.lower()), result["improved_code"], "```"]
    return "\n".join(lines) + "\n"


def build_json_report(result: dict[str, Any], complexity: dict[str, Any] | None) -> str:
    return json.dumps({"review": result, "complexity": complexity}, indent=2, default=str)


def build_repo_markdown(repository: dict[str, Any], review: dict[str, Any]) -> str:
    """Render a repository review as Markdown."""
    lines = [
        "# CodeLens Repository Report: {}".format(repository["full_name"]),
        "",
        "- Branch: {}".format(repository["branch"]),
        "- Files reviewed: {}".format(review["files_reviewed"]),
        "- Critical/high findings: {}".format(review["critical_bugs"]),
        "- Warnings: {}".format(review["warnings"]),
        "- Average score: {}".format(review["overall_score"] if review["overall_score"] is not None else "N/A"),
        "",
    ]
    for item in review["file_results"]:
        lines += ["## {}".format(item["path"]), "", item["review"].get("summary") or "No summary.", ""]
        lines += [_bug_line(b) for b in item["review"].get("bugs", []) if isinstance(b, dict)] or ["No findings."]
        lines.append("")
    return "\n".join(lines)
