"""Scoped content patches for the existing batch ledger's protected undo/redo."""
from copy import deepcopy
from . import people_state as S

DICT_COLLECTIONS=('faces','persons','groups','analysis_runs')
LIST_KEYS={'overrides':('scope','target_id','operation_id','parameter_path'),
           'links':('face_instance_id','person_id'),'unresolved_legacy':('id',)}


def indexed(state,collection):
    if collection in DICT_COLLECTIONS:return state[collection]
    return {tuple(row[k] for k in LIST_KEYS[collection]):row for row in state[collection]}


def between(before,after):
    before=S.check(before);after=S.check(after);changes=[]
    for collection in (*DICT_COLLECTIONS,*LIST_KEYS):
        left,right=indexed(before,collection),indexed(after,collection)
        for key in sorted(set(left)|set(right)):
            if left.get(key)!=right.get(key):changes.append({'collection':collection,'key':list(key) if isinstance(key,tuple) else key,
                'before':deepcopy(left.get(key)),'after':deepcopy(right.get(key))})
    return changes


def apply(state,changes,*,redo):
    out=S.check(state)
    for change in changes:
        collection=change['collection']
        if collection not in (*DICT_COLLECTIONS,*LIST_KEYS):raise ValueError('Unknown people history collection')
        values=indexed(out,collection);key=tuple(change['key']) if collection in LIST_KEYS else change['key']
        expected=change['before' if redo else 'after'];replacement=change['after' if redo else 'before']
        if values.get(key)!=expected:raise ValueError('People scope was edited after this batch; protected undo refused')
        if replacement is None:values.pop(key,None)
        else:values[key]=deepcopy(replacement)
        out[collection]=list(values.values()) if collection in LIST_KEYS else values
    out['revision']+=1
    return S.check(out)
