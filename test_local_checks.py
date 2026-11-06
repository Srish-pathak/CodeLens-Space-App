from local_checks import run_local_checks


def _descriptions(code, language="Python"):
    return [f["description"] for f in run_local_checks(code, language)]


def test_clean_python_has_no_findings():
    assert run_local_checks("def add(a, b):\n    return a + b\n", "Python") == []


def test_python_risky_patterns_are_found():
    code = "import os\ndef f(x, y=[]):\n    try:\n        eval(x)\n    except:\n        pass\n"
    text = " ".join(_descriptions(code))
    assert "never used" in text and "mutable default" in text and "eval" in text and "Bare" in text


def test_hardcoded_secret_is_critical_in_any_language():
    findings = run_local_checks('const apiKey = "abcd1234efgh5678";', "JavaScript")
    assert any(f["severity"] == "critical" for f in findings)


def test_javascript_specific_checks():
    text = " ".join(_descriptions("var a = 1;\nif (a == 2) console.log(a);\n", "JavaScript"))
    assert "let" in text and "===" in text and "console.log" in text


def test_syntax_errors_do_not_crash():
    assert isinstance(run_local_checks("def broken(:\n", "Python"), list)
