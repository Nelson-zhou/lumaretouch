"""Durable immutable-source repair ownership and ordered capture fences.

Legacy unbound operations are valid only on a physical original. Source patch
and clone retain normalized vector intent; proxy weights are not final pixels.
No stack union, inference, pixel decoding or second history owner lives here.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re


def check_binding(value):
    if value is None:return None
    if (type(value) is not dict or set(value)!={'sha256','width','height'}
            or type(value['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',value['sha256']) is None
            or any(type(value[k]) is not int or value[k]<1 for k in ('width','height'))):
        raise ValueError('Invalid repair immutable source binding')
    return deepcopy(value)


def validate_source_ops(ops,source):
    """Validate an already decoded stack against its frame's effective source."""
    from .repair_record import validate_repair_ops
    source=check_binding(source);validate_repair_ops(ops)
    for op in ops:
        bound=check_binding(op.source_binding)
        if bound!=source:
            raise ValueError('Repair stack belongs to another immutable source')
        if source is not None and op.kind not in ('source_patch','clone_stamp'):
            raise ValueError('Derived repair kind has no source-owned replay contract')
    return ops


def _stacks(owner):
    if isinstance(owner,dict):
        # Reject ambiguous aliases rather than silently hiding a foreign stack.
        for private,public in (('_repair_ops','repair_ops'),('_redo_ops','redo_ops')):
            if private in owner and public in owner:
                raise ValueError('Repair state contains ambiguous stack aliases')
        return (owner.get('_repair_ops',owner.get('repair_ops',[])),
                owner.get('_redo_ops',owner.get('redo_ops',[])))
    return getattr(owner,'_repair_ops',[]),getattr(owner,'_redo_ops',[])


def validate_stacks(state_or_engine):
    from . import creative_derived_source as D
    source=D.binding(state_or_engine) if D.record(state_or_engine) is not None else None
    for ops in _stacks(state_or_engine):validate_source_ops(ops,source)
    return source


def stack_digest(state_or_engine):
    """Exact ordered active+redo evidence, including coverage and normalized intent."""
    source=validate_stacks(state_or_engine)
    active,redo=_stacks(state_or_engine)
    return digest_ops(active,redo,source)


def digest_ops(active,redo,source):
    """Pipeline adapter with explicit source, never a guessed original binding."""
    import numpy as np
    source=check_binding(source)
    validate_source_ops(active,source);validate_source_ops(redo,source)
    digest=sha256()
    digest.update(b'lumaretouch-repair-stack-v1\0')
    digest.update(json.dumps(source,sort_keys=True,separators=(',',':')).encode())
    from .repair_record import check_repair_fields
    for label,ops in zip(('active','redo'),(active,redo)):
        digest.update(label.encode());digest.update(len(ops).to_bytes(8,'big'))
        for op in ops:
            value=check_repair_fields(vars(op),allow_legacy=False)
            header={key:value[key] for key in ('op_id','kind','params','source_binding')}
            header['shape']=list(value['weight'].shape)
            raw=json.dumps(header,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
            for row in value['weight']:
                digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return digest.hexdigest()
