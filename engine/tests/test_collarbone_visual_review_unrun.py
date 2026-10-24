# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic transport contracts, not photo/algorithm acceptance."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import base64
import json
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import collarbone_transfer_review as R, full_candidate_render as F
from lumaretouch_engine.optics_candidate_identity import fingerprint


def fixture(monkeypatch, *, derived=False):
    source = {'asset_sha256': 'a'*64, 'original_sha256': ('b' if derived else 'a')*64,
              'creative_source': {'sha256': 'a'*64, 'width': 1200, 'height': 600} if derived else None}
    row = {'src_w': 1200, 'src_h': 600, 'state': {'_crop_rect': [0., 0., 1., 1.], '_crop_rotation': 0.}}
    engine = SimpleNamespace(); before = {'amount': 0., 'other_target': .2}; candidate = {'amount': .5, 'other_target': .7}
    calls = []
    def identity(owner, target, state, document, revision, *, people_graph):
        assert owner is engine and target is row and state is row['state']
        return {'document_id': document, 'revision': revision, 'source_proof': deepcopy(source),
                'candidate_sha256': fingerprint(state), 'people_sha256': fingerprint(people_graph)}, people_graph, {}
    def render(owner, target, state, document, revision, *, people_graph):
        proof, _, _ = identity(owner, target, state, document, revision, people_graph=people_graph)
        calls.append(deepcopy(people_graph))
        rgb = np.full((600, 1200, 3), .2+people_graph['amount']*.2, dtype=np.float32)
        return rgb, {**proof, 'source_size': [1200, 600], 'output_size': [1200, 600]}
    monkeypatch.setattr(F, 'identity', identity); monkeypatch.setattr(F, 'render', render)
    coverage = {'version': 1, 'support_transfer': 'none', 'targets': [{'scope': 'reviewed-clavicle-only'}]}
    return engine, row, before, candidate, coverage, calls


def prepare(data):
    return R.prepare(*data[:4], 'target-one', '7', data[4])


def ack(record):
    return {'document_id': record['document_id'], 'revision': record['revision'],
            'before_sha256': record['before']['sha256'], 'after_sha256': record['after']['sha256'],
            'coverage_sha256': record['coverage_sha256']}


@pytest.mark.parametrize('derived', [False, True])
def test_actual_full_pair_uses_complete_people_candidates(monkeypatch, derived):
    data = fixture(monkeypatch, derived=derived); prior = deepcopy(data[1]); record, public = prepare(data)
    assert data[5] == [data[2], data[3]] and data[1] == prior
    assert record['source_size'] == [1200, 600] and record['before']['width'] == 1024
    assert record['before']['height'] == 512 and record['coverage_sha256'] == R.coverage_digest(data[4])
    assert 'base64' not in json.dumps(record) and R.checked(record) == record
    for side in ('before', 'after'):
        raw = base64.b64decode(public[side]['base64'], validate=True)
        assert sha256(raw).hexdigest() == record[side]['sha256']
        assert len(raw) <= R.MAX_PNG_BYTES and len(public[side]['base64']) <= R.MAX_BASE64


def test_zero_reset_also_requires_pair_ack(monkeypatch):
    data = fixture(monkeypatch); data[2]['amount'] = .5; data[3]['amount'] = 0.
    record, _ = prepare(data)
    with pytest.raises(ValueError): R.acknowledgments(None, [record])
    assert R.acknowledgments([ack(record)], [record]) == [ack(record)]
    assert record['before']['sha256'] != record['after']['sha256']


@pytest.mark.parametrize('key', ['document_id', 'revision', 'before_sha256', 'after_sha256', 'coverage_sha256'])
def test_ack_rejects_each_changed_identity(monkeypatch, key):
    record, _ = prepare(fixture(monkeypatch)); value = ack(record); value[key] = 'changed'
    with pytest.raises(ValueError): R.acknowledgments([value], [record])


def test_ack_rejects_extra_fields_and_duplicates(monkeypatch):
    record, _ = prepare(fixture(monkeypatch)); value = ack(record)
    with pytest.raises(ValueError): R.acknowledgments([{**value, 'approved': True}], [record])
    with pytest.raises(ValueError): R.acknowledgments([value, value], [record, record])


def test_candidate_aggregate_drift_rejected(monkeypatch):
    data = fixture(monkeypatch); record, _ = prepare(data); data[3]['other_target'] = .8
    with pytest.raises(ValueError): R.verify(*data[:4], 'target-one', '7', data[4], record)


def test_local_coverage_drift_rejected(monkeypatch):
    data = fixture(monkeypatch); record, _ = prepare(data); data[4]['targets'][0]['scope'] = 'neutral-no-effect'
    with pytest.raises(ValueError): R.verify(*data[:4], 'target-one', '7', data[4], record)


def test_display_is_not_silently_reduced_to_fit_bytes(monkeypatch):
    data = fixture(monkeypatch); monkeypatch.setattr(R, 'MAX_PNG_BYTES', 1)
    with pytest.raises(ValueError, match='no lower-detail substitute'): prepare(data)


def test_compact_record_refuses_pixels_and_wrong_scale(monkeypatch):
    record, public = prepare(fixture(monkeypatch))
    with pytest.raises(ValueError): R.checked(public)
    record['after']['width'] = 256
    with pytest.raises(ValueError): R.checked(record)


def test_coverage_digest_is_ui_canonical_utf8():
    value = {'z': '女', 'a': [1, None, True]}
    assert R.coverage_digest(value) == sha256('{"a":[1,null,true],"z":"女"}'.encode()).hexdigest()


def test_batch_source_wiring_keeps_final_aggregate_and_private_records():
    source = (Path(__file__).parents[1]/'src/lumaretouch_engine/people_batch_transfer.py').read_text()
    assert "targets,displays=_collarbone_visuals(engine,rows,targets,public)" in source
    assert "people_json=canonical(payload)" in source
    assert "visible['people_transfer'] = deepcopy(payload)" in source
    assert "attach(controller.store,plan,displays)" in source
    assert "verify_available(controller.store,plan)" in source
    assert source.index('visual_review.verify(engine,row,scoped') < source.index('controller.store.claim(plan,collarbone_review_ack=visual_ack')
    assert "if visual_ack is not None:body['collarbone_review_ack']=deepcopy(visual_ack)" in source


def test_shared_source_alias_and_postprepare_aggregate_are_fenced():
    source = (Path(__file__).parents[1]/'src/lumaretouch_engine/people_batch_transfer.py').read_text()
    assert "if document(engine,row)['document_id'] not in reviewed" in source
    assert "if any(target['document_id'] not in reviewed for target in targets.values())" in source
    assert source.index("if any(target['document_id'] not in reviewed") < source.index('    prepare_scoped(engine,plans,targets)')
    assert source.index('    prepare_scoped(engine,plans,targets)') < source.index('visual_review.verify(engine,row,scoped')


def test_failed_attachment_discards_pending_plan_and_png_storage():
    source = (Path(__file__).parents[1]/'src/lumaretouch_engine/people_batch_transfer.py').read_text()
    assert "controller.store.pending.pop(plan.token,None)" in source
    assert "prune(controller.store)" in source
    assert source.index("len(json.dumps(body,ensure_ascii=True") < source.index('plan=controller.store.create(')
    assert source.index('verify_available(controller.store,plan)') < source.index('controller.store.claim(plan,collarbone_review_ack=visual_ack')


def test_unknown_terminal_retains_collarbone_scope_with_ack():
    source = (Path(__file__).resolve().parents[1] / 'src/lumaretouch_engine/people_batch_transfer.py').read_text()
    tail = source[source.index("    except Exception as error:\n        body={'success':False,'outcome_unknown':True"):]
    assert "body['collarbone_review_ack']=deepcopy(visual_ack)" in tail
    assert "body['module_scope']=list(plan.modules)" in tail
    assert tail.index("body['module_scope']=list(plan.modules)") < tail.index('controller.store.finish(plan,body)')


def test_preview_extent_integer_ties_even_and_large_dimensions():
    assert R.preview_size([2048, 5]) == (1024, 2)
    assert R.preview_size([2048, 7]) == (1024, 4)
    assert R.preview_size([7, 2048]) == (4, 1024)
    assert R.preview_size([4294967295, 1]) == (1024, 1)
    assert R.preview_size([1024, 17]) == (1024, 17)
