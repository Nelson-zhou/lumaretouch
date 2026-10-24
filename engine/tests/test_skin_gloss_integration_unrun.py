"""AUTHORED / UNRUN. Registry/source routes are not photographic acceptance."""
from pathlib import Path
import ast

from lumaretouch_engine import people_algorithms as A
from lumaretouch_engine import skin_gloss_state as G
from lumaretouch_engine import creative_derived_effects as D


def test_separate_signed_gloss_does_not_expand_finish_or_colour_recipes():
    assert A.defaults()[G.OP] == {'/amount': 0.}
    assert A.defaults()['lnx.skin_finish.v1'] == {'/whitening': 0., '/rosiness': 0.}
    assert A.defaults()['lnx.skin_colour.v1'] == {'/temperature': 0., '/tint': 0.}
    assert G.OP in D.OPERATIONS


def test_real_native_readiness_and_packaged_core():
    root = Path(__file__).resolve().parents[2]
    source = root / 'engine/src/lumaretouch_engine'
    assert 'skin_gloss_capability()' in (source / 'server.py').read_text()
    stage = (root / 'packaging/stage-engine.sh').read_text()
    assert 'build-skin-gloss.sh' in stage
    assert 'liblrt_skin_gloss.so' in stage
    assert '"$here/../LICENSE" "$stage/lumaretouch_engine/third_party/skin_gloss/"' in stage


def test_gloss_does_not_add_body_authority_or_a_second_history_owner():
    root = Path(__file__).resolve().parents[2] / 'engine/src/lumaretouch_engine'
    support = (root / 'skin_colour_body_support.py').read_text()
    assert 'skin_gloss_body_visibility' not in support
    families = next(ast.literal_eval(node.value) for node in ast.parse(support).body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'FAMILIES'
                            for target in node.targets))
    assert families == ('skin_colour', 'skin_finish', 'body_skin_evenness', 'body_face_match')
    assert 'skin_gloss' not in families
    assert "LocalEffect(ref, 'skin_gloss'" not in (root / 'skin_colour_people.py').read_text()


def test_exact_handbook_mapping_is_separate_from_other_skin_texture_leaves():
    import json
    root = Path(__file__).resolve().parents[2]
    registry = json.loads((root / 'docs/p0/registry-extensions.json').read_text())
    entry = next(row for row in registry['entries'] if row['operation_id'] == G.OP)
    assert entry['requirement_ids'] == ['LNX-REF-PC-32465-C-1eed7cf9a9']
    assert entry['neutral'] == G.neutral()
