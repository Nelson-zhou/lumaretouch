"""AUTHORED / UNRUN. Source wiring is not numerical or photographic acceptance."""
from pathlib import Path
import ast
import json

from lumaretouch_engine import people_algorithms as A
from lumaretouch_engine import skin_texture_state as T
from lumaretouch_engine import creative_derived_effects as D


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'engine/src/lumaretouch_engine'


def test_independent_registered_controls_and_derived_consumer():
    assert A.defaults()[T.OP] == {'/texture': 0., '/clarity': 0.}
    assert T.OP in D.OPERATIONS
    assert A.defaults()['lnx.skin_gloss.v1'] == {'/amount': 0.}


def test_exact_two_handbook_ids_and_neutral():
    registry = json.loads((ROOT / 'docs/p0/registry-extensions.json').read_text())
    entry = next(row for row in registry['entries'] if row['operation_id'] == T.OP)
    assert entry['requirement_ids'] == ['LNX-REF-PC-32465-C-1c80d411ce', 'LNX-REF-PC-32465-C-46e0c819b6']
    assert entry['neutral'] == T.neutral()


def test_native_build_header_license_and_ready_connection():
    stage = (ROOT / 'packaging/stage-engine.sh').read_text()
    for token in ('build-skin-texture.sh', 'liblrt_skin_texture.so', 'core/skin_texture/skin_texture.h',
                  'core/skin_texture/README.md', 'third_party/skin_texture/'):
        assert token in stage
    assert 'skin_texture_capability()' in (SOURCE / 'server.py').read_text()


def test_no_body_authority_or_parallel_skin_effect_owner():
    support = (SOURCE / 'skin_colour_body_support.py').read_text()
    families = next(ast.literal_eval(node.value) for node in ast.parse(support).body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'FAMILIES'
                            for target in node.targets))
    assert families == ('skin_colour', 'skin_finish', 'body_skin_evenness')
    assert 'skin_texture' not in families and 'skin_texture_body_visibility' not in support
    renderer = (SOURCE / 'skin_colour_people.py').read_text()
    assert "LocalEffect(ref, 'skin_texture'" not in renderer
    assert 'reference_rgb=reference, radius=texture_radius' in renderer
    assert "if stage=='skin_colour':" in (SOURCE / 'people_pipeline.py').read_text()
