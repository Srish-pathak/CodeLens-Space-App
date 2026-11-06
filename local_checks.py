"""Offline heuristic checks so the app is useful without any AI API key."""

import ast
import re
from typing import Any

SECRET_PATTERN = re.compile(
    r"""(?ix)
    \b(api[_-]?key|secret|passwd|password|token|auth[_-]?key)\b
    \s*[:=]\s*
    ["'][A-Za-z0-9_\-/+=]{8,}["']
    """
)
LONG_LINE = 120
LONG_FUNCTION_LINES = 50


def _bug(line: Any, severity: str, description: str) -> dict[str, Any]:
    return {"line": line, "severity": severity, "description": description, "source": "local"}


def _python_checks(code: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    findings: list[dict[str, Any]] = []

    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imported[alias.asname or alias.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    exported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ) and isinstance(node.value, (ast.List, ast.Tuple)):
            exported |= {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    for name, line in imported.items():
        if name not in used and name not in exported:
            findings.append(_bug(line, "warning", f"Import '{name}' is never used."))

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append(_bug(node.lineno, "warning",
                                     "Bare 'except:' hides every error, including KeyboardInterrupt. Catch specific exceptions."))
            elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                findings.append(_bug(node.lineno, "warning", "Exception is caught and silently ignored."))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(_bug(node.lineno, "warning",
                                         f"Function '{node.name}' uses a mutable default argument; it is shared between calls."))
            length = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1
            if length > LONG_FUNCTION_LINES:
                findings.append(_bug(node.lineno, "info",
                                     f"Function '{node.name}' is {length} lines long. Consider splitting it up."))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"eval", "exec"}:
                findings.append(_bug(node.lineno, "critical",
                                     f"'{func.id}()' can execute arbitrary code. Avoid it on untrusted input."))
            elif isinstance(func, ast.Attribute) and func.attr in {"system", "popen"} \
                    and isinstance(func.value, ast.Name) and func.value.id == "os":
                findings.append(_bug(node.lineno, "warning", "os.system/popen is shell-injection prone; use subprocess with a list."))
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    findings.append(_bug(node.lineno, "warning", "subprocess call with shell=True is injection prone."))
        elif isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                    findings.append(_bug(node.lineno, "info", "Compare to None with 'is' / 'is not', not '=='."))
        elif isinstance(node, ast.Assert) and isinstance(node.test, ast.Tuple) and node.test.elts:
            findings.append(_bug(node.lineno, "warning", "assert on a non-empty tuple is always true."))
    return findings


def _generic_checks(code: str, language: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for number, line in enumerate(code.splitlines(), start=1):
        if SECRET_PATTERN.search(line):
            findings.append(_bug(number, "critical", "Possible hard-coded credential. Move secrets to environment variables."))
        if len(line) > LONG_LINE:
            findings.append(_bug(number, "info", f"Line is {len(line)} characters long (limit {LONG_LINE})."))
        if re.search(r"\b(TODO|FIXME|HACK)\b", line):
            findings.append(_bug(number, "info", "Unresolved TODO/FIXME marker."))
        if language in {"JavaScript", "JSX", "TypeScript", "TSX"}:
            if re.search(r"\beval\s*\(", line):
                findings.append(_bug(number, "critical", "eval() can execute arbitrary code."))
            if re.search(r"\bvar\s+\w+", line):
                findings.append(_bug(number, "info", "Prefer 'let' or 'const' over 'var'."))
            if re.search(r"[^=!]==[^=]", line) and "=>" not in line:
                findings.append(_bug(number, "info", "Prefer strict equality '===' over '=='."))
            if re.search(r"\.innerHTML\s*=|dangerouslySetInnerHTML", line):
                findings.append(_bug(number, "warning", "Injecting raw HTML can cause XSS."))
            if "console.log" in line:
                findings.append(_bug(number, "info", "Leftover console.log statement."))
        if language in {"C++"} and re.search(r"\b(gets|strcpy|sprintf)\s*\(", line):
            findings.append(_bug(number, "critical", "Unsafe C string function; risk of buffer overflow."))
        if language == "Java" and re.search(r"catch\s*\(\s*(Exception|Throwable)\b", line):
            findings.append(_bug(number, "info", "Catching Exception/Throwable is too broad."))
    return findings


def run_local_checks(code: str, language: str) -> list[dict[str, Any]]:
    """Return heuristic findings sorted by line number."""
    findings = _generic_checks(code, language)
    if language == "Python":
        findings += _python_checks(code)
    seen, unique = set(), []
    for item in findings:
        key = (item["line"], item["description"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(key=lambda f: (f["line"] if isinstance(f["line"], int) else 0))
    return unique
