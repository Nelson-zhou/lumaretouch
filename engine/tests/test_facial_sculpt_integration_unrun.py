# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Shared route and historical identity regressions."""
from copy import deepcopy
from pathlib import Path
import pytest
from lumaretouch_engine import people_state as P, people_algorithms as A
from lumaretouch_engine import people_source_context as CONTEXT
from lumaretouch_engine import facial_sculpt_state as S

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def graph():
    state = P.empty()
    evidence = {'backend': 'authored_fixture', 'detector_model_sha256': None,
                'semantic_model_sha256': None, 'landmark_digest': None,
                'status': 'synthetic', 'source_width': 640, 'source_height': 480,
                'orientation': 'exif_normalized_once'}
    face = P.new_face('a'*64, (.1, .1, .8, .8), evidence)
    face['face_instance_id'] = 'fixture-face'
    state['faces']['fixture-face'] = face
    state['persons']['fixture-person'] = {'anonymous': True}
    state['links'] = [{'face_instance_id': 'fixture-face', 'person_id': 'fixture-person',
                       'state': 'confirmed', 'confirmation_revision': 0}]
    state['groups']['fixture-group'] = {'label': 'Fixture', 'priority': 0, 'face_ids': ['fixture-face']}
    return P.check(state)


def test_old_context_digest_ignores_only_new_implicit_defaults(monkeypatch):
    state = graph()
    defaults = A.defaults()
    old = deepcopy(defaults)
    old.pop(S.OP)
    monkeypatch.setattr(A, 'defaults', lambda: deepcopy(old))
    before = CONTEXT.digest(state, 'a'*64)
    monkeypatch.setattr(A, 'defaults', lambda: deepcopy(defaults))
    assert CONTEXT.digest(state, 'a'*64) == before


@pytest.mark.parametrize('scope,target', [('face', 'fixture-face'), ('all_people', 'a'*64),
                                        ('person', 'fixture-person'), ('group', 'fixture-group')])
def test_context_keeps_explicit_new_intent_even_neutral(scope, target):
    state = graph()
    edited = P.set_override(state, scope, target, S.OP, '/highlight', 0.0)
    assert CONTEXT.digest(state, 'a'*64) != CONTEXT.digest(edited, 'a'*64)


def test_source_route_uses_full_renderer_and_owned_bank():
    runtime = (ENGINE / 'people_render_runtime.py').read_text()
    assert 'A.FACIAL_SCULPT.validate_graph(state)' in runtime
    assert 'sculpt_budget=byte_budget-owned' in runtime
    assert runtime.index('if sculpt_budget <') < runtime.index('sculpt_review = sculpt_raster')
    assert 'byte_budget=sculpt_budget' in runtime
    assert 'local.append(sculpt_record)' in runtime
    pipeline = (ENGINE / 'people_pipeline.py').read_text()
    assert 'from .facial_sculpt_composition import apply_records_t' in pipeline
    assert "out=PEOPLE_PIPE.source_effect(self,'facial_sculpt',out)" in (ENGINE / 'vram.py').read_text()
    assert "facial_sculpt_assets=snapshot.get('support_assets',{})" in (ENGINE / 'people_engine_runtime.py').read_text()


def test_exact_reference_and_mutating_review_have_separate_routes():
    source = (ENGINE / 'people_host_commands.py').read_text()
    assert "SCULPT_READS = frozenset(('facial_sculpt_reference',))" in source
    assert "SCULPT_ACTIONS = SCULPT_READS | {'facial_sculpt_review'}" in source
    assert "'facial_sculpt_request'" in source
    assert 'require_sculpt_transition' in (ENGINE / 'people_host.py').read_text()
    assert 'require_sculpt_transition' in (ENGINE / 'people_candidate_render.py').read_text()


def test_released_reference_finishes_without_a_document_mutation():
    workflow = (ROOT / 'ui/src/people/workflow.ts').read_text()
    assert '(faceStyleRead || decorationReleased || sculptReleased)' in workflow
    assert 'facialSculptReleasedRequestId: sculptReleased ? command.request_id : null' in workflow
    panel = (ROOT / 'ui/src/facialSculpt/FacialSculptPanel.tsx').read_text()
    assert 'people.state.facialSculptReleasedRequestId === reference.request.request_id' in panel


def test_current_photo_transition_refuses_cross_source_and_aliases():
    source = (ENGINE / 'facial_sculpt_project.py').read_text()
    assert 'if changed - {asset}:' in source
    assert 'require_unaliased(engine, actual, changed)' in source
