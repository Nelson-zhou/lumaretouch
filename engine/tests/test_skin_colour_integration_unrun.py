"""AUTHORED / UNRUN. Synthetic contracts, not photographic acceptance."""
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine import skin_colour_state as S, skin_colour_people as C
from lumaretouch_engine import people_algorithms as A


@pytest.mark.parametrize('bad', [True, '0', None, float('nan'), float('inf'), -1.01, 1.01])
def test_signed_amount_rejects_non_numeric_or_out_of_range(bad):
    with pytest.raises(ValueError):
        S.check({**S.neutral(), 'temperature': bad})


def test_new_operation_is_not_unsigned_eye_enhancement():
    assert S.OP in A.specifications()
    assert A.defaults()[S.OP] == {'/temperature': 0., '/tint': 0.}
    assert S.check({**S.neutral(), 'temperature': -1, 'tint': 1})['temperature'] == -1
    assert 'temperature' not in A.defaults()[A.ENHANCE]
    with pytest.raises(ValueError): S.check({**S.neutral(), 'face_ref': {}})
    with pytest.raises(ValueError): S.check({**S.neutral(), 'coverage': []})


def test_neutral_requires_no_anatomy_or_native_core():
    assert C.prepare(None, None, None, None, S.neutral(), byte_budget=0) == []


def test_memory_admission_precedes_rasterization(monkeypatch):
    from lumaretouch_engine import face_scope as F
    monkeypatch.setattr(F, 'selected_face_skin', lambda *a, **kw: pytest.fail('Unadmitted raster'))
    ref = {'asset_sha256': 'a'*64, 'face_instance_id': 'face', 'analysis_revision': 1}
    row = {'face_ref': ref, 'evidence': {'backend': 'mediapipe', 'semantic_model_sha256': 'b'*64}}
    with pytest.raises(ValueError, match='memory budget'):
        C.prepare(ref, row, [], np.zeros((4,4,3),np.float32),
                  {**S.neutral(), 'temperature': .5}, byte_budget=0)


def test_real_source_path_and_shared_history_wiring():
    root = Path(__file__).resolve().parents[2]
    source = root/'engine/src/lumaretouch_engine'
    read = lambda name: (source/name).read_text()
    runtime = read('people_render_runtime.py')
    assert "A.SKIN_COLOUR.active(values[A.SKIN_COLOUR.OP])" in runtime
    assert 'verify_analysis(other_face, other, (h,w))' in runtime
    assert 'analysis, others, effect_source' in runtime
    assert "source_effect(self,'skin_colour',out)" in read('vram.py')
    assert "'skin_colour'" in read('people_pipeline.py')
    assert 'lnx.skin_colour.v1' in read('creative_derived_effects.py')
    assert 'selected_face_skin(skin' in read('skin_colour_people.py')
    assert "analysis.get('face_skin')" in read('skin_colour_people.py')
    assert 'other_landmarks=others' in read('skin_colour_people.py')
    assert "skin_colour_capability()" in read('server.py')
    # Export installs the same prepared field bank, not a new per-tile solver.
    assert 'prepare_export' in read('people_export.py')
    assert 'at_dimensions' in read('people_engine_runtime.py')


def test_geometry_keeps_foreign_face_oval_and_features_out():
    # A deliberately artificial mesh only exercises masks, never a product face.
    from lumaretouch_engine import face_scope as F
    from lumaretouch_engine.ops import enhance as H
    lm = np.full((478,3), .5, np.float32)
    def ellipse(ids, cx, cy, rx, ry):
        for i, index in enumerate(ids):
            a = 2*np.pi*i/len(ids)
            lm[index,:2] = [cx+rx*np.cos(a), cy+ry*np.sin(a)]
    ellipse(F.FACE_OVAL,.5,.5,.4,.45)
    ellipse(H.EYE_RING_LEFT,.35,.35,.08,.04)
    ellipse(H.EYE_RING_RIGHT,.65,.35,.08,.04)
    ellipse(F.BROW_LEFT,.65,.25,.09,.025)
    ellipse(F.BROW_RIGHT,.35,.25,.09,.025)
    ellipse(F.LIPS,.5,.7,.12,.05)
    support = F.selected_face_skin(np.ones((128,128),np.float32),lm)
    assert support[45,45] == 0 and support[89,64] == 0
    assert not np.any(support[:3]) and np.any(support > .5)
    other = lm.copy()
    assert not np.any(F.selected_face_skin(np.ones((128,128),np.float32),lm,other_landmarks=[other]))
