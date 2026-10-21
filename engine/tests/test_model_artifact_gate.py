"""Release inventory must reject missing, altered and undeclared model bytes."""
import hashlib
import importlib.util
from pathlib import Path
import pytest

SCRIPT=Path(__file__).resolve().parents[2]/'packaging/check-model-artifacts.py'
spec=importlib.util.spec_from_file_location('artifact_gate',SCRIPT)
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def setup(tmp_path):
    p=tmp_path/'nested'/'model.tflite';p.parent.mkdir();p.write_bytes(b'fixed-model')
    row=dict(id='model',artifact=p.name,tier='bundled',sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
             size_bytes=p.stat().st_size,evidence='一手',weights_license='Apache-2.0')
    return {'models':[row]},p,row


def test_valid_bundle(tmp_path):
    ledger,_,_=setup(tmp_path)
    assert gate.validate(ledger,tmp_path)==[]


def test_missing_declared_bundle(tmp_path):
    ledger,p,_=setup(tmp_path);p.unlink()
    assert any('expected one' in x for x in gate.validate(ledger,tmp_path))


@pytest.mark.parametrize('suffix',sorted(gate.WEIGHT_SUFFIXES))
def test_unlisted_model_formats_are_rejected(tmp_path,suffix):
    ledger,_,_=setup(tmp_path)
    (tmp_path/('unreviewed'+suffix)).write_bytes(b'unknown')
    assert any('unlisted weight' in x for x in gate.validate(ledger,tmp_path))


def test_modified_tflite_bytes_are_rejected(tmp_path):
    ledger,p,_=setup(tmp_path);p.write_bytes(b'tampered!!!')
    assert any('sha256 mismatch' in x for x in gate.validate(ledger,tmp_path))


def test_conflicting_hash_aliases_are_rejected(tmp_path):
    ledger,_,row=setup(tmp_path);row['artifact_sha256']='f'*64
    assert any('conflicting' in x for x in gate.validate(ledger,tmp_path))


@pytest.mark.parametrize('field,value',[('size_bytes',123),('evidence','未核'),('weights_license','unknown'),('sha256',None)])
def test_incomplete_or_wrong_ledger_is_rejected(tmp_path,field,value):
    ledger,_,row=setup(tmp_path);row[field]=value
    assert gate.validate(ledger,tmp_path)


def test_duplicate_staged_copy_rejected(tmp_path):
    ledger,p,_=setup(tmp_path);(tmp_path/p.name).write_bytes(p.read_bytes())
    assert any('expected one' in x for x in gate.validate(ledger,tmp_path))


def test_symlink_not_followed(tmp_path):
    ledger,p,_=setup(tmp_path)
    (tmp_path/'extra.onnx').symlink_to('/nonexistent')
    assert any('symlink' in x for x in gate.validate(ledger,tmp_path))


def test_nonbundled_model_cannot_leak_into_package(tmp_path):
    ledger,_,row=setup(tmp_path);row['tier']='blocked'
    assert any('staged but tier' in x for x in gate.validate(ledger,tmp_path))


def test_release_script_calls_the_same_validator():
    sh=(SCRIPT.parent/'check-release.sh').read_text()
    assert 'python3 packaging/check-model-artifacts.py "$stage"' in sh
