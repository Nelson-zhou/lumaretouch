"""Explicit native parameter adaptation, never Adobe process emulation.

Only the syntax evidenced by Adobe's PV11.0 sample is admitted. Original XML is
retained byte-for-byte. Every encountered CRS property remains in the report.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import json
import math
import re
from . import xmp_document as X

MODE = 'native-parameter-adaptation-v1'
EXPOSURE = 'lnx.exposure.v1'
CURVES = 'lnx.curves.v1'
CURVE_FIELDS = ('ToneCurvePV2012', 'ToneCurvePV2012Red', 'ToneCurvePV2012Green', 'ToneCurvePV2012Blue')
METADATA = {'Version', 'PresetType', 'Name', 'ShortName', 'SortName', 'Group', 'Description', 'UUID',
            'Copyright', 'ContactInfo', 'HasSettings', 'AlreadyApplied'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return sha256(canonical(value)).hexdigest()


def scalar(properties, key):
    value = properties.get(key)
    return value if type(value) is str else None


def points(value):
    if type(value) is not list or not 2 <= len(value) <= 64:
        raise ValueError('Requires an explicit ordered sequence of 2–64 points')
    result = []
    for text in value:
        if type(text) is not str or not re.fullmatch(r'\s*\d{1,3}\s*,\s*\d{1,3}\s*', text):
            raise ValueError('Each point must be an integer x,y pair')
        x, y = (int(v.strip()) for v in text.split(','))
        if not 0 <= x <= 255 or not 0 <= y <= 255 or (result and x / 255. <= result[-1][0]):
            raise ValueError('Point coordinates must be 0–255 with strictly increasing x')
        result.append([x / 255., y / 255.])
    if result[0][0] != 0. or result[-1][0] != 1.:
        raise ValueError('Explicit endpoint x values 0 and 255 are required; no extrapolated points')
    return result


def analyse(document):
    props = document['properties']; candidates = {}; issues = {}
    process = scalar(props, 'ProcessVersion')
    supported_syntax = process == '11.0'
    reason = 'Only Adobe first-party sample ProcessVersion 11.0 syntax is admitted; no Adobe process is emulated'
    auto_exposure = props.get('AutoExposure') not in (None, 'False', 'false', '0')
    if 'Exposure2012' in props:
        try:
            if not supported_syntax: raise ValueError(reason)
            if 'Exposure' in props: raise ValueError('Mixed legacy and 2012 exposure is ambiguous')
            if auto_exposure: raise ValueError('Automatic exposure dependency cannot be imported as a fixed value')
            raw = props['Exposure2012']
            if type(raw) is not str or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', raw.strip()):
                raise ValueError('Exposure must be a finite decimal scalar')
            ev = float(raw)
            if not math.isfinite(ev) or not -5 <= ev <= 5: raise ValueError('Native EV range is −5 to +5; values are never clipped')
            candidates['exposure'] = {EXPOSURE: {'ev': ev}}
        except ValueError as error: issues['Exposure2012'] = str(error)
    if any(key in props for key in CURVE_FIELDS):
        try:
            if not supported_syntax: raise ValueError(reason)
            if any(key in props for key in ('ToneCurve', 'ToneCurveRed', 'ToneCurveGreen', 'ToneCurveBlue')):
                raise ValueError('Mixed legacy and 2012 point curves are ambiguous')
            if props.get('EnableToneCurve') not in (None, 'True', 'true', '1'):
                raise ValueError('Disabled or invalid tone-curve switch cannot be reinterpreted as active')
            if not all(key in props for key in CURVE_FIELDS):
                raise ValueError('All four explicit PV2012 curve arrays are required; absent channels are not reset silently')
            recipe = {'version': 1, 'space': 'srgb-display', 'interpolation': 'pchip', 'boundary': 'linear', 'enabled': True}
            for channel, field in zip(('master', 'red', 'green', 'blue'), CURVE_FIELDS): recipe[channel] = points(props[field])
            if props.get('ToneCurveName2012') == 'Linear' and any(x != y for channel in ('master', 'red', 'green', 'blue') for x, y in recipe[channel]):
                raise ValueError('Linear curve name contradicts the explicit nonidentity coordinates')
            candidates['point_curves'] = {CURVES: {'recipe': recipe}}
        except ValueError as error:
            for key in CURVE_FIELDS:
                if key in props: issues[key] = str(error)
    rows = []
    for key in sorted(props):
        if key in issues: status, why = 'invalid', issues[key]
        elif key == 'Exposure2012' and 'exposure' in candidates:
            status, why = 'adaptable', 'Explicit EV value becomes native exposure; Adobe response, baseline and processing order are not reproduced'
        elif key in CURVE_FIELDS and 'point_curves' in candidates:
            status, why = 'adaptable', 'All four arrays replace the entire native curve module, including previous luminance/parametric curves, using sRGB-display PCHIP rather than Adobe interpolation or color domain'
        elif key in METADATA: status, why = 'metadata', 'Preserved original metadata; not an image operation or compatibility guarantee'
        elif key == 'ProcessVersion': status, why = 'unsupported', reason
        elif key in ('WhiteBalance', 'Temperature', 'Tint', 'IncrementalTemperature', 'IncrementalTint'):
            status, why = 'unsupported', 'Adobe white balance is not native relative Kelvin/tint; no inferred reference or copied gains'
        elif 'Profile' in key or key in ('Look', 'LookTable', 'Table', 'Parameters'):
            status, why = 'unsupported', 'Camera/profile/look dependencies are preserved but not loaded, resolved, downloaded or emulated'
        else: status, why = 'unsupported', 'Preserved but not mapped; this effect does not become part of the native adaptation'
        rows.append({'name': key, 'status': status, 'value': deepcopy(props[key]), 'reason': why})
    for name, value in sorted(document.get('metadata', {}).get('other_properties', {}).items()):
        rows.append({'name': name, 'status': 'unsupported', 'value': deepcopy(value),
                     'reason': 'Non-CameraRaw property retained in original bytes; no rendering, metadata rewrite or external resource interpretation is performed'})
    adaptations = [{'id': key, 'title': 'Native exposure EV' if key == 'exposure' else 'Native four-channel point curves',
                    'module': next(iter(value)), 'reason': 'Explicit non-equivalent parameter reinterpretation; replaces this native module only'} for key, value in candidates.items()]
    report = {'version': 1, 'source_sha256': document['sha256'], 'filename': document['basename'],
              'byte_length': len(document['raw']), 'process_version': process, 'camera_raw_version': scalar(props, 'Version'),
              'properties': rows, 'adaptations': adaptations, 'can_import': bool(candidates),
              'warnings': ['This is not an Adobe-compatible rendering engine. All unsupported effects remain absent from the adaptation.',
                           'Only explicitly selected native modules are replaced. Unselected native edits remain unchanged.',
                           'Original XML bytes are preserved. Actual current-photo before/after review is required before applying.']}
    if not supported_syntax: report['warnings'].append(reason + '; received ' + repr(process))
    report['report_sha256'] = digest(report)
    return report, candidates


def select(document, acknowledgment):
    report, candidates = analyse(document)
    if type(acknowledgment) is not dict or set(acknowledgment) != {'source_sha256', 'report_sha256', 'mode', 'selected'}:
        raise ValueError('XMP requires explicit complete compatibility acknowledgment')
    if acknowledgment['mode'] != MODE or acknowledgment['source_sha256'] != report['source_sha256'] or acknowledgment['report_sha256'] != report['report_sha256']:
        raise ValueError('XMP content or compatibility report changed; inspect again')
    selected = acknowledgment['selected']
    if type(selected) is not list or not selected or any(type(key) is not str or key not in candidates for key in selected) or len(set(selected)) != len(selected):
        raise ValueError('Choose only valid explicit XMP adaptations; unsupported fields cannot be authorized as compatible')
    modules = {}
    for key in sorted(selected): modules.update(deepcopy(candidates[key]))
    return modules, sorted(selected), report


def retained(document, acknowledgment):
    modules, selected, report = select(document, acknowledgment)
    return modules, {'version': 1, 'source_sha256': document['sha256'], 'filename': document['basename'],
                     'source_base64': base64.b64encode(document['raw']).decode('ascii'), 'selected': selected, 'report': report}


def check(value, modules):
    if type(value) is not dict or set(value) != {'version', 'source_sha256', 'filename', 'source_base64', 'selected', 'report'} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Invalid retained XMP adaptation')
    if type(value['filename']) is not str or not value['filename']: raise ValueError('Retained XMP requires its original bounded filename')
    encoded = value['source_base64']
    if type(encoded) is not str or len(encoded) > 1_398_104: raise ValueError('Retained XMP bytes exceed the bound')
    try: raw = base64.b64decode(encoded, validate=True)
    except Exception as error: raise ValueError('Invalid original XMP byte encoding') from error
    document = X.parse(raw, basename=value['filename'])
    report, _ = analyse(document)
    expected, selected, report = select(document, {'mode': MODE, 'source_sha256': value['source_sha256'],
        'report_sha256': report['report_sha256'], 'selected': value['selected']})
    if canonical(expected) != canonical(modules) or canonical(report) != canonical(value['report']):
        raise ValueError('Retained XMP modules/report differ from the original bytes and explicit selection')
    return {'version': 1, 'source_sha256': document['sha256'], 'filename': document['basename'],
            'source_base64': encoded, 'selected': selected, 'report': report}


def public(value):
    return {key: deepcopy(item) for key, item in value.items() if key != 'source_base64'} | {'read_only_summary': True}
