"""Full edited crop review; durable evidence has no display pixels.

The shared renderer applies canonical geometry at full source resolution first.
Only its finished output is reduced/quantized for this explicitly display-only
sRGB PNG. The original/canonical source and exported float pixels stay intact.
"""
from copy import deepcopy
import base64
import hashlib
import io

MAX_TARGETS=16
PREVIEW_EDGE=320
MAX_BASE64=400_000
FIELDS={'version','document_id','revision','source_proof','candidate_sha256',
        'people_sha256','crop','source_size','output_size','preview'}


def _size(value):
    if type(value) is not list or len(value)!=2 or any(type(x) is not int or x<1 for x in value):
        raise ValueError('Crop review requires exact positive source/output dimensions')
    return value


def parameters(state):
    from .scope import OP_CROP,params_of,check_params
    return check_params(OP_CROP,params_of(state,[OP_CROP])[OP_CROP])


def checked(record):
    from .creative_derived_source import check_row_proof
    from .people_state import digest
    from .scope import OP_CROP,check_params
    if type(record) is not dict or set(record)!=FIELDS or type(record['version']) is not int or record['version']!=1:
        raise ValueError('Crop transfer lacks its exact frozen full-target review')
    if type(record['document_id']) is not str or not 1<=len(record['document_id'])<=128:
        raise ValueError('Invalid crop review document identity')
    revision=record['revision']
    if type(revision) is not str or not revision.isascii() or not revision.isdigit() or len(revision)>20 or int(revision)>2**64-1:
        raise ValueError('Invalid crop review document revision')
    check_row_proof(record['source_proof'])
    digest(record['candidate_sha256']);digest(record['people_sha256'])
    if check_params(OP_CROP,record['crop'])!=record['crop']:raise ValueError('Noncanonical crop review parameters')
    _size(record['source_size']);_size(record['output_size'])
    preview=record['preview']
    if type(preview) is not dict or set(preview)!={'mime','width','height','sha256'} or preview['mime']!='image/png':
        raise ValueError('Frozen crop history must retain only compact preview evidence')
    if any(type(preview[k]) is not int or not 1<=preview[k]<=PREVIEW_EDGE for k in ('width','height')):
        raise ValueError('Invalid crop preview display extent')
    digest(preview['sha256'])
    from .ops.geometry import out_size
    if list(out_size(*record['source_size'],record['crop']['rect_normalized'],record['crop']['rotation_degrees']))!=record['output_size']:
        raise ValueError('Crop review output does not match canonical full-source geometry')
    source=record['source_proof']['creative_source']
    if source is not None and [source['width'],source['height']]!=record['source_size']:
        raise ValueError('Crop review belongs to another creative canvas extent')
    return deepcopy(record)


def check_record(record):
    """Frozen batch schema hook; display bytes are never accepted here."""
    return checked(record)


def verify(engine,row,candidate_state,document_id,revision,record):
    from .full_candidate_render import identity
    record=checked(record)
    actual,_,_=identity(engine,row,candidate_state,document_id,revision)
    if any(record[key]!=value for key,value in actual.items()) or record['crop']!=parameters(candidate_state):
        raise ValueError('Crop target source, edits, analysis or document changed after review')
    if record['source_proof']['creative_source'] is None:
        if [row.get('src_w'),row.get('src_h')]!=record['source_size']:
            raise ValueError('Crop target original extent changed after review')


def prepare(engine,row,candidate_state,document_id,revision):
    from .full_candidate_render import render
    from PIL import Image
    import numpy as np
    crop=parameters(candidate_state)
    rgb,proof=render(engine,row,candidate_state,document_id,revision)
    # Float exporter is encoded-sRGB working RGB. Clipping here is presentation
    # only, just like normal SDR display, not a conversion of the source asset.
    display=Image.fromarray(np.clip(np.rint(rgb*255.),0,255).astype(np.uint8),'RGB')
    display.thumbnail((PREVIEW_EDGE,PREVIEW_EDGE),Image.Resampling.LANCZOS)
    # High-entropy 320px PNGs may exceed the transport cap. Reduce only this
    # display image, never rerender with reduced source pixels or crop rounding.
    while True:
        stream=io.BytesIO();display.save(stream,format='PNG')
        raw=stream.getvalue();encoded=base64.b64encode(raw).decode('ascii')
        if len(encoded)<=MAX_BASE64:break
        edge=max(display.size)-16
        if edge<1:
            display.close();raise ValueError('Crop preview exceeds bounded display transport')
        scale=min(edge/rgb.shape[1],edge/rgb.shape[0],1.)
        smaller=display.resize((max(1,round(rgb.shape[1]*scale)),max(1,round(rgb.shape[0]*scale))),Image.Resampling.LANCZOS)
        display.close();display=smaller
    width,height=display.size;display.close()
    private=checked({'version':1,**proof,'crop':crop,'preview':{
        'mime':'image/png','width':width,'height':height,'sha256':hashlib.sha256(raw).hexdigest()}})
    verify(engine,row,candidate_state,document_id,revision,private)
    public=deepcopy(private);public['preview']['base64']=encoded
    return private,public
