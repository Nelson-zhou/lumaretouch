"""Resolve optional tensor modules on first use, never during protocol startup.

Use normal import_module on demand so Python's import locks/error handling stay
in charge. A missing root returns None; a broken installed package raises when
actually used rather than being mislabeled as a working backend.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from types import ModuleType


class _DeferredModule:
    def __init__(self, name: str):
        self._name = name
        self._module: ModuleType | None = None

    def __getattr__(self, name: str):
        if self._module is None:
            self._module = importlib.import_module(self._name)
        return getattr(self._module, name)


def optional_module(name: str):
    root = name.partition('.')[0]
    if root in sys.modules:
        if sys.modules[root] is None:
            return None
    elif importlib.util.find_spec(root) is None:
        return None
    return _DeferredModule(name)
