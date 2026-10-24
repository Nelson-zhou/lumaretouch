"""AUTHORED / UNRUN. Source route contracts, not runtime or photo acceptance."""
from pathlib import Path

from lumaretouch_engine import people_algorithms as A
from lumaretouch_engine import skin_finish_state as F


def test_distinct_unsigned_operation_keeps_signed_colour():
    assert A.defaults()[F.OP] == {'/whitening': 0., '/rosiness': 0.}
    assert A.defaults()['lnx.skin_colour.v1'] == {'/temperature': 0., '/tint': 0.}


def test_source_host_and_project_routes_preserve_separate_body_consent():
    root = Path(__file__).resolve().parents[2]
    source = root / 'engine/src/lumaretouch_engine'
    read = lambda name: (source / name).read_text()
    assert "skin_finish_capability()" in read('server.py')
    assert "family='skin_finish'" in read('people_project.py')
    assert "result['skin_finish_body']" in read('people_host.py')
    assert "'skin_finish_body_confirm'" in read('people_host_commands.py')
    assert "'skin_finish_body_visibility'" in read('people_support_assets.py')
    assert "'lnx.skin_finish.v1'" in read('creative_derived_effects.py')
    assert "skin_finish_body_assets=snapshot.get('support_assets',{})" in read('people_engine_runtime.py')


def test_packaged_core_has_independent_build_and_licence():
    root = Path(__file__).resolve().parents[2]
    stage = (root / 'packaging/stage-engine.sh').read_text()
    assert 'build-skin-finish.sh' in stage
    assert 'third_party/skin_finish' in stage
    assert (root / 'LICENSE').is_file()
    assert '"$here/../LICENSE" "$stage/lumaretouch_engine/third_party/skin_finish/"' in stage
    assert (root / 'core/skin_finish/README.md').is_file()


def test_one_existing_stage_not_independent_additive_finish_stage():
    root = Path(__file__).resolve().parents[2] / 'engine/src/lumaretouch_engine'
    text = (root / 'skin_colour_people.py').read_text()
    assert 'apply_finish(result, coverage' in text
    assert "LocalEffect(ref, 'skin_colour'" in text
    assert "LocalEffect(ref, 'skin_finish'" not in text
    assert 'result-original' in text
