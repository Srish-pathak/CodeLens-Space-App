import ast
from typing import Any


class StaticAnalyzer(ast.NodeVisitor):
    """Find simple Python call-signature mismatches."""

    def __init__(self) -> None:
        self.functions: dict[str, int] = {}
        self.signatures: dict[str, dict[str, Any]] = {}
        self.bugs: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        positional = [argument.arg for argument in node.args.posonlyargs]
        positional.extend(argument.arg for argument in node.args.args)
        defaults_start = len(positional) - len(node.args.defaults)
        positional_required = positional[:defaults_start]
        positional_or_keyword = [
            argument.arg for argument in node.args.args
        ]
        keyword_only = [argument.arg for argument in node.args.kwonlyargs]
        keyword_required = [
            argument.arg
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
            if default is None
        ]

        self.functions[node.name] = len(positional) + len(keyword_only)
        self.signatures[node.name] = {
            "positional": positional,
            "positional_required": positional_required,
            "posonly_count": len(node.args.posonlyargs),
            "keyword": positional_or_keyword + keyword_only,
            "keyword_required": keyword_required,
            "vararg": node.args.vararg is not None,
            "kwarg": node.args.kwarg is not None,
        }
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in self.functions:
                mismatch = self._call_mismatch(node, name)
                if mismatch:
                    self.bugs.append(
                        {
                            "line": node.lineno,
                            "severity": "critical",
                            "description": mismatch,
                        }
                    )
        self.generic_visit(node)

    def _call_mismatch(self, node: ast.Call, name: str) -> str | None:
        """Validate calls without treating defaults or keyword arguments as omissions."""
        signature = self.signatures[name]
        positional_names = signature["positional"]
        positional_required = set(signature["positional_required"])
        keyword_names = set(signature["keyword"])
        vararg = signature["vararg"]
        kwarg = signature["kwarg"]

        # A starred argument can supply an unknown number of values.
        if (
            any(isinstance(argument, ast.Starred) for argument in node.args)
            or any(keyword.arg is None for keyword in node.keywords)
        ):
            return None

        supplied = set()
        positional_supplied = 0
        for index, _argument in enumerate(node.args):
            positional_supplied += 1
            if index >= len(positional_names):
                if not vararg:
                    return f"Function '{name}' received too many positional arguments."
                continue
            supplied.add(positional_names[index])

        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            if keyword.arg in positional_names[:signature["posonly_count"]]:
                return f"Function '{name}' does not accept '{keyword.arg}' as a keyword argument."
            if keyword.arg not in keyword_names:
                if not kwarg:
                    return f"Function '{name}' received unexpected keyword argument '{keyword.arg}'."
                supplied.add(keyword.arg)
                continue
            if keyword.arg in supplied:
                return f"Function '{name}' received multiple values for argument '{keyword.arg}'."
            supplied.add(keyword.arg)

        missing = {
            argument for argument in positional_required
            if argument not in supplied
        }
        if positional_supplied:
            missing.difference_update(positional_names[:positional_supplied])
        keyword_required = set(signature["keyword_required"])
        missing.update(keyword_required.difference(supplied))
        if missing:
            names = ", ".join(sorted(missing))
            return f"Function '{name}' is missing required argument(s): {names}."
        return None


def analyze_static(code: str, language: str) -> list[dict[str, Any]]:
    """Return static-analysis findings for Python code."""
    if language != "Python":
        return []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    analyzer = StaticAnalyzer()
    analyzer.visit(tree)
    analyzer.bugs = []
    analyzer.visit(tree)
    return analyzer.bugs