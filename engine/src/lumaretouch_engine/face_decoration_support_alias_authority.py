# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed authority for one exact visible-support transition, never scalar consent.

Minting freezes the shared owner, complete closure and append-only bank pair.
Only the dedicated image-ACK transaction publishes; this proof cannot make an
ordinary scalar route accept source-owned painting. AUTHORED / UNRUN.
"""
from copy import deepcopy
from dataclasses import dataclass
from . import people_state as P, people_support_assets as BANK
from . import face_decoration_support as SUPPORT, virtual_copy_people as V
from . import creative_derived_source as SOURCE, face_style_alias_review as CLOSURE


def support_changes(before, candidate, refs, before_assets, after_assets, *, allow_detach=False):
    from .people_graph_patch import between
    from .people_graph_owner import affected_assets
    before = P.check(before); candidate = P.check(candidate)
    BANK.check_store(before_assets); BANK.check_store(after_assets)
    checked = [P.check_ref(ref) for ref in refs]
    if not checked or len(checked) > 64 or len({ref['face_instance_id'] for ref in checked}) != len(checked):
        raise ValueError('Support authority requires exact bounded selected and active face references')
    changes = between(before, candidate)
    if (len(changes) != 1 or changes[0]['collection'] != 'faces'
            or before['association_revision'] != candidate['association_revision']):
        raise ValueError('Support authority can change only one existing selected face visibility pointer')
    change = changes[0]; left = change['before']; right = change['after']
    if type(left) is not dict or type(right) is not dict:
        raise ValueError('Support authority cannot create or delete an analysed face')
    ref = P.face_ref(left)
    if (ref not in checked or P.face_ref(right) != ref or affected_assets(before, candidate) != {ref['asset_sha256']}
            or any(item['asset_sha256'] != ref['asset_sha256'] for item in checked)):
        raise ValueError('Support authority cannot change face/source ownership or add donor references')
    from .face_decoration_batch_plan import recipe
    from .face_decoration_state import active
    required = {ref['face_instance_id']}
    for graph in (before, candidate):
        required.update(key for key, face in graph['faces'].items()
                        if face['enabled'] and face['asset_sha256'] == ref['asset_sha256'] and active(recipe(graph, key)))
    if {value['face_instance_id'] for value in checked} != required:
        raise ValueError('Support authority must include the selected and all before/candidate active faces')
    for graph, assets in ((before, before_assets), (candidate, after_assets)):
        for value in checked:
            face = graph['faces'].get(value['face_instance_id'])
            if face is None or P.face_ref(face) != value or not face['enabled'] or face['evidence']['status'] != 'verified':
                raise ValueError('Support authority needs every exact enabled analysed coverage face')
            if active(recipe(graph, value['face_instance_id'])) or SUPPORT.KIND in face['local_assets']:
                SUPPORT.resolve(graph, assets, value)
    pointers = []
    for face, graph, assets in ((left, before, before_assets), (right, candidate, after_assets)):
        pointer = face['local_assets'].get(SUPPORT.KIND)
        pointers.append(None if pointer is None else SUPPORT.resolve(graph, assets, ref)[1])
    if (all(key is not None for key in pointers)
            and before_assets[pointers[0]]['row']['region'] == after_assets[pointers[1]]['row']['region']):
        raise ValueError('Identical visible painting cannot manufacture a support transaction')
    if pointers[1] is None and not allow_detach:
        raise ValueError('Support authority only permits initial or revised visible painting')
    stripped_left = deepcopy(left); stripped_right = deepcopy(right)
    stripped_left['local_assets'].pop(SUPPORT.KIND, None); stripped_right['local_assets'].pop(SUPPORT.KIND, None)
    if stripped_left != stripped_right or pointers[0] == pointers[1]:
        raise ValueError('Support authority cannot change scalars, recovery, observations or inert paint')
    if any(after_assets.get(key) != value for key, value in before_assets.items()):
        raise ValueError('Support authority cannot replace or remove retained immutable bank records')
    allowed = set() if pointers[1] is None else {pointers[1]}
    if set(after_assets) - set(before_assets) - allowed:
        raise ValueError('Support authority cannot append unrelated or donor support assets')
    return changes


@dataclass(frozen=True)
class SupportAliasAuthority:
    engine: object
    owner: object
    row: dict
    before: dict
    candidate: dict
    targets: dict
    asset: str
    refs: list
    before_assets: dict
    after_assets: dict

    def verify(self, engine, row, before, candidate):
        from .face_decoration_support_alias_transaction import bank
        support_changes(before, candidate, self.refs, self.before_assets, self.after_assets)
        if (engine is not self.engine or V.scope(row) != 'project' or V.row_owner(engine, row) is not self.owner
                or self.owner.snapshot() != self.before or before != self.before or candidate != self.candidate
                or bank(engine) != self.before_assets):
            raise ValueError('Support authority lost its exact shared owner, graph or frozen bank')
        current = engine._people_preset_capture()
        CLOSURE.verify_dormant(engine, self.row, {self.asset})
        members = CLOSURE._eligible(engine, self.row, current, self.asset)
        if {item[3].document_id for item in members} != {target['document_id'] for target in self.targets.values()}:
            raise ValueError('Support authority omitted or added an affected document')
        plans = {'project': {'row': self.row, 'before': self.before, 'candidate': self.candidate,
                             'reviewed_face_refs': self.refs}}
        if CLOSURE._targets(engine, engine._batch_controller(), plans, current) != self.targets:
            raise ValueError('Support authority membership, source, revision or path changed')
        for other, state, proof, _ in members:
            SOURCE.verify_row({**other, 'state': state}, proof)


def mint(engine, row, before, candidate, targets, refs, *, before_assets, after_assets):
    from .people_graph_owner import affected_assets
    assets = affected_assets(before, candidate)
    if len(assets) != 1 or V.scope(row) != 'project':
        raise ValueError('Support authority requires one exact shared owner/source')
    value = SupportAliasAuthority(engine, V.row_owner(engine, row), row, deepcopy(before), deepcopy(candidate),
        deepcopy(targets), next(iter(assets)), deepcopy(refs), deepcopy(before_assets), deepcopy(after_assets))
    value.verify(engine, row, before, candidate)
    return value
