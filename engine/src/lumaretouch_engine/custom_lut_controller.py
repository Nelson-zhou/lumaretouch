"""Latest-intent/document guard; host must atomically commit prepared frame+recipe.

Host supplies source captured at the LUT stage, not the already-graded preview.
Host commit callback must push history and swap recipe/frame as one transaction,
raising without mutation on failure. Existing builtin LUT is mutually exclusive.
"""
from __future__ import annotations
import threading
from .custom_lut_recipe import validate
from .custom_lut_native import ParsedCube

class Controller:
    def __init__(self, library):
        self.library = library
        self._lock = threading.RLock()
        self._generation = 0
        self._document = None
        self._revision = 0

    def bind(self, document, revision):
        with self._lock:
            self._generation += 1
            self._document, self._revision = document, revision

    def cancel(self):
        with self._lock: self._generation += 1

    def begin(self, document, revision):
        with self._lock:
            if document != self._document or revision != self._revision: raise ValueError("文档或编辑版本已改变")
            self._generation += 1
            return (document, revision, self._generation)

    def stale(self, token):
        with self._lock: return token != (self._document, self._revision, self._generation)

    def prepare_and_commit(self, token, recipe, source, commit):
        recipe = validate(recipe)
        if self.stale(token): raise InterruptedError("较新操作已替代 LUT 请求")
        frame = source
        if recipe:
            # Resolve even at amount=0: missing portable resources are never hidden.
            with ParsedCube(self.library.content(recipe["asset_id"])) as cube:
                frame = cube.apply(source, recipe["amount"], lambda: self.stale(token))
        with self._lock:
            if self.stale(token): raise InterruptedError("较新操作已替代 LUT 请求")
            next_revision = self._revision + 1
            commit(recipe, frame, token[0], self._revision, next_revision)
            self._revision = next_revision
            return {"document_id": token[0], "revision": next_revision, "recipe": recipe}


def render_export(source, recipe, library, cancelled=lambda: False):
    """Same Rust operator for full-quality inspection/export; no uint8 conversion."""
    recipe = validate(recipe)
    if recipe is None: return source
    with ParsedCube(library.content(recipe["asset_id"])) as cube:
        return cube.apply(source, recipe["amount"], cancelled)
