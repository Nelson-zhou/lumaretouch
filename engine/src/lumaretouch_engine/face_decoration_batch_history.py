# SPDX-License-Identifier: GPL-3.0-or-later
"""Decoration identity on the existing exact scalar dependency/history contract.

The established validator checks scalar-only patches, complete affected document
membership, immutable observations/support and unrelated state dependencies.
Translation is local validation only; no eye-bag marker is stored or advertised.
"""
from . import eye_bag_batch_history as COMMON
KEY='face_decoration_batch_review'


def _entry(entry):
    return {**entry,COMMON.KEY:entry[KEY]}


def check(entry):
    return None if KEY not in entry else COMMON.check(_entry(entry))


def prepare(engine,plans,targets,ack):
    return COMMON.prepare(engine,plans,targets,ack)


def verify_restore(engine,entry,plans,targets):
    if check(entry) is None:return
    COMMON.verify_restore(engine,_entry(entry),plans,targets)
    from .face_decoration_batch_plan import closure
    closure(engine,engine._docs,plans)


def status_summary(entry):
    marker=check(entry)
    return None if marker is None else {'version':1,'review_sha256':marker['review_sha256'],'member_count':len(marker['targets'])}
