"""AUTHORED / UNRUN. Qoder/local owner runs only after explicit native build.

No runtime, native, pixel, UI or persistence acceptance was run by the author.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import final_canvas_flip_state as S
from lumaretouch_engine import final_canvas_output as O

AXES = [(False, False), (True, False), (False, True), (True, True)]

def recipe(h=False, v=False):
    return {'horizontal': h, 'vertical': v}

@pytest.mark.parametrize('bad', [None, {}, [False, False], {'horizontal': False},
    {'horizontal': 1, 'vertical': False}, {'horizontal': False, 'vertical': 'false'},
    {'horizontal': False, 'vertical': False, 'extra': 0}])
def test_strict_boolean_recipe(bad):
    with pytest.raises(ValueError): S.check(bad)
    assert S.from_state({}) == recipe()


def test_neutral_object_identity_without_native(monkeypatch):
    def forbidden(): raise AssertionError('neutral loaded native')
    monkeypatch.setattr(O, 'native', forbidden)
    marker = object()
    assert O.processing_to_final(marker, recipe()) is marker

@pytest.mark.parametrize('dtype', [np.uint8, np.uint16, np.float32, np.float64])
@pytest.mark.parametrize('horizontal,vertical', AXES)
def test_asymmetric_exact_bits_no_mutation(dtype, horizontal, vertical):
    # Odd rectangular dimensions catch axis swaps, off-by-one and both-axis bugs.
    pixels = np.arange(7*11*3, dtype=dtype).reshape(7, 11, 3)
    if np.issubdtype(dtype, np.floating):
        pixels = pixels / dtype(13) - dtype(7)
        pixels[0, 0] = [-0., np.inf, np.nan]  # Reflection itself is byte-copy only.
    frozen = pixels.tobytes()
    spec = recipe(horizontal, vertical)
    got = O.processing_to_final(pixels, spec)
    expected = pixels[::-1 if vertical else 1, ::-1 if horizontal else 1]
    assert got.dtype == pixels.dtype and got.shape == pixels.shape
    assert got.tobytes() == expected.tobytes()
    assert pixels.tobytes() == frozen
    assert O.processing_to_final(got, spec).tobytes() == frozen
    if horizontal or vertical: assert not np.shares_memory(got, pixels)


def test_strided_exact_and_memory_refusal(monkeypatch):
    pixels = np.arange(15*21*3, dtype=np.uint16).reshape(15, 21, 3)[::2, ::2]
    assert O.processing_to_final(pixels, recipe(True)).tobytes() == pixels[:, ::-1].tobytes()
    monkeypatch.setattr(O, 'admit', lambda *_: (_ for _ in ()).throw(MemoryError('bounded refusal')))
    with pytest.raises(MemoryError): O.processing_to_final(pixels, recipe(True))


def test_neutral_hash_and_original_presentation_unchanged():
    from lumaretouch_engine.history_policy import state_signature
    from lumaretouch_engine.optics_candidate_identity import fingerprint
    from lumaretouch_engine.frame_presentation import make
    old = {'_strength': 0., '_crop_rect': (0., 0., 1., 1.)}
    neutral = {**old, S.KEY: recipe()}
    active = {**old, S.KEY: recipe(True)}
    assert state_signature(old) == state_signature(neutral)
    assert fingerprint(old) == fingerprint(neutral)
    assert state_signature(old) != state_signature(active)
    assert fingerprint(old) != fingerprint(active)
    assert make(1, (101, 77)) == make(1, (101, 77), flip=recipe())
    assert make(1, (101, 77)) != make(1, (101, 77), flip=recipe(True))
    assert make(1, (101, 77), kind='original') == make(1, (101, 77), kind='original', flip=recipe(True, True))
    with pytest.raises(ValueError): fingerprint({S.KEY: None})
    with pytest.raises(ValueError): state_signature({S.KEY: None})

@pytest.mark.parametrize('branch', ['active', 'inactive', 'undo', 'redo'])
def test_every_retained_project_branch_validates(branch):
    from lumaretouch_engine.final_canvas_flip_project import validate_records
    tree = {'active': {S.KEY: recipe()}, 'inactive': {S.KEY: recipe(True)},
            'undo': [{S.KEY: recipe(False, True)}], 'redo': [{S.KEY: recipe(True, True)}]}
    validate_records(tree)
    target = tree[branch][0] if branch in ('undo', 'redo') else tree[branch]
    target[S.KEY]['horizontal'] = 1
    with pytest.raises(ValueError): validate_records(tree)


def test_v23_migration_keeps_identity_and_rejects_new_recipe_in_old_schema(tmp_path):
    from lumaretouch_engine import project as P
    old = P.new_project('legacy', str(tmp_path))
    old['schema_version'] = P.IDENTITY_SCHEMA
    P.validate(old)
    upgraded = P._migrate(old)
    assert upgraded['schema_version'] == 'lrt.project.v24'
    assert upgraded['project_id'] == old['project_id']
    assert upgraded['source_assets'] == old['source_assets']
    assert upgraded['docs'] == old['docs']
    old[S.KEY] = recipe(True)
    with pytest.raises(P.ProjectError): P.validate(old)


def test_admission_inventories_account_for_neutral_flip():
    from dataclasses import fields
    from lumaretouch_engine.export import ExportSpec
    from lumaretouch_engine.creative_edited_capture_admission import SPEC_FIELDS, SNAPSHOT_FIELDS, SPEC_NEUTRAL_RECIPES, CORE_FIELDS
    assert {field.name for field in fields(ExportSpec)} == SPEC_FIELDS
    assert 'final_canvas_flip' in SNAPSHOT_FIELDS & SPEC_NEUTRAL_RECIPES
    assert 'final_canvas_flip' not in CORE_FIELDS  # Missing old snapshot stays neutral.

@pytest.mark.parametrize('horizontal,vertical', AXES)
@pytest.mark.parametrize('rotation', [0., 90., 17.])
@pytest.mark.parametrize('bits', [8, 16])
def test_export_full_canvas_parity_before_roi(bits, rotation, horizontal, vertical):
    from lumaretouch_engine.export import ExportSpec, export_image, export_image16
    dtype = np.uint16 if bits == 16 else np.uint8
    source = (np.arange(13*17*3, dtype=np.uint32).reshape(13, 17, 3)*71 % (65536 if bits == 16 else 256)).astype(dtype)
    crop = (.11, .13, .91, .89)
    spec = ExportSpec(strength=0., final_canvas_flip=recipe(horizontal, vertical))
    def render(domain):
        owned = deepcopy(spec)
        if bits == 16:
            return export_image16(source, owned, device='cpu', crop_rect=crop, rotation_degrees=rotation, output_domain=domain)[0]
        return export_image(source, owned, device='cpu', geometry=(crop, rotation), output_domain=domain)[0]
    processing, final = render('processing'), render('final')
    assert final.dtype == dtype
    assert final.tobytes() == processing[::-1 if vertical else 1, ::-1 if horizontal else 1].tobytes()


def test_new_captures_refused_but_source_recipe_is_not_changed():
    engine = SimpleNamespace(_final_canvas_flip=recipe(True), masks=object(), landmarks=object())
    before = engine.__dict__.copy()
    with pytest.raises(ValueError, match='坐标捕获'): S.require_processing_capture(engine)
    with pytest.raises(ValueError, match='创意素材捕获'): S.require_capture_state({S.KEY: recipe(True)})
    assert engine.__dict__ == before


class FakeEngine:
    """Only the command transaction ports, not a replacement renderer."""
    def __init__(self):
        self._load_id = '123'; self._final_canvas_flip = recipe(); self._project_dirty = False
        self._vram = SimpleNamespace(final_canvas_flip=recipe())
        self.history = SimpleNamespace(undo=[], redo=['retained'], group='', group_ns=0)
        self.frames = []; self.rev = 9; self.fail = False
    def _guard_editable(self, _): return None
    def _cancel_snapshot(self, _): pass
    def _close_owned_previews(self): pass
    def _history_capture(self): return {S.KEY: deepcopy(self._final_canvas_flip)}
    def _history_controller(self): return self.history
    def _write_current_frame(self, mode):
        if self.fail and mode == 'final_canvas_flip': raise MemoryError('render refused')
        self.frames.append((mode, deepcopy(self._final_canvas_flip)))
        return {'event': 'frame', 'mode': mode}
    def _history_record(self, group, before, *, coalesce):
        assert coalesce is False
        self.history.undo.append(before); self.history.redo.clear(); self.history.group = group; self._project_dirty = True
    def _fence_current_document(self): self.rev += 1
    def doc_state(self): return {S.KEY: deepcopy(self._final_canvas_flip)}
    def emit_session_state(self): pass


def request(rid='flip-one', **patch):
    return {'cmd': 'final_canvas_flip', 'request_id': rid, 'document_id': '123', 'revision': '9', **recipe(True), **patch}


def test_desired_state_replay_race_and_discrete_history(monkeypatch):
    from lumaretouch_engine import final_canvas_flip_host as H, extended_tone_host as T
    engine = FakeEngine(); monkeypatch.setattr(T, 'revision', lambda e: e.rev)
    monkeypatch.setattr(O, 'native', lambda: None)
    original = request()
    result = H.command(engine, original, lambda _: None)
    assert result['success'] and result['original_request'] == original and result['result_revision'] == '10'
    assert engine._final_canvas_flip == recipe(True) and len(engine.history.undo) == 1 and engine.rev == 10
    assert H.command(engine, original, lambda _: None) == result  # Exact receipt replay, no toggle/write.
    stale = H.command(engine, request('stale'), lambda _: None)
    assert not stale['success'] and stale['phase'] == 'rejected' and not stale['outcome_unknown']
    assert len(engine.history.undo) == 1 and engine._final_canvas_flip == recipe(True)
    H.command(engine, request('flip-two', revision='10', **recipe(True, True)), lambda _: None)
    assert len(engine.history.undo) == 2  # Never coalesce adjacent H/V clicks.
    cross = H.command(engine, request('cross', document_id='456'), lambda _: None)
    assert cross['phase'] == 'rejected' and not cross['success']
    with pytest.raises(ValueError): H.command(engine, {**original, 'document_id': '456'}, lambda _: None)


def test_render_failure_restores_recipe_history_and_dirty(monkeypatch):
    from lumaretouch_engine import final_canvas_flip_host as H, extended_tone_host as T
    engine = FakeEngine(); engine.fail = True
    monkeypatch.setattr(T, 'revision', lambda e: e.rev); monkeypatch.setattr(O, 'native', lambda: None)
    result = H.command(engine, request(), lambda _: None)
    assert result['phase'] == 'rolled_back' and not result['outcome_unknown'] and not result['success']
    assert engine._final_canvas_flip == recipe() and engine._vram.final_canvas_flip == recipe()
    assert engine.history.undo == [] and engine.history.redo == ['retained'] and not engine._project_dirty
    assert engine.rev == 9 and engine.frames[-1][0] == 'final_canvas_flip_rollback'


@pytest.mark.parametrize('mode', ['stale', 'missing_native', 'render', 'rollback', 'fence', 'success', 'replay'])
def test_private_recovery_outcomes_do_not_taint_known_refusals(monkeypatch, mode):
    from lumaretouch_engine import final_canvas_flip_host as H, extended_tone_host as T, project_recovery_runtime as R
    engine = FakeEngine(); engine._project_recovery_runtime = SimpleNamespace(tainted=False, reason=None, revision=4)
    monkeypatch.setattr(T, 'revision', lambda e: e.rev); monkeypatch.setattr(O, 'native', lambda: None)
    command = request()
    if mode == 'stale': command['revision'] = '8'
    if mode == 'missing_native': monkeypatch.setattr(O, 'native', lambda: (_ for _ in ()).throw(RuntimeError('native missing')))
    if mode == 'render': engine.fail = True
    if mode == 'rollback': engine._write_current_frame = lambda _: (_ for _ in ()).throw(MemoryError('all render failed'))
    if mode == 'fence':
        def partial_fence(): engine.rev += 1; raise RuntimeError('fence publication failed')
        engine._fence_current_document = partial_fence
    if mode == 'replay': H.command(engine, command, lambda _: None)
    boundary, handler = R.begin(engine, command, lambda r: H.command(engine, r, lambda _: None))
    result = handler(command); R.finish(engine, boundary)
    runtime = engine._project_recovery_runtime
    assert runtime.tainted == (mode in ('rollback', 'fence'))
    assert runtime.revision == (5 if mode == 'success' else 4)
    assert result['outcome_unknown'] == (mode in ('rollback', 'fence'))


@pytest.mark.parametrize('bits', [8, 16])
@pytest.mark.parametrize('scale,sharpen', [(1, 0.), (1, .2), (2, 0.), (2, .2)])
@pytest.mark.parametrize('grading', [False, True])
def test_arbitrary_geometry_float_finishing_no_integer_detour(monkeypatch, bits, scale, sharpen, grading):
    from lumaretouch_engine.export import ExportSpec, export_image, export_image16
    from lumaretouch_engine.photo_detail_stage import PhotoDetailStage
    from lumaretouch_engine import colour_grading_state as CG, selective_colour_state as SC
    source = (np.arange(40*40*3, dtype=np.uint32).reshape(40, 40, 3)*71 % (65536 if bits == 16 else 256)).astype(np.uint16 if bits == 16 else np.uint8)
    spec = ExportSpec(strength=0., scale=scale, sharpen_amount=sharpen, final_canvas_flip=recipe(True))
    if grading:
        spec.colour_grading = CG.neutral(); spec.colour_grading['midtones']['saturation'] = 12.
        spec.selective_colour = SC.neutral(); spec.selective_colour['ranges']['reds']['cyan'] = 8.
    seen=[]; real=PhotoDetailStage.apply_np
    def inspect(self, pixels):
        seen.append(pixels.dtype)
        assert pixels.dtype != np.float64  # Geometry has reentered supported finishing ABI.
        if bits == 16 or scale != 1 or sharpen or grading: assert pixels.dtype == np.float32
        return real(self, pixels)
    monkeypatch.setattr(PhotoDetailStage, 'apply_np', inspect)
    # Source crop is exactly 20x20; 17-degree bounds round consistently at scale 2.
    crop=(.1,.2,.6,.7)
    if bits == 16: output,_=export_image16(source,spec,device='cpu',crop_rect=crop,rotation_degrees=17.)
    else: output,_=export_image(source,spec,device='cpu',geometry=(crop,17.))
    assert seen and output.dtype == source.dtype
    assert output.shape[:2] == (25*scale,25*scale)


def test_project_save_reopen_named_versions_and_history(tmp_path):
    from PIL import Image
    from lumaretouch_engine import project as P, manual_liquify_state as ML
    source = tmp_path / 'original.png'
    Image.fromarray(np.arange(8*11*3, dtype=np.uint8).reshape(8, 11, 3)).save(source)
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    project = P.new_project('flip', str(tmp_path))
    base = {'_manual_liquify': ML.empty(), '_strength': 0., '_crop_rect': (0., 0., 1., 1.), '_crop_rotation': 0.}
    first = P.add_doc(project, str(source), {**base, S.KEY: recipe(True)}, version_id='horizontal', version_name='Horizontal original')
    did = first['document_id']
    second = P.add_doc(project, str(source), {**base, S.KEY: recipe(False, True)}, document_id=did, version_id='vertical', version_name='Vertical original')
    dropped = []
    second['document_history'] = P.encode({'undo': [{**base, S.KEY: recipe(True)}],
        'redo': [{**base, S.KEY: recipe(True, True)}]}, project['assets'], dropped, 'document_history')
    assert dropped == []
    path = tmp_path / 'flip.lrproject.json'
    P.save(project, str(path)); reopened = P.load(str(path))
    row = P.find_doc(reopened, document_id=did)
    assert [(v['id'], v['name']) for v in row['versions']] == [('horizontal', 'Horizontal original'), ('vertical', 'Vertical original')]
    assert row['versions'][0]['recipe'][S.KEY] == recipe(True)
    assert row['versions'][1]['recipe'][S.KEY] == recipe(False, True)
    history = P.decode(row['document_history'], reopened['assets'], [], 'history')
    assert history['undo'][0][S.KEY] == recipe(True)
    assert history['redo'][0][S.KEY] == recipe(True, True)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
