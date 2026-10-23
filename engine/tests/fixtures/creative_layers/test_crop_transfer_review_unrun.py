"""AUTHORED / UNRUN. Schema fixtures are not real render/quality acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import crop_transfer_review as C
from lumaretouch_engine import full_candidate_render as F
from lumaretouch_engine import virtual_copy_people as V,people_state as S


def record():
    return {'version':1,'document_id':'target','revision':'3',
        'source_proof':{'asset_sha256':'a'*64,'original_sha256':'a'*64,'creative_source':None},
        'candidate_sha256':'b'*64,'people_sha256':'c'*64,
        'crop':{'rect_normalized':[0.,0.,1.,1.],'rotation_degrees':0.},
        'source_size':[640,480],'output_size':[640,480],
        'preview':{'mime':'image/png','width':320,'height':240,'sha256':'d'*64}}


def test_private_record_has_no_pixels_and_roundtrips():
    value=record();assert C.check_record(value)==value
    value['preview']['base64']='iVBOR'
    with pytest.raises(ValueError):C.check_record(value)


@pytest.mark.parametrize('field,value',[
    ('output_size',[639,480]),('source_size',[0,480]),('candidate_sha256','bad'),
    ('people_sha256','bad'),('revision','18446744073709551616'),('revision','-1'),
    ('version',True),('document_id',''),
])
def test_invalid_compact_proofs_refuse(field,value):
    frozen=record();frozen[field]=value
    with pytest.raises(ValueError):C.check_record(frozen)


def test_creative_dimensions_are_owned_not_original():
    frozen=record();frozen['source_proof']['creative_source']={'sha256':'a'*64,'width':800,'height':600}
    with pytest.raises(ValueError):C.check_record(frozen)


@pytest.mark.parametrize('field',['source_proof','candidate_sha256','people_sha256','revision','document_id'])
def test_verify_rejects_changed_identity_without_render(monkeypatch,field):
    frozen=record();actual={key:deepcopy(frozen[key]) for key in ('source_proof','candidate_sha256','people_sha256','revision','document_id')}
    if field=='source_proof':actual[field]['original_sha256']='e'*64
    else:actual[field]='e'*64
    monkeypatch.setattr(F,'identity',lambda *a,**kw:(actual,{},{}))
    monkeypatch.setattr(C,'parameters',lambda state:frozen['crop'])
    with pytest.raises(ValueError):C.verify(None,{'src_w':640,'src_h':480},{},'target','3',frozen)


def test_changed_crop_and_original_extent_refuse(monkeypatch):
    frozen=record();actual={key:deepcopy(frozen[key]) for key in ('source_proof','candidate_sha256','people_sha256','revision','document_id')}
    monkeypatch.setattr(F,'identity',lambda *a,**kw:(actual,{},{}))
    monkeypatch.setattr(C,'parameters',lambda state:{**frozen['crop'],'rotation_degrees':90.})
    with pytest.raises(ValueError):C.verify(None,{'src_w':640,'src_h':480},{},'target','3',frozen)
    monkeypatch.setattr(C,'parameters',lambda state:frozen['crop'])
    with pytest.raises(ValueError):C.verify(None,{'src_w':480,'src_h':640},{},'target','3',frozen)


def test_fresh_unclassified_import_is_not_mutated_or_inferred():
    row={'document_id':'target','_people_new_import':True};before=deepcopy(row);engine=SimpleNamespace()
    with pytest.raises(ValueError,match='establish'):F.people_context(engine,row)
    assert row==before and engine.__dict__=={}


def test_established_empty_owner_stays_empty_without_installation():
    row={'document_id':'target'};engine=SimpleNamespace()
    context=F.people_context(engine,row)
    assert context['people_graph']==S.empty() and engine.__dict__=={} and row=={'document_id':'target'}


def test_private_context_read_does_not_activate_owner():
    value={'version':1,'people_graph':S.empty(),**{key:{} for key in V.FIELDS}}
    row={'document_id':'target',V.KEY:deepcopy(value)};engine=SimpleNamespace()
    assert F.people_context(engine,row)==value
    assert V.RUNTIME not in row and engine.__dict__=={}


def test_renderer_source_contract_is_full_geometry_before_display():
    # Source inspection only; executing this fixture does not claim pixel parity.
    from pathlib import Path
    root=Path(__file__).resolve().parents[4]/'engine/src/lumaretouch_engine'
    renderer=(root/'full_candidate_render.py').read_text();preview=(root/'crop_transfer_review.py').read_text()
    assert 'load_full(' in renderer and 'require_photo_return(base)' in renderer
    assert 'export_float(pixels,spec,geometry=geometry' in renderer
    assert 'M.verify_snapshot(snap,path,(h,w))' in renderer
    assert 'if skipped:raise ValueError' in renderer
    assert preview.index('rgb,proof=render(')<preview.index('display.thumbnail(')
