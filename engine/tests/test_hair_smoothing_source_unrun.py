# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN static source-boundary fixtures; not source/runtime acceptance."""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'


def text(name):
    return (ROOT / ('hair_smoothing_' + name + '.py')).read_text()


def test_original_source_authority_is_internal_and_no_derived_loader():
    source = text('source')
    assert 'type(resolver) is not SourceResolver' in source and 'resolver._token is not _TOKEN' in source
    assert 'F.capture_original' in source and 'F.capture(engine, expected_source=source' in source
    assert 'export_source(' not in source and 'spec.source' not in source
    assert "proof['creative_source'] is not None" in source
    assert "snapshot.get('creative_source') is not None" in source


def test_neutral_source_factory_returns_before_snapshot_lookup():
    module=ast.parse(text('source'))
    factory=next(node for node in module.body if isinstance(node,ast.FunctionDef) and node.name=='from_export')
    assert isinstance(factory.body[1],ast.If) and isinstance(factory.body[1].body[0],ast.Return)


def test_replay_only_uses_existing_source_and_ordered_repair_plumbing_not_neck_detector():
    source=text('source')
    assert 'from .neck_wrinkle_source_capture import capture' in source
    assert 'neck_wrinkle_measure' not in source and 'neck_wrinkle_layer' not in source
    assert "'input_sha256': captured.input_sha256" in source
    assert "'repair_sha256': resolver.repair_sha256" in source
    assert 'np.frombuffer(captured.content' in source
    assert '32_000_000' in source


def test_metadata_freeze_not_proxy_or_pixel_recipe():
    source=text('inputs')
    assert "KEY = 'hair_smoothing_source_info'" in source
    assert "'active_sha256': R.digest_ops(active, [], bound)" in source
    assert "'repair_sha256': R.digest_ops(active, redo, bound)" in source
    assert 'base64' not in source and 'np.' not in source


def test_native_eligibility_survives_projection_and_replay():
    source=text('layer')
    assert 'eligibility=eligible' in source and 'eligibility=projected_eligibility' in source
    assert 'gain[blocked > 0] = 0' in source and "'authorizes_export': False" in source
    assert 'hair_smoothing_measure import measure' in source
    assert 'neck_wrinkle_measure' not in source


def test_fresh_review_geometry_gate_never_globally_forbids_replay():
    host=text('host');source=text('source')
    assert 'def require_geometry(' in host and 'require_geometry(snapshot, before, source)' in host
    assert "proof.get('source_size') != canonical_size" in host
    assert 'require_geometry' not in source
    for family in ('A.SLIM_FACE','A.FACE_CONTOUR','A.FACE_SIZE','A.LOWER_FACE','A.MID_FACE',
                   'A.CHIN_SHAPE','A.CHIN_LENGTH','A.PHILTRUM','A.EYE_SYMMETRY','A.HAIR_VOLUME'):
        assert family in host


def test_prompted_replay_explicitly_refuses_instead_of_inferring_or_skipping():
    source=text('support')
    assert "obj['kind'] == 'prompted'" in source
    assert 'PromptedJob' not in source and 'prompted_fields' not in source
    assert "face['asset_sha256'] == source['sha256'] and H.KIND in face['local_assets']" in source
