# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: cohort ownership/trigger/review contracts, not photo quality."""
from copy import deepcopy
from pathlib import Path
import ast
import pytest
from lumaretouch_engine import collarbone_cohort_review as C
from lumaretouch_engine import people_cross_owner_workflow as W
from lumaretouch_engine import skin_colour_transfer_review as K


def endpoints():
    return [{'index': index, 'row': {'state': {'sentinel': index}, 'path': str(index)},
             'before': {'amount': 0., 'owner': index}, 'candidate': {'amount': .4, 'owner': index},
             'ref': {'face_instance_id': 'face-'+str(index)},
             'proof': {'document': {'document_id': 'doc-'+str(index), 'revision': index}},
             'candidate_sha256': str(index)*64, 'person_id': 'person'} for index in range(3)]


def resolver(monkeypatch):
    monkeypatch.setattr(C, 'resolve', lambda graph, face, defaults: graph)
    monkeypatch.setattr(C.A, 'recipes', lambda graph: {C.C.OP: {'version': 1, 'amount': graph['amount']}})


def test_explicit_selection_requires_images_even_neutral():
    assert C.required([], {'selection': {C.C.OP: ['/amount']}}, {'intent': []})


@pytest.mark.parametrize('operation', ['create', 'patch', 'unlink'])
def test_retained_intent_requires_images_without_current_selected_module(operation):
    assert C.required([], {'selection': {}, 'operation': operation},
                      {'intent': [{'op': C.C.OP, 'path': '/amount', 'value': 0.}]})


@pytest.mark.parametrize('stage', ['before', 'candidate'])
def test_active_explicit_face_member_requires_cohort_images(monkeypatch, stage):
    resolver(monkeypatch); rows = endpoints()
    for row in rows: row['candidate']['amount'] = 0.
    rows[2][stage]['amount'] = .7
    assert C.required(rows, {'selection': {'lnx.deform.v1': ['/slim_face']}}, {'intent': []})


def test_unrelated_neutral_cohort_not_forced_into_collarbone_review(monkeypatch):
    resolver(monkeypatch); rows = endpoints()
    for row in rows: row['candidate']['amount'] = 0.
    assert not C.required(rows, {'selection': {}}, {'intent': []})


def test_coverage_uses_each_candidate_owner_and_own_face(monkeypatch):
    rows = endpoints(); observed = []
    def target(engine, row, candidate, payload, *, family):
        observed.append((row, candidate, deepcopy(payload), family)); return {'own': payload['target_refs']}
    monkeypatch.setattr(K, 'for_target', target)
    for row in rows: C.coverage(object(), row)
    for row, event in zip(rows, observed):
        assert event[0] is row['row'] and event[1] is row['candidate']
        assert event[2]['target_refs'] == [row['ref']]
        assert event[2]['target_document'] == row['proof']['document']
        assert event[3] == 'collarbone'


def test_prepare_includes_source_and_every_independent_target(monkeypatch):
    rows = endpoints(); calls = []; verified = []
    monkeypatch.setattr(C, 'coverage', lambda engine, row: {'owner': row['candidate']['owner']})
    def prepare(engine, row, before, candidate, document, revision, coverage):
        calls.append((row, before, candidate, document, revision, coverage))
        record = {'document_id': document, 'revision': revision}
        return record, {**record, 'before': {'base64': 'AAAA'}, 'after': {'base64': 'BBBB'}}
    monkeypatch.setattr(C.R, 'prepare', prepare)
    monkeypatch.setattr(C, 'verify', lambda engine, row, frozen: verified.append(row))
    displays = C.prepare(object(), rows)
    assert list(displays) == ['doc-0', 'doc-1', 'doc-2']
    assert [call[1] for call in calls] == [row['before'] for row in rows]
    assert [call[2] for call in calls] == [row['candidate'] for row in rows]
    assert verified == rows
    assert all('base64' not in str(row['collarbone_visual']) for row in rows)


def test_public_source_evidence_preserves_own_proof_and_compact_visual():
    row = endpoints()[0]
    row.update(collarbone_coverage={'owner': 0}, collarbone_visual={'document_id': 'doc-0'})
    result = W._public(row, live=True)
    assert result['live'] is True and result['association']['owner'] == row['proof']
    assert result['association']['collarbone_coverage'] == row['collarbone_coverage']
    assert result['association']['collarbone_visual'] == row['collarbone_visual']
    result['association']['collarbone_visual']['document_id'] = 'other'
    assert row['collarbone_visual']['document_id'] == 'doc-0'


def test_coverage_drift_refuses_before_identity_verification(monkeypatch):
    row = endpoints()[0]
    monkeypatch.setattr(C, 'coverage', lambda engine, item: {'owner': 0})
    with pytest.raises(ValueError, match='coverage'):
        C.verify(object(), row, {'collarbone_coverage': {'owner': 1}})


def test_verify_uses_same_actual_before_and_candidate_graph(monkeypatch):
    row = endpoints()[0]; own = {'owner': 0}; record = {'proof': 'frozen'}; seen = []
    monkeypatch.setattr(C, 'coverage', lambda engine, item: own)
    monkeypatch.setattr(C.R, 'verify', lambda *args: seen.append(args))
    C.verify(object(), row, {'collarbone_coverage': own, 'collarbone_visual': record})
    assert seen[0][1:] == (row['row'], row['before'], row['candidate'], 'doc-0', '0', own, record)


def test_cohort_ack_and_final_recheck_precede_claim_source_wiring():
    source = (Path(__file__).parents[1]/'src/lumaretouch_engine/people_cross_owner_workflow.py').read_text()
    commit = source[source.index('def commit('):]
    assert commit.index('CLAVICLE.R.acknowledgments') < commit.index('prepare(engine, selected, validate=False)')
    assert commit.index('prepare_scoped(engine, plans, targets)') < commit.index('CLAVICLE.verify(engine, item, json.loads(frozen.people_json))')
    assert commit.index('verify_available(controller.store, plan)') < commit.index('controller.store.claim(plan')
    assert "{target['document_id'] for target in targets.values()}" in commit
    assert "collarbone_cohort=True, collarbone_review_ack=deepcopy(visual_ack), module_scope=list(plan.modules)" in commit


def test_frozen_records_include_source_and_failed_attach_cleans_pending():
    source = (Path(__file__).parents[1]/'src/lumaretouch_engine/people_cross_owner_workflow.py').read_text()
    tree = ast.parse(source)
    preflight = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'preflight')
    frozen = next(node.value for node in preflight.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'frozen' for target in node.targets))
    assert isinstance(frozen, ast.ListComp) and ast.unparse(frozen.generators[0].iter) == 'endpoints'
    assert any(isinstance(node, ast.Call) and ast.unparse(node.func) == 'CLAVICLE.evidence'
               and len(node.args) == 1 and ast.unparse(node.args[0]) == 'item' for node in ast.walk(frozen))
    assert "'collarbone_visual_required': visual_required" in source
    handlers = [handler for node in ast.walk(preflight) if isinstance(node, ast.Try) for handler in node.handlers]
    assert any(any(isinstance(node, ast.Call) and ast.unparse(node.func) == 'controller.store.pending.pop'
                   and [ast.unparse(argument) for argument in node.args] == ['plan.token', 'None']
                   for node in ast.walk(handler))
               and any(isinstance(node, ast.Call) and ast.unparse(node.func) == 'prune'
                       and [ast.unparse(argument) for argument in node.args] == ['controller.store']
                       for node in ast.walk(handler)) for handler in handlers)
