"""Fill the counts in public docstrings from the data, rather than typing them in.

Every default this package applies is documented with the number of cells or cycles
it affects. Those numbers are not literals in the source: each docstring carries an
``@@name@@`` placeholder, and the first successful load substitutes the value counted
from the loaded tables.

Until the first load the markers are still visible in ``help()``: ``@@n_cells@@``
rather than a number, which says plainly that the number has not been read yet. Any
loader call, or :func:`matr_clean.describe`, fills every registered docstring in one
pass. Nothing is ever substituted from a hard-coded table.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

#: Functions whose docstring carries placeholders, with their unfilled template.
_TEMPLATES = {}  # type: Dict[str, str]
_TARGETS = {}  # type: Dict[str, Callable[..., Any]]

_FILLED = False


def register(func):
    """Decorator: remember *func*'s docstring template so it can be filled later."""
    if func.__doc__:
        _TEMPLATES[func.__qualname__] = func.__doc__
        _TARGETS[func.__qualname__] = func
    return func


def placeholders(template: str) -> List[str]:
    names = []
    rest = template
    while "@@" in rest:
        _, _, rest = rest.partition("@@")
        name, sep, rest = rest.partition("@@")
        if not sep:
            break
        if name not in names:
            names.append(name)
    return names


def fill(counts: Dict[str, Any]) -> None:
    """Substitute *counts* into every registered docstring. Idempotent."""
    global _FILLED
    for qualname, template in _TEMPLATES.items():
        text = template
        for name in placeholders(template):
            value = counts.get(name)
            if value is None:
                continue
            text = text.replace("@@{0}@@".format(name), "{0:,}".format(value)
                                if isinstance(value, int) else str(value))
        target = _TARGETS[qualname]
        try:
            target.__doc__ = text
        except AttributeError:  # pragma: no cover - builtins cannot be documented
            pass
    _FILLED = True


def is_filled() -> bool:
    return _FILLED


def unfilled_names() -> List[str]:
    """Placeholder names still present in any registered docstring."""
    out = []  # type: List[str]
    for qualname, func in _TARGETS.items():
        for name in placeholders(func.__doc__ or ""):
            if name not in out:
                out.append(name)
    return out
