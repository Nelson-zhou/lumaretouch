# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole persistent-cohort collarbone image evidence, including source member.

No association, body evidence or pixels are borrowed from another member. This
adapter keeps the existing association controller and scoped ledger as owners.
All numerical, transport and photographic acceptance is UNRUN.
"""
from copy import deepcopy
from . import collarbone_state as C, collarbone_transfer_review as R
from . import people_algorithms as A
from .people_resolver import resolve


def required(endpoints, selected, review):
    if C.OP in selected['selection'] or any(leaf['op'] == C.OP for leaf in review['intent']):
        return True
    # Unrelated shared changes can coexist with explicit face overrides. Review
    # real active collarbone members too, not just the newly selected keys.
    return any(C.active(A.recipes(resolve(item[key], item['ref']['face_instance_id'], A.defaults()))[C.OP])
               for item in endpoints for key in ('before', 'candidate'))


def coverage(engine, item):
    from .skin_colour_transfer_review import for_target
    # This is a target-local resolver request, not a transferred recipe or a
    # fabricated people-transfer proof. for_target resolves the actual graph.
    payload = {'parameters': [{'operation_id': C.OP}], 'target_refs': [item['ref']],
               'target_document': item['proof']['document']}
    return for_target(engine, item['row'], item['candidate'], payload, family='collarbone')


def prepare(engine, endpoints):
    if not 2 <= len(endpoints) <= R.MAX_TARGETS:
        raise ValueError('Collarbone cohort review requires every two to sixteen members including source')
    displays = {}; total = 0
    for item in endpoints:
        document = item['proof']['document']; own_coverage = coverage(engine, item)
        record, display = R.prepare(engine, item['row'], item['before'], item['candidate'],
            document['document_id'], str(document['revision']), own_coverage)
        item['collarbone_coverage'] = own_coverage
        item['collarbone_visual'] = record
        total += len(display['before']['base64']) + len(display['after']['base64'])
        if total > R.MAX_TOTAL_BASE64:
            raise ValueError('Complete collarbone cohort exceeds bounded image preparation; no member was omitted or reduced')
        displays[document['document_id']] = {'revision': str(document['revision']),
                                           'before': display['before'], 'after': display['after']}
    # Later member rendering may refresh evidence. No earlier image authorizes
    # a different source, graph or support bank discovered during that work.
    for item in endpoints: verify(engine, item, item)
    return displays


def verify(engine, item, frozen):
    own_coverage = coverage(engine, item)
    if own_coverage != frozen.get('collarbone_coverage'):
        raise ValueError('A collarbone cohort member changed its independent coverage after review')
    document = item['proof']['document']
    return R.verify(engine, item['row'], item['before'], item['candidate'],
        document['document_id'], str(document['revision']), own_coverage, frozen.get('collarbone_visual'))


def evidence(item):
    return {key: deepcopy(item[key]) for key in ('collarbone_coverage', 'collarbone_visual') if key in item}
