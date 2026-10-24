# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit internal proof for one reviewed scalar alias preparation, not a flag."""
from dataclasses import dataclass
from copy import deepcopy
from . import virtual_copy_people as V, creative_derived_source as SOURCE
from . import face_style_alias_review as CLOSURE


@dataclass(frozen=True)
class AliasAuthority:
    engine: object
    owner: object
    row: dict
    before: dict
    candidate: dict
    targets: dict
    asset: str
    refs: list

    def verify(self, engine, row, before, candidate):
        from .people_graph_owner import affected_assets
        from .face_decoration_alias_history import scalar_changes
        scalar_changes(before,candidate,self.refs)
        if (engine is not self.engine or V.scope(row) != 'project'
                or V.row_owner(engine,row) is not self.owner or self.owner.snapshot()!=self.before
                or before!=self.before or candidate!=self.candidate
                or affected_assets(before,candidate)!={self.asset}):
            raise ValueError('Decoration alias authority does not match this exact owner/graph/source transition')
        current=engine._people_preset_capture()
        CLOSURE.verify_dormant(engine,self.row,{self.asset})
        members=CLOSURE._eligible(engine,self.row,current,self.asset)
        if {item[3].document_id for item in members}!={t['document_id'] for t in self.targets.values()}:
            raise ValueError('Decoration alias authority cannot omit or add affected documents')
        plans={'project':{'row':self.row,'before':self.before,'candidate':self.candidate,'reviewed_face_refs':self.refs}}
        if CLOSURE._targets(engine,engine._batch_controller(),plans,current)!=self.targets:
            raise ValueError('Decoration alias ledger membership or immutable source changed')
        for other,state,proof,_ in members: SOURCE.verify_row({**other,'state':state},proof)


def mint(engine, row, before, candidate, targets, refs):
    from .people_graph_owner import affected_assets
    assets=affected_assets(before,candidate)
    if len(assets)!=1 or V.scope(row)!='project':
        raise ValueError('Decoration alias authority is limited to one shared owner/source')
    value=AliasAuthority(engine,V.row_owner(engine,row),row,deepcopy(before),deepcopy(candidate),deepcopy(targets),next(iter(assets)),deepcopy(refs))
    value.verify(engine,row,before,candidate)
    return value
