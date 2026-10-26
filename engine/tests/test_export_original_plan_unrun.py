"""Authored UNRUN host-integration fixtures; not codec/runtime acceptance.

The fake resolver below is an explicit test double, never a production fallback.
Real native ABI/header/decoder/writer acceptance is listed in the handoff matrix.
"""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from lumaretouch_engine import export_format_plan as F
from lumaretouch_engine import export_format_native as N
from lumaretouch_engine import export_source_facts as S
from lumaretouch_engine import export_destination_policy as D
from lumaretouch_engine import export_destination_runtime as R


def fixture_source(tmp_path, name, identity, container, bits):
    # These bytes are deliberately not an image: this fixture covers the frozen
    # host contract only. It must never be presented as successful pixel decode.
    path = tmp_path / name
    data = ('host-contract-only-' + identity).encode()
    path.write_bytes(data)
    info = path.stat()
    fp = {'path':str(path), 'bytes':len(data), 'sha256':sha256(data).hexdigest(),
          'head_sha256':sha256(data).hexdigest(), 'hash_level':'full',
          'mtime_ns':info.st_mtime_ns, 'readonly':False}
    facts = {'schema':S.SCHEMA, 'container':container, 'source_kind':'bitmap',
        'precision':bits, 'single_frame':True, 'variant':'encoded', 'fingerprint':fp,
        'decoder_stamp':{'inspector':S.INSPECTOR,
            'file_stamp':[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns],
            'width':3, 'height':2, 'orientation':1, 'encoding':'unsigned-integer',
            'frames':1, 'source_variant':'rgb'},
        'effective_asset':{'kind':'encoded', 'sha256':fp['sha256']}}
    facts['fact_id'] = D.digest(facts)
    row = {'path':str(path), 'document_id':identity, 'source_asset_id':'source-'+identity,
           'recipe_version_id':'recipe-'+identity, 'copy_number':0}
    key = 'document:' + sha256(identity.encode()).hexdigest()
    entry = {**row, 'fingerprint':fp, 'source_facts':facts, 'stem':identity}
    return row, key, entry


def fixture_resolver(facts, capabilities):
    assert all(capabilities.values())
    codec = {'jpeg':'jpg', 'png':'png', 'tiff':'tif', 'webp':'webp'}[facts['container']]
    bits = facts['precision']
    return {'codec':codec, 'bits':bits, 'extension':codec, 'applicable_options':{
        'quality':bits == 8 and codec != 'tif', 'tiff_compression':codec == 'tif',
        'gps':bits == 8, 'target_size':codec == 'jpg' and bits == 8}}


@pytest.fixture
def native_double(monkeypatch):
    monkeypatch.setattr(N, 'resolve', fixture_resolver)
    monkeypatch.setattr(S, 'capabilities', lambda:dict.fromkeys(N.CAPABILITY_KEYS, True))


def freeze_cases(cases, **changes):
    entries = {key:entry for _,key,entry in cases}
    snapshots = {key:({'exposure':0.0, 'creative_base':None}, True) for _,key,_ in cases}
    options = dict(quality=95, tiff_compression=None, metadata_include_gps=False,
                   target_size=None, output_profile='srgb')
    options.update(changes)
    envelope = F.freeze(list(entries), entries, snapshots, **options)
    return entries, snapshots, envelope


def destination(tmp_path, cases, envelope):
    output = tmp_path / 'output'
    output.mkdir()
    rows = [row for row,_,_ in cases]
    version = SimpleNamespace(workspace='workspace', version=lambda row:SimpleNamespace(
        document_id=row['document_id'], revision=2))
    engine = SimpleNamespace(_docs=rows, _document_versions=lambda:version)
    settings = {'format':'original', 'format_plan':envelope, 'watermark':{'alsoClean':True}}
    plan = R.build(engine, rows, [key for _,key,_ in cases],
        {key:entry for _,key,entry in cases}, settings,
        D.Policy(chosen_root=str(output), create_missing=True).__dict__, 7)
    return plan, settings


def test_mixed_plan_preserves_codec_precision_and_clean_paths(tmp_path, native_double):
    cases = [fixture_source(tmp_path,'misleading.tif','one','jpeg',8),
             fixture_source(tmp_path,'misleading.jpg','two','png',16),
             fixture_source(tmp_path,'three.bin','three','tiff',16)]
    entries, snapshots, envelope = freeze_cases(cases)
    plan, settings = destination(tmp_path, cases, envelope)
    assert len(plan.entries) == 6
    for key, entry in entries.items():
        decision = entry['format_decision']
        outputs = [e for e in plan.entries if e.item_id in (key,key+'::clean')]
        assert len(outputs) == 2 and len({e.target for e in outputs}) == 2
        assert all(e.target.endswith('.'+decision['codec']) for e in outputs)
        assert decision['options']['tiff_compression'] == ('none' if decision['codec']=='tif' else None)
    assert 'bit_depth' not in json.loads(plan.settings_json)
    assert D.restore(plan.payload()).plan_id == plan.plan_id


def test_worker_uses_retained_decisions_not_resolver(tmp_path, native_double, monkeypatch):
    cases = [fixture_source(tmp_path,'source.bin','one','png',16)]
    entries, snapshots, envelope = freeze_cases(cases)
    plan, _ = destination(tmp_path, cases, envelope)
    key = cases[0][1]
    opts = {'format_plan':envelope, 'destination_plan':plan.payload()}
    def forbidden(*_):
        raise AssertionError('retry/worker must never resolve another format')
    monkeypatch.setattr(N, 'resolve', forbidden)
    stamp = entries[key]['source_facts']['decoder_stamp']['file_stamp']
    assert F.worker_decision(opts,key,entries[key],snapshots[key][0],source_stamp=stamp)['bits'] == 16
    changed = deepcopy(snapshots[key][0]); changed['exposure'] = 0.25
    with pytest.raises(ValueError,match='recipe_changed'):
        F.worker_decision(opts,key,entries[key],changed)
    with pytest.raises(ValueError,match='source_stamp_changed'):
        F.worker_decision(opts,key,entries[key],snapshots[key][0],source_stamp=[*stamp[:-1],stamp[-1]+1])


def test_target_size_and_gps_reject_entire_mixed_intent_before_destination(tmp_path,native_double):
    cases = [fixture_source(tmp_path,'one','one','jpeg',8),
             fixture_source(tmp_path,'two','two','tiff',16)]
    with pytest.raises(ValueError,match='GPS'):
        freeze_cases(cases,metadata_include_gps=True)
    from lumaretouch_engine.export_target_size_policy import TargetSize
    with pytest.raises(ValueError,match='JPEG8'):
        freeze_cases(cases,target_size=TargetSize(100000,1000).wire())
    assert not (tmp_path/'output').exists()


def test_tiff_options_apply_only_to_tiff_and_defaults_differ(tmp_path,native_double):
    cases = [fixture_source(tmp_path,'a','a','tiff',8),
             fixture_source(tmp_path,'b','b','tiff',16),
             fixture_source(tmp_path,'c','c','png',8)]
    entries, _, _ = freeze_cases(cases)
    assert [entries[key]['format_decision']['options']['tiff_compression'] for _,key,_ in cases] == ['deflate','none',None]
    entries, _, _ = freeze_cases(cases,tiff_compression='lzw')
    assert [entries[key]['format_decision']['options']['tiff_compression'] for _,key,_ in cases] == ['lzw','lzw',None]


@pytest.mark.parametrize('extra',[{'bit_depth':8},{'bit_depth':16},{'images':['/a.jpg']},
    {'document_ids':[]},{'destination_policy':None}])
def test_original_rejects_client_depth_and_legacy_intent(extra):
    command = {'document_ids':['doc'], 'destination_policy':{'mode':'source_folder'}, **extra}
    with pytest.raises(ValueError): F.require_intent(command,preview=True)


def test_start_requires_exact_preview_identity():
    command = {'document_ids':['doc'],'destination_policy':{}}
    with pytest.raises(ValueError): F.require_intent(command,preview=False)
    F.require_intent({**command,'destination_plan_id':'0'*64},preview=False)


def test_nested_schema_validated_even_if_outer_hash_recomputed(tmp_path,native_double):
    cases = [fixture_source(tmp_path,'source','one','png',16)]
    _, _, envelope = freeze_cases(cases)
    plan, settings = destination(tmp_path,cases,envelope)
    settings = deepcopy(settings)
    settings['format_plan']['entries'][cases[0][1]]['client_codec'] = 'jpg'
    payload = plan.payload(); payload['settings_json'] = D.canonical(settings)
    payload['plan_id'] = D.digest({k:v for k,v in payload.items() if k != 'plan_id'})
    with pytest.raises(ValueError,match='invalid_format_decision'):
        D.restore(payload)


def test_actual_receipts_keep_original_intent_separate(tmp_path,native_double):
    cases = [fixture_source(tmp_path,'source','one','png',16)]
    entries, _, envelope = freeze_cases(cases)
    plan, _ = destination(tmp_path,cases,envelope)
    key = cases[0][1]
    result = {'out':R.primary_target(plan.payload(),key),'format':'png','bits':16,'bytes':123}
    R.decorate(result,plan.payload(),key)
    assert result['format'] == 'png' and result['requested_format'] == 'original'
    assert result['outputs'][0]['format'] == 'png'
    assert result['decision_id'] == entries[key]['format_decision']['decision_id']
    assert result['outputs'][0]['fact_id'] == result['fact_id']


def test_partial_clean_retry_reuses_only_same_authenticated_commit(tmp_path,native_double):
    cases = [fixture_source(tmp_path,'source','one','jpeg',8)]
    _, _, envelope = freeze_cases(cases)
    plan, _ = destination(tmp_path,cases,envelope)
    key = cases[0][1]
    from pathlib import Path
    clean = next(e.target for e in plan.entries if e.item_id == key+'::clean')
    Path(clean).parent.mkdir()
    Path(clean).write_bytes(b'fixture encoded bytes; not a real JPEG acceptance result')
    result = {'error':'watermarked variant failed', 'outputs':[{'path':clean,'format':'jpg',
        'bits':8,'variant':'clean','bytes':Path(clean).stat().st_size,'skipped':False,
        'encoded_sha256':sha256(Path(clean).read_bytes()).hexdigest()}]}
    R.decorate(result,plan.payload(),key)
    assert result['outputs'][0]['output_identity']['sha256']
    reused = R.run(plan.payload(),key,R.reuse_output,clean,previous_outputs=result['outputs'])
    assert reused['reused_previous_commit'] and reused['path'] == clean
    primary = R.primary_target(plan.payload(),key)
    assert R.run(plan.payload(),key,R.resolve,primary,previous_outputs=result['outputs']) == (primary,None)
    Path(clean).write_bytes(b'changed')
    with pytest.raises(ValueError,match='替换或改变'):
        R.run(plan.payload(),key,R.reuse_output,clean,previous_outputs=result['outputs'])
    assert Path(clean).read_bytes() == b'changed'  # Never overwritten or renamed.


def test_verification_failed_commit_is_never_reused(tmp_path,native_double):
    cases = [fixture_source(tmp_path,'source','one','png',16)]
    _, _, envelope = freeze_cases(cases)
    plan, _ = destination(tmp_path,cases,envelope)
    key = cases[0][1]
    target = R.primary_target(plan.payload(),key)
    output = {'path':target,'format':'png','bits':16,'bytes':1,'committed':True,
              'verification_failed':True,'error':'readback mismatch'}
    R.decorate({'error':'readback mismatch','outputs':[output]},plan.payload(),key)
    assert R.run(plan.payload(),key,R.reuse_output,target,previous_outputs=[output]) is None


def test_custom_icc_bytes_are_frozen_not_reopened_on_retry(tmp_path,native_double):
    profile = tmp_path/'custom.icc'
    original = b'host-contract-only ICC; real writer validation remains mandatory'
    profile.write_bytes(original)
    cases = [fixture_source(tmp_path,'source','one','png',16)]
    _, _, envelope = freeze_cases(cases,output_profile=str(profile))
    plan, _ = destination(tmp_path,cases,envelope)
    profile.write_bytes(b'replaced after admission')
    key = cases[0][1]
    assert R.run(plan.payload(),key,R.frozen_profile,str(profile)) == original
    assert envelope['output_profile_asset']['sha256'] == sha256(original).hexdigest()


def test_recomputed_hash_does_not_allow_contradictory_source_precision(tmp_path,native_double):
    cases = [fixture_source(tmp_path,'source','one','png',16)]
    _, _, envelope = freeze_cases(cases)
    decision = envelope['entries'][cases[0][1]]
    decision['bits'] = 8
    decision['decision_id'] = D.digest({k:v for k,v in decision.items() if k != 'decision_id'})
    with pytest.raises(ValueError,match='source_inconsistent'):
        F.validate(envelope)
