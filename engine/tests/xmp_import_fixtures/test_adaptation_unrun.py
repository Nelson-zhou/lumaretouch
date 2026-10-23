"""AUTHORED / UNRUN. Synthetic contracts, not Adobe fidelity or executed tests."""
from copy import deepcopy
from hashlib import sha256
import pytest
from lumaretouch_engine import xmp_adaptation as A


def document(**props):
    raw = b'synthetic parser-independent input'
    return {'raw': raw, 'sha256': sha256(raw).hexdigest(), 'basename': 'sample.xmp',
            'properties': {'ProcessVersion': '11.0', **props}}


def ack(report, selected):
    return {'mode': A.MODE, 'source_sha256': report['source_sha256'],
            'report_sha256': report['report_sha256'], 'selected': selected}


def test_exposure_is_absolute_native_parameter_not_added_or_adobe_emulated():
    doc = document(Exposure2012='+1.25', Temperature='5500', CameraProfile='Embedded')
    report, candidates = A.analyse(doc)
    assert candidates == {'exposure': {A.EXPOSURE: {'ev': 1.25}}}
    assert all(row['status'] == 'unsupported' for row in report['properties'] if row['name'] in ('Temperature', 'CameraProfile', 'ProcessVersion'))
    assert A.select(doc, ack(report, ['exposure']))[0] == candidates['exposure']


@pytest.mark.parametrize('value', ['6', '-6', 'NaN', 'inf', '', '1,2'])
def test_invalid_exposure_is_reported_not_clamped(value):
    report, candidates = A.analyse(document(Exposure2012=value))
    assert not candidates and not report['can_import']
    assert next(row for row in report['properties'] if row['name'] == 'Exposure2012')['status'] == 'invalid'


@pytest.mark.parametrize('process', [None, '6.7', '10.0', '15.0', '11', '11.00'])
def test_unknown_process_never_silently_uses_pv11_sample(process):
    doc = document(Exposure2012='1'); doc['properties']['ProcessVersion'] = process
    report, candidates = A.analyse(doc)
    assert not candidates and not report['can_import']


def test_complete_curve_group_uses_all_explicit_channels():
    props = {field: ['0, 0', '128, 150', '255, 255'] for field in A.CURVE_FIELDS}
    report, candidates = A.analyse(document(**props))
    recipe = candidates['point_curves'][A.CURVES]['recipe']
    assert recipe['interpolation'] == 'pchip' and recipe['space'] == 'srgb-display'
    assert recipe['red'][1] == [128 / 255, 150 / 255]
    del props['ToneCurvePV2012Blue']
    assert 'point_curves' not in A.analyse(document(**props))[1]


@pytest.mark.parametrize('points', [['1, 0', '255, 255'], ['0, 0', '256, 255'],
                                  ['0, 0', '128, 50', '128, 80', '255, 255'],
                                  ['0, 0', '127.5, 128', '255, 255']])
def test_curve_nodes_are_never_sorted_synthesized_or_quantized(points):
    with pytest.raises(ValueError): A.points(points)


def test_ambiguous_active_settings_and_legacy_mix_block_selected_group():
    assert not A.analyse(document(Exposure2012='1', Exposure='1'))[1]
    assert not A.analyse(document(Exposure2012='1', AutoExposure='True'))[1]
    props = {field: ['0, 0', '128, 150', '255, 255'] for field in A.CURVE_FIELDS}
    assert not A.analyse(document(**props, ToneCurveName2012='Linear'))[1]
    assert not A.analyse(document(**props, EnableToneCurve='False'))[1]


def test_report_content_and_selection_are_explicitly_bound():
    doc = document(Exposure2012='1'); report, _ = A.analyse(doc)
    consent = ack(report, ['exposure']); consent['report_sha256'] = '0' * 64
    with pytest.raises(ValueError): A.select(doc, consent)
    with pytest.raises(ValueError): A.select(doc, ack(report, ['white_balance']))
    with pytest.raises(ValueError): A.select(doc, ack(report, ['exposure', 'exposure']))
    changed = deepcopy(doc); changed['properties']['Temperature'] = '6000'
    with pytest.raises(ValueError): A.select(changed, ack(report, ['exposure']))


def test_portable_original_bytes_and_report_are_revalidated():
    from lumaretouch_engine import xmp_document as X
    raw = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
           b'<r:RDF xmlns:r="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
           b'xmlns:p="http://ns.adobe.com/camera-raw-settings/1.0/">'
           b'<r:Description r:about="" p:ProcessVersion="11.0" p:Exposure2012="1.25"/>'
           b'</r:RDF>')
    doc = X.parse(raw, basename='synthetic.xmp'); report, _ = A.analyse(doc)
    modules, retained = A.retained(doc, ack(report, ['exposure']))
    assert A.check(retained, modules) == retained
    import base64
    assert base64.b64decode(retained['source_base64']) == raw
    assert 'source_base64' not in A.public(retained)
    altered = deepcopy(retained); altered['report']['warnings'] = []
    with pytest.raises(ValueError): A.check(altered, modules)
    altered = deepcopy(modules); altered[A.EXPOSURE]['ev'] = 2
    with pytest.raises(ValueError): A.check(retained, altered)


def test_review_ack_binds_both_actual_pngs_and_compatibility_report():
    from lumaretouch_engine.preset_xmp_import import acknowledgment
    record = {'preset': {'xmp_import': {'report': {'source_sha256': 'a' * 64, 'report_sha256': 'b' * 64}}},
              'xmp': {'before': {'sha256': 'c' * 64}, 'after': {'sha256': 'd' * 64}}}
    value = {'source_sha256': 'a' * 64, 'report_sha256': 'b' * 64,
             'before_sha256': 'c' * 64, 'after_sha256': 'd' * 64}
    acknowledgment(value, record)
    for key in value:
        bad = deepcopy(value); bad[key] = 'e' * 64
        with pytest.raises(ValueError): acknowledgment(bad, record)


def test_corrupt_xmp_is_one_catalogue_error_not_loss_of_all_presets(tmp_path, monkeypatch):
    import json
    from lumaretouch_engine import preset_store as PS
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path))
    invalid = {'schema': 'lrt.preset.v1', 'id': 'broken-xmp', 'name': 'Broken XMP',
               'kind': 'color', 'modules': {A.EXPOSURE: {'ev': 1}}, 'xmp_import': {'version': 999}}
    (tmp_path / 'broken-xmp.json').write_text(json.dumps(invalid))
    docs, errors = PS.raw_list_all()
    assert any(row['id'] == 'color-warm' for row in docs)
    assert any('broken-xmp.json' in row['file'] for row in errors)


def test_non_camera_raw_properties_are_visible_not_silently_dropped():
    doc = document(Exposure2012='1')
    doc['metadata'] = {'other_properties': {'{https://example.invalid/settings}effect': {'kind': 'structure', 'fields': {}}}}
    report, _ = A.analyse(doc)
    row = next(row for row in report['properties'] if row['name'].startswith('{https://example.invalid/'))
    assert row['status'] == 'unsupported' and row['value']['kind'] == 'structure'
