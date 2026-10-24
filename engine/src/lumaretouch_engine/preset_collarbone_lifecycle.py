# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact-row preset transaction bridge; never another history/commit owner.

The renderer/planner port owns the reviewed portrait graph and its restoration.
This bridge only fences the existing preset transaction's callbacks.
"""
from .scope import ScopeError


class CollarbonePresetReplay:
    def __init__(self, ports, row, identity, revision, record):
        self.ports = ports; self.row = row; self.identity = identity
        self.revision = revision; self.record = record; self.started = False
        if ports.collarbone_replay is None or ports.verify_collarbone_applied is None:
            raise ScopeError('Collarbone preset requires exact reviewed graph replay and post-render verification')

    def current(self):
        row = self.ports.target_row()
        if (row is not self.row or (row.get('document_id'), row.get('path'), self.ports.document_id()) != self.identity
                or self.ports.revision() != self.revision):
            raise ScopeError('Collarbone preset target, load identity or revision changed; refusing stale write or rollback')
        return row

    def replay(self, state, **kwargs):
        rollback = kwargs.get('mode') == 'preset_rollback'
        if rollback and not self.started:
            raise ScopeError('Collarbone preset forward write did not start; refusing to overwrite another state with rollback')
        row = self.current()
        if not rollback: self.started = True
        return self.ports.collarbone_replay(row, state, self.identity[2], self.revision,
            self.record, rollback=rollback, **{**kwargs, 'strict_local': True})

    def verify(self, *, rollback=False):
        row = self.current(); actual = self.ports.capture()
        self.ports.verify_collarbone_applied(row, actual, self.identity[2], self.revision,
                                             self.record, rollback=rollback)
        self.current()
