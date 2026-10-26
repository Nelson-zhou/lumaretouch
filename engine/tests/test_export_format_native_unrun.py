"""AUTHORED / UNRUN: Original policy marshalling and installed native ABI.

No imports, collection, build, execution or codec activity during authoring.
Pure Rust policy vectors are also authored in core/export_format/tests.rs.
"""
import pytest
from lumaretouch_engine import export_format_native as N


def facts(**changes):
    return {'container': 'png', 'source_kind': 'bitmap', 'precision': 16,
            'single_frame': True, 'variant': 'encoded', **changes}


def capabilities(**changes):
    return {key: changes.get(key, True) for key in N.CAPABILITY_KEYS}


@pytest.fixture
def installed_native():
    status = N.readiness()
    if not status['export_original_format_available']:
        pytest.skip(status['export_original_format_reason'])
    return N


@pytest.mark.parametrize('container,bits,codec,options', [
    ('jpeg', 8, 'jpg', {'quality', 'gps', 'target_size'}),
    ('png', 8, 'png', {'quality', 'gps'}),
    ('png', 16, 'png', set()),
    ('tiff', 8, 'tif', {'tiff_compression', 'gps'}),
    ('tiff', 16, 'tif', {'tiff_compression'}),
    ('webp', 8, 'webp', {'quality', 'gps'}),
])
@pytest.mark.parametrize('variant', ['encoded', 'creative'])
def test_installed_native_supported_matrix(installed_native, container, bits, codec, options, variant):
    result = installed_native.resolve(facts(container=container, precision=bits, variant=variant), capabilities())
    assert result == {'codec': codec, 'bits': bits, 'extension': codec,
                      'applicable_options': {key: key in options for key in N.OPTION_KEYS}}


@pytest.mark.parametrize('container,bits,needed', [
    ('jpeg', 8, 'jpg8'), ('png', 8, 'png8'), ('png', 16, 'png16'),
    ('tiff', 8, 'tif8'), ('tiff', 16, 'tif16'), ('webp', 8, 'webp8'),
])
def test_installed_native_missing_codec_never_substitutes(installed_native, container, bits, needed):
    with pytest.raises(N.ExportFormatError) as error:
        installed_native.resolve(facts(container=container, precision=bits), capabilities(**{needed: False}))
    assert error.value.code == 'original_writer_unavailable'


@pytest.mark.parametrize('changes,code', [
    ({'source_kind': 'raw', 'container': 'tiff'}, 'original_raw_unsupported'),
    ({'source_kind': 'raw', 'variant': 'creative'}, 'original_raw_unsupported'),
    ({'source_kind': 'unknown'}, 'original_source_kind_unknown'),
    ({'container': 'unknown'}, 'original_container_unsupported'),
    ({'variant': 'unknown'}, 'original_source_variant_unsupported'),
    ({'single_frame': False}, 'original_single_frame_required'),
    ({'precision': 0}, 'original_precision_unsupported'),
    ({'precision': 12}, 'original_precision_unsupported'),
    ({'precision': 32}, 'original_precision_unsupported'),
    ({'container': 'jpeg'}, 'original_precision_unsupported'),
    ({'container': 'webp'}, 'original_precision_unsupported'),
])
def test_installed_native_refuses_without_fallback(installed_native, changes, code):
    with pytest.raises(N.ExportFormatError) as error:
        installed_native.resolve(facts(**changes), capabilities())
    assert error.value.code == code


@pytest.mark.parametrize('changes', [
    {'precision': True}, {'precision': '16'}, {'precision': -1}, {'precision': 2**32},
    {'single_frame': 1}, {'single_frame': None}, {'container': 'jpg'},
    {'source_kind': None}, {'variant': 'proxy'},
])
def test_malformed_facts_refuse_before_native(monkeypatch, changes):
    def forbidden():
        raise AssertionError('malformed host DTO must not enter native')
    monkeypatch.setattr(N, '_native', forbidden)
    with pytest.raises(N.ExportFormatError) as error:
        N.resolve(facts(**changes), capabilities())
    assert error.value.code == 'original_invalid_host_facts'


@pytest.mark.parametrize('bad', [None, {}, {'jpg8': True}, {**capabilities(), 'unknown': True}, capabilities(png16=1)])
def test_malformed_capabilities_refuse_before_native(monkeypatch, bad):
    def forbidden():
        raise AssertionError('malformed capabilities must not enter native')
    monkeypatch.setattr(N, '_native', forbidden)
    with pytest.raises(N.ExportFormatError) as error:
        N.resolve(facts(), bad)
    assert error.value.code == 'original_invalid_host_facts'


@pytest.mark.parametrize('code', ['original_policy_unavailable', 'original_policy_abi_mismatch'])
def test_missing_or_wrong_abi_never_resolves_in_python(monkeypatch, code):
    def unavailable():
        raise N.ExportFormatError(code)
    monkeypatch.setattr(N, '_native', unavailable)
    assert N.readiness()['export_original_format_available'] is False
    with pytest.raises(N.ExportFormatError) as error:
        N.resolve(facts(), capabilities())
    assert error.value.code == code


@pytest.mark.parametrize('packed', [0, 255, 3 | (2 << 8), 1 << 40,
                                  (2 << 8) | (16 << 16) | (3 << 24)])
def test_malformed_native_result_is_not_a_decision(monkeypatch, packed):
    class Library:
        def lrt_export_format_resolve(self, *_args):
            return packed
    monkeypatch.setattr(N, '_native', lambda: Library())
    with pytest.raises(N.ExportFormatError) as error:
        N.resolve(facts(), capabilities())
    assert error.value.code == 'original_policy_invalid_result'
