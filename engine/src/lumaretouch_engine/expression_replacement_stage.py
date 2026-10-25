# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure owned donor/target staging, full-image comparison and real fusion display."""
from copy import deepcopy
from dataclasses import dataclass
import base64
import hashlib
import io
import json
import math
import uuid
import numpy as np

OP = 'lnx.expression_replacement.v1'
CONFIRMATIONS = {'same_person','same_session','real_measured_landmarks',
                 'reviewed_pose','both_unoccluded','fusion_reviewed'}
MAX_PACKET_BYTES = 256_000


def digest_array(array):
    return hashlib.sha256(np.ascontiguousarray(array,dtype='<f4').tobytes()).hexdigest()


def source(capture):
    # Even an imported donor is represented by its new colour-managed canonical
    # asset identity. Its actual original-file digest is separate provenance.
    return {'asset_sha256':capture.source['sha256'], 'original_sha256':capture.original_sha256,
            'source_kind':'derived', 'width':capture.source['width'], 'height':capture.source['height'],
            'orientation':'exif_normalized_once', 'retained_asset_id':capture.asset['id']}


def image(rgb, owner):
    from PIL import Image
    if type(rgb) is not np.ndarray or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Expression review display must be a genuine RGB8 projection')
    im=Image.fromarray(rgb,'RGB');im.thumbnail((1600,1600))
    stream=io.BytesIO();im.save(stream,format='PNG');raw=stream.getvalue()
    if len(raw)>12_000_000:raise ValueError('Expression review image exceeds transport budget')
    return {'mime':'image/png','width':im.width,'height':im.height,
            'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode('ascii'),
            'source_sha256':owner['asset_sha256'],'source_width':owner['width'],'source_height':owner['height'],
            'mapping':'normalized_full_frame','orientation':'exif_normalized_once'}


def display_shape(owner):
    scale=min(1.,1600/max(owner['width'],owner['height']))
    return max(2,round(owner['width']*scale)),max(2,round(owner['height']*scale))


def asset_image(asset, owner, *, max_bytes, cancelled=lambda:False):
    """One exact source-derived review grid, independent of inference alignment."""
    from PIL import Image
    from .creative_layer_native import display_rgba
    width,height=display_shape(owner)
    if asset['width']*asset['height']*4+width*height*96+16_000_000>max_bytes:
        raise MemoryError('Expression full-source display exceeds remaining memory budget')
    pixels=np.frombuffer(asset['content'],dtype='<f4').reshape(asset['height'],asset['width'],4)
    small=np.empty((height,width,4),dtype=np.float32)
    for channel in range(4):
        if cancelled():raise InterruptedError('Expression review display cancelled')
        plane=Image.fromarray(pixels[:,:,channel],mode='F')
        small[:,:,channel]=np.asarray(plane.resize((width,height),Image.Resampling.BOX),dtype=np.float32)
        plane.close()
    return image(display_rgba(small,matte=(0.,0.,0.),cancelled=cancelled),owner)


def face(capture, ref, *, cancelled=lambda:False):
    from .expression_replacement_geometry import face_crop
    from .people_binding import landmark_digest
    crop, _, _, allowed, protected = face_crop(capture,ref,cancelled=cancelled)
    analysis=capture.analyses[ref['face_instance_id']]
    return {'face_ref':deepcopy(ref),'enabled':True,'analysis_status':'verified','manual':False,
            'landmarks_count':478,'landmarks_sha256':landmark_digest(analysis['landmarks']),
            'crop':crop,'eligibility_sha256':digest_array(allowed),'protection_sha256':digest_array(protected)}


def photograph(capture, label, *, max_bytes, cancelled=lambda:False):
    from .people_state import face_ref
    faces=[]
    refused=[]
    for row in capture.graph['faces'].values():
        try:
            if cancelled():raise InterruptedError('Expression face catalogue cancelled')
            if max_bytes<64_000_000:raise MemoryError('Expression catalogue crop exceeds remaining memory')
            faces.append(face(capture,face_ref(row),cancelled=cancelled))
        except ValueError as error:refused.append(str(error))
    if not faces:raise ValueError('没有满足原尺寸融合条件的人脸：'+'；'.join(refused[:3]))
    # The complete graph stays private and protects every detected face, including
    # unsupported candidates omitted from the selectable list.
    owner=source(capture)
    return {'source':owner,'label':str(label)[:256] or '照片','faces':faces,'image':asset_image(capture.asset,owner,max_bytes=max_bytes,cancelled=cancelled)}


def packet(value):
    if type(value) is not dict or set(value)!={'command','command_json','command_sha256'}:
        raise ValueError('Expression packet needs exact structured and byte-level command identity')
    raw=value['command_json']
    if type(raw) is not str or len(raw.encode('utf-8'))>MAX_PACKET_BYTES:
        raise ValueError('Expression command bytes exceed budget')
    def unique(items):
        out={}
        for key,item in items:
            if key in out:raise ValueError('Duplicate expression JSON field')
            out[key]=item
        return out
    def nonfinite(_):raise ValueError('Nonfinite expression JSON number')
    def finite_float(value):
        number=float(value)
        if not math.isfinite(number):raise ValueError('Nonfinite expression JSON number')
        return number
    parsed=json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite,parse_float=finite_float)
    def same(a,b):
        if type(a) is not type(b):return False
        if isinstance(a,dict):return set(a)==set(b) and all(same(a[k],b[k]) for k in a)
        if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
        return a==b
    if not same(parsed,value['command']) or hashlib.sha256(raw.encode('utf-8')).hexdigest()!=value['command_sha256']:
        raise ValueError('Expression command content/hash mismatch')
    if type(parsed) is not dict or type(parsed.get('version')) is not int or parsed.get('version')!=1 or parsed.get('operation_id')!=OP:
        raise ValueError('Unsupported expression command version')
    return deepcopy(parsed)


@dataclass(frozen=True)
class Candidate:
    preview: dict
    document: dict
    rendered_asset: str
    patch_asset: str
    effective_fusion_asset: str
    numerical_receipt: tuple
    no_change: bool
    assets: dict


def prepare(command, target, donor, *, max_bytes, cancelled=lambda:False):
    from .expression_replacement_geometry import face_crop, fusion_mask
    from .expression_replacement_native import blend
    from .creative_document_assets import make_asset, AssetStore
    assets=AssetStore()
    from .creative_document_render import CreativeRenderer
    from . import creative_document_state as S
    required={'version','operation_id','action','request_id','binding','target','donor','fusion','settings','confirmations'}
    if set(command)!=required or command['action']!='preview':raise ValueError('Malformed expression preview command')
    confirmations=command['confirmations']
    if type(confirmations) is not dict or set(confirmations)!=CONFIRMATIONS or any(v is not True for v in confirmations.values()):
        raise ValueError('Explicit same-person/session/visible-source review is required')
    for name,capture in (('target',target),('donor',donor)):
        owner=command[name]
        if type(owner) is not dict or set(owner)!={'source','face'} or owner['source']!=source(capture):
            raise ValueError('Expression source differs from immutable capture')
        if owner['face']!=face(capture,owner['face']['face_ref'],cancelled=cancelled):
            raise ValueError('Expression face/crop/support differs from actual measured evidence')
    if target.asset['id']==donor.asset['id'] or target.original_sha256==donor.original_sha256:
        raise ValueError('Choose an independently captured donor photograph, not the same source')
    settings=command['settings']
    if type(settings) is not dict or set(settings)!={'density','pyramid_levels','colour_match_strength'} or settings['colour_match_strength']!=0:
        raise ValueError('This expression workflow does not invent colour-match skin references')
    tc,t,tl,ta,tp=face_crop(target,command['target']['face']['face_ref'],cancelled=cancelled)
    _,d,dl,da,dp=face_crop(donor,command['donor']['face']['face_ref'],cancelled=cancelled)
    fusion=fusion_mask(command['fusion'],tc,target.source,ta,cancelled=cancelled)
    if not np.any(fusion>0):raise ValueError('Paint a nonempty actual target fusion region')
    from .expression_replacement_source import resident_bytes
    resident=resident_bytes(target,donor,t,d,tl,dl,ta,da,tp,dp,fusion)
    result,effective,receipt=blend(t,d,tl,dl,ta,da,tp,dp,fusion,
        density=settings['density'],levels=settings['pyramid_levels'],reviews=127,
        max_bytes=max_bytes-resident,cancelled=cancelled)
    if cancelled():raise InterruptedError('Expression candidate cancelled before publication')
    patch=make_asset('rgba',tc['width'],tc['height'],result.astype('<f4',copy=False).tobytes())
    mask=make_asset('mask',tc['width'],tc['height'],effective.astype('<f4',copy=False).tobytes())
    for asset in (target.asset,patch,mask):assets.intern(asset)
    doc=S.create(command['binding']['document_id'],target.asset['id'],assets)
    doc=S.apply(doc,{'action':'add_image','asset_id':patch['id'],'name':'同场次表情 · 人工确认供体'},assets)
    layer=doc['selected_id']
    transform={**S.TRANSFORM,'x':float(tc['left']),'y':float(tc['top'])}
    doc=S.apply(doc,{'action':'transform','layer_id':layer,'transform':transform},assets)
    retained=assets.records(S.references(doc)|{mask['id']})
    remaining=max_bytes-resident_bytes(target,donor,t,d,tl,dl,ta,da,tp,dp,fusion,result,effective,receipt,retained)
    rendered=CreativeRenderer(doc,assets,max_bytes=remaining,cancelled=cancelled).render_asset()
    assets.intern(rendered)
    owner=source(target)
    remaining=max_bytes-resident_bytes(target,donor,t,d,tl,dl,ta,da,tp,dp,fusion,result,effective,receipt,retained,rendered)
    before=asset_image(target.asset,owner,max_bytes=remaining,cancelled=cancelled)
    after=asset_image(rendered,owner,max_bytes=remaining-24_000_000,cancelled=cancelled)
    # Diagnostic fusion display is generated from the native coverage, not by
    # painting a second approximate mask on the preview or altering result alpha.
    dw,dh=display_shape(owner)
    if dw*dh*96+64_000_000>remaining:
        raise MemoryError('Expression fusion review exceeds remaining source budget')
    # Sample the small review grid directly. Do not allocate a full-image mask
    # solely for display; the immutable native crop remains mask authority.
    sx=(np.arange(dw,dtype=np.float64)+.5)*owner['width']/dw-.5-tc['left']
    sy=(np.arange(dh,dtype=np.float64)+.5)*owner['height']/dh-.5-tc['top']
    x0=np.floor(sx).astype(int);y0=np.floor(sy).astype(int)
    fx=sx-x0;fy=sy-y0
    shown=np.zeros((dh,dw),dtype=np.float64)
    for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
        if cancelled():raise InterruptedError('Expression fusion display cancelled')
        ix=x0+dx;iy=y0+dy
        valid=(iy[:,None]>=0)&(iy[:,None]<tc['height'])&(ix[None,:]>=0)&(ix[None,:]<tc['width'])
        sample=effective[np.clip(iy,0,tc['height']-1)[:,None],np.clip(ix,0,tc['width']-1)[None,:]]
        weight=(fy if dy else 1-fy)[:,None]*(fx if dx else 1-fx)[None,:]
        shown+=np.where(valid,sample*weight,0)
    fusion_rgb=np.repeat(np.rint(np.clip(shown,0,1)*255).astype(np.uint8)[:,:,None],3,axis=2)
    fusion_image=image(fusion_rgb,owner)
    if cancelled():raise InterruptedError('Expression candidate changed during full-image review')
    preview={'preview_token':uuid.uuid4().hex,'candidate_sha256':rendered['id'][7:],
             'fusion_mask_sha256':mask['id'][7:],'output_width':target.source['width'],
             'output_height':target.source['height'],'before':before,'after':after,'fusion_image':fusion_image}
    return Candidate(preview,doc,rendered['id'],patch['id'],mask['id'],
                     tuple(float(v) for v in receipt),bool(np.array_equal(result,t)),
                     assets.records(S.references(doc)|{rendered['id'],mask['id']}))
