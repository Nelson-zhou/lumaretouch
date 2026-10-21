"""Unrecognized native ABI must be refused before any field access."""
from types import SimpleNamespace
import pytest
from lumaretouch_engine.ops import libraw as lr

@pytest.mark.parametrize('version', ['0.21.2-Release', '0.22.2-Release', 'unknown'])
def test_rejects_mismatched_abi_before_opening_handle(monkeypatch, version):
    fake = SimpleNamespace(libraw_version=lambda: version.encode())
    monkeypatch.setattr(lr, 'load_lib', lambda: fake)
    def forbidden_handle():
        pytest.fail('an unverified ABI reached handle/struct access')
    monkeypatch.setattr(lr, 'Handle', forbidden_handle)
    with pytest.raises(lr.LibRawUnavailable, match='ABI 版本不匹配'):
        lr.self_check()

def test_exact_table_version_is_required():
    fake = SimpleNamespace(libraw_version=lambda: lr.L.LIBRAW_VERSION.encode())
    assert lr._require_layout_version(fake) == lr.L.LIBRAW_VERSION
