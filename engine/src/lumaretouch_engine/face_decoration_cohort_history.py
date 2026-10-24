# SPDX-License-Identifier: GPL-3.0-or-later
"""Decoration marker over the existing exact association history contract. UNRUN."""
from . import eye_bag_cohort_history as COMMON
KEY='face_decoration_cohort_review'


def _entry(entry):return {**entry,COMMON.KEY:entry[KEY]}


def check(entry):return None if KEY not in entry else COMMON.check(_entry(entry))


def prepare(engine,plans,targets,review,ack):return COMMON.prepare(engine,plans,targets,review,ack)


def verify_restore(engine,entry,plans,targets,*,redo):
    if check(entry) is not None:COMMON.verify_restore(engine,_entry(entry),plans,targets,redo=redo)


def status_summary(entry):
    marker=check(entry)
    return None if marker is None else {'version':1,'review_sha256':marker['review_sha256'],'member_count':len(marker['targets'])}
