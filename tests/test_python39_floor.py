"""The declared Python floor is 3.9, checked statically rather than hoped for.

``pyproject.toml`` says ``requires-python = ">=3.9"``. Nothing in CI runs a 3.9
interpreter, so this asserts the floor the only way a newer interpreter can: by
re-parsing every module with ``ast.parse(feature_version=(3, 9))``, which refuses
syntax 3.9 did not have, and by grepping for the runtime constructs that parse
everywhere but fail at import on 3.9.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import matr_clean

PACKAGE = Path(matr_clean.__file__).resolve().parent
MODULES = sorted(PACKAGE.glob("*.py"))
FLOOR = (3, 9)


def test_there_are_modules_to_check():
    assert len(MODULES) >= 8
    assert (PACKAGE / "features.py") in MODULES
    # v0.3.0's two modules are picked up by the glob; name them so a rename or a
    # deletion fails here rather than silently reducing what the floor covers.
    assert (PACKAGE / "series.py") in MODULES
    assert (PACKAGE / "_h5.py") in MODULES


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_module_parses_as_python_39(path):
    """Rejects match statements, parenthesised context managers, and the rest."""
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path), feature_version=FLOOR)
    except SyntaxError as exc:
        pytest.fail(
            "{0} needs Python > 3.9: {1} at line {2}".format(
                path.name, exc.msg, exc.lineno
            )
        )


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_annotations_are_postponed(path):
    """``from __future__ import annotations`` is what makes ``X | Y`` and
    ``list[str]`` annotations safe on 3.9: they stay strings and are never
    evaluated."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    futures = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "__future__"
        for alias in node.names
    }
    assert "annotations" in futures, (
        "{0} lacks `from __future__ import annotations`".format(path.name)
    )


#: Constructs that parse on any version but raise on 3.9 at *runtime*.
_RUNTIME_TRAPS = (
    (re.compile(r"\bfrom\s+typing\s+import\s+[^\n]*\b(Self|TypeAlias|ParamSpec)\b"),
     "typing.Self / TypeAlias / ParamSpec are 3.10+"),
    (re.compile(r"\bzip\((?:[^()\n]|\([^()\n]*\))*,\s*strict\s*="),
     "zip(strict=) is 3.10+"),
    (re.compile(r"\bitertools\.pairwise\b"), "itertools.pairwise is 3.10+"),
    (re.compile(r"\bmath\.nextafter\b"), "math.nextafter is 3.9, but check"),
    (re.compile(r"\bdict\s*\|\s*dict\b"), "dict | dict at runtime is 3.9+, ok"),
    (re.compile(r"@dataclass\([^)]*\bslots\s*=", re.S), "dataclass(slots=) is 3.10+"),
    (re.compile(r"\bstr\.removeprefix\b|\.removeprefix\("), "removeprefix is 3.9, ok"),
    (re.compile(r"\bgraphlib\b"), "graphlib is 3.9, ok"),
)

#: The ones that genuinely break 3.9, kept separate so the list above can carry
#: notes without failing the test.
_FATAL = (
    "typing.Self / TypeAlias / ParamSpec are 3.10+",
    "zip(strict=) is 3.10+",
    "itertools.pairwise is 3.10+",
    "dataclass(slots=) is 3.10+",
)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_runtime_construct_newer_than_39(path):
    source = path.read_text(encoding="utf-8")
    problems = [
        note for pattern, note in _RUNTIME_TRAPS
        if note in _FATAL and pattern.search(source)
    ]
    assert problems == [], "{0}: {1}".format(path.name, problems)


def test_pyproject_declares_the_floor():
    root = PACKAGE.parent
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.9"' in text
    # and the series extra names a floor too, for v0.3.0
    assert 'series = ["h5py>=3.0"]' in text


def test_the_package_does_not_import_h5py_at_module_scope():
    """v0.2.0 must install and import with pandas and numpy alone."""
    offenders = []
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if any(name.split(".")[0] == "h5py" for name in names):
                # allowed only inside a function body
                at_module_scope = any(
                    node in getattr(top, "body", []) for top in tree.body
                ) or node in tree.body
                if at_module_scope:
                    offenders.append((path.name, node.lineno))
    assert offenders == [], "h5py imported at module scope: {0}".format(offenders)


def test_h5py_is_not_a_hard_dependency():
    root = PACKAGE.parent
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.search(r"^dependencies = \[(.*?)\]", text, re.M | re.S)
    assert deps is not None
    assert "h5py" not in deps.group(1)
    assert "pandas" in deps.group(1) and "numpy" in deps.group(1)
