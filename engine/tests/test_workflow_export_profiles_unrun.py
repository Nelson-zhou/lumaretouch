"""SOURCE-AUTHORED / UNRUN. No encoder, runtime or photographic acceptance claimed."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import workflow_owner_protocol as P
from lumaretouch_engine import workflow_owner_export as E


def test_legacy_profile_is_unchanged_and_catalogue_is_exact_and_detached():
    rows = P.export_profiles()
    assert len(rows) == 5
    assert rows[0] == {'recipe_sha256': P.RECIPE_SHA256, 'recipe_profile': P.RECIPE_PROFILE}
    assert len({row['recipe_sha256'] for row in rows}) == 5
    assert [(r['recipe_profile']['export_options']['format'],
             r['recipe_profile']['export_options']['quality'],
             r['recipe_profile']['export_options']['bit_depth']) for r in rows] == [
                 ('jpg', 95, 8), ('jpg', 80, 8), ('jpg', 100, 8), ('png', 95, 8), ('tif', 95, 16)]
    rows[0]['recipe_profile']['export_options']['quality'] = 1
    assert P.export_profiles()[0]['recipe_profile']['export_options']['quality'] == 95


def test_expanded_profiles_require_automatic_mode_and_reject_unknown_settings():
    for row in P.export_profiles()[1:]:
        with pytest.raises(ValueError, match='Unsupported export profile'):
            P.resolve_export_profile(row['recipe_sha256'])
        assert P.resolve_export_profile(row['recipe_sha256'], automatic=True) == row['recipe_profile']
    for changed in ({'quality': 90}, {'format': 'webp'}, {'scale': 2}, {'output_profile': 'source'}):
        profile = deepcopy(P.RECIPE_PROFILE); profile['export_options'].update(changed)
        with pytest.raises(ValueError, match='No format fallback'):
            P.resolve_export_profile(P.digest(profile), automatic=True)


@pytest.mark.parametrize('index,extension', [(0, 'jpg'), (1, 'jpg'), (2, 'jpg'), (3, 'png'), (4, 'tif')])
def test_freeze_pins_exact_command_options_and_real_planner_targets(monkeypatch, index, extension):
    row = P.export_profiles()[index]
    target = '/output/photo.' + extension
    def planner(engine, command, roots):
        for key, value in row['recipe_profile']['export_options'].items():
            assert command[key] == value
        assert command['destination_policy']['conflict'] == 'ask'
        assert command['destination_policy']['create_missing'] is False
        return {'plan_id': 'actual-plan', 'entries': [{'disposition': 'write', 'target': target}]}
    monkeypatch.setattr(E, 'preview', planner)
    frozen = E.freeze(SimpleNamespace(), {'document_id': 'doc'}, {'document_revision': 'rev'},
                      '/output', 1, 'request', {'/output': ['1', '2']}, recipe_sha256=row['recipe_sha256'])
    assert frozen['plan']['targets'] == [target]
    assert frozen['plan']['recipe_sha256'] == row['recipe_sha256']
    assert frozen['plan']['plan_sha256'] == P.digest(frozen['destination'])


@pytest.mark.parametrize('disposition', ['skip', 'rename', 'ask'])
def test_no_collision_resolution_is_invented(monkeypatch, disposition):
    monkeypatch.setattr(E, 'preview', lambda *args: {'plan_id': 'plan',
        'entries': [{'disposition': disposition, 'target': '/output/photo.png'}]})
    with pytest.raises(ValueError, match='collides'):
        E.freeze(SimpleNamespace(), {'document_id': 'doc'}, {'document_revision': 'rev'},
                 '/output', 1, 'request', {'/output': ['1', '2']},
                 recipe_sha256=P.export_profiles()[3]['recipe_sha256'])
