# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed mixed-preset consent, distinct from scalar edit and support painting.

Only selected portrait scalar leaves may change. Source-owned observations and
all support bytes remain immutable; a sibling never receives the current full
recipe. This internal proof binds the complete source-alias closure. UNRUN.
"""
from copy import deepcopy
from dataclasses import dataclass
from . import people_state as P, people_support_assets as BANK
from . import virtual_copy_people as V, creative_derived_source as SOURCE
from . import face_style_alias_review as CLOSURE


def mixed_changes(before, candidate, refs, *, selected_ref, modules, assets):
    from . import people_algorithms as A, scope as SC, face_decoration_state as D
    from .face_decoration_scope import resolved_recipe
    from .face_decoration_support import resolve
    from .people_graph_patch import between
    from .people_graph_owner import affected_assets
    before = P.check(before); candidate = P.check(candidate); BANK.check_store(assets)
    selected = P.check_ref(selected_ref); modules = list(modules)
    if (not modules or len(modules) > SC.PRESET_MAX_MODULES or SC.check_scope(modules) != modules
            or 'lnx.people_graph.v1' in modules):
        raise ValueError('Mixed decoration authority needs its exact selected preset modules')
    checked = [P.check_ref(ref) for ref in refs]
    if (not 1 <= len(checked) <= 64 or selected not in checked
            or len({ref['face_instance_id'] for ref in checked}) != len(checked)
            or any(ref['asset_sha256'] != selected['asset_sha256'] for ref in checked)):
        raise ValueError('Mixed decoration authority requires exact selected and active source-owned faces')
    required = {selected['face_instance_id']}; retained_active = False
    for graph in (before, candidate):
        for key, face in graph['faces'].items():
            if not face['enabled'] or face['asset_sha256'] != selected['asset_sha256']: continue
            if D.active(resolved_recipe(graph, key)):
                required.add(key); retained_active = True
        for ref in checked:
            face = graph['faces'].get(ref['face_instance_id'])
            if face is None or P.face_ref(face) != ref or not face['enabled'] or face['evidence']['status'] != 'verified':
                raise ValueError('Mixed decoration authority cannot substitute retained source analysis')
            if D.active(resolved_recipe(graph, ref['face_instance_id'])):
                resolve(graph, assets, ref)
    if required != {ref['face_instance_id'] for ref in checked} or (D.OP not in modules and not retained_active):
        raise ValueError('Mixed decoration authority omitted active coverage or has no decoration review purpose')
    if (before['association_revision'] != candidate['association_revision']
            or affected_assets(before, candidate) - {selected['asset_sha256']}):
        raise ValueError('Mixed decoration authority cannot change association or another source')
    changes = between(before, candidate)
    if len(changes) > 4096: raise ValueError('Mixed decoration authority exceeds the exact scalar patch budget')
    for change in changes:
        key = change['key']
        if (change['collection'] != 'overrides' or type(key) is not list or len(key) != 4
                or key[:2] != ['face', selected['face_instance_id']] or key[2] not in modules
                or key[3] not in A.defaults().get(key[2], {})):
            raise ValueError('Mixed decoration authority cannot transport support, observations, defaults or unselected effects')
        for record in (change['before'], change['after']):
            if record is None: continue
            if (type(record) is not dict or set(record) != {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}
                    or [record[name] for name in ('scope', 'target_id', 'operation_id', 'parameter_path')] != key):
                raise ValueError('Mixed decoration scalar leaf identity changed')
            P.scalar(record['value'])
    return changes


@dataclass(frozen=True)
class PresetAliasAuthority:
    engine: object
    owner: object
    row: dict
    before: dict
    candidate: dict
    targets: dict
    selected_ref: dict
    refs: list
    modules: list
    before_assets: dict

    def verify(self, engine, row, before, candidate):
        from .face_decoration_preset_alias_transaction import bank
        mixed_changes(before, candidate, self.refs, selected_ref=self.selected_ref,
                      modules=self.modules, assets=self.before_assets)
        if (engine is not self.engine or V.scope(row) != 'project' or V.row_owner(engine, row) is not self.owner
                or self.owner.snapshot() != self.before or before != self.before or candidate != self.candidate
                or bank(engine) != self.before_assets):
            raise ValueError('Mixed decoration authority lost its exact shared owner, graph or immutable bank')
        current = engine._people_preset_capture(); asset = self.selected_ref['asset_sha256']
        CLOSURE.verify_dormant(engine, self.row, {asset})
        members = CLOSURE._eligible(engine, self.row, current, asset); targets = {}
        for other, state, proof, version in members:
            SOURCE.verify_row({**other, 'state': state}, proof)
            index = next(i for i, item in enumerate(engine._docs) if item is other)
            targets[str(index)] = {'path': other['path'], 'document_id': version.document_id,
                'revision': version.revision, 'asset_sha256': asset, 'people_scope': 'project',
                'source_proof': proof, 'reviewed_face_refs': deepcopy(self.refs)}
        if targets != self.targets:
            raise ValueError('Mixed decoration authority changed the complete member source, path, revision or face closure')


def mint(engine, row, before, candidate, targets, refs, *, selected_ref, modules, before_assets):
    if V.scope(row) != 'project': raise ValueError('Mixed decoration authority needs one shared project owner')
    value = PresetAliasAuthority(engine, V.row_owner(engine, row), row, deepcopy(before), deepcopy(candidate),
        deepcopy(targets), deepcopy(selected_ref), deepcopy(refs), list(modules), deepcopy(before_assets))
    value.verify(engine, row, before, candidate)
    return value
