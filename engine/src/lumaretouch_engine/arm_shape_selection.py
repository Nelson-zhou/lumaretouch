# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual SAM2 candidate pixels, not a renamed manual width generator.

This is assisted prompted selection, NOT an arm semantic model. Every candidate
is exposed for review. Torso/other-person leakage is rejected, never cropped away.
Importing this module never starts inference or installs dependencies.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import numpy as np
from . import arm_shape_state as S, body_pose_evidence as E
from . import prompted_model_manifest as M
from . import prompted_mask_source as P


def encode_mask(mask):
    a=np.asarray(mask)
    if a.ndim!=2 or min(a.shape)<2 or max(a.shape)>2048 or not np.isin(a,(0,1)).all():
        raise ValueError('Actual binary source-inference mask required')
    raw=np.packbits(a.astype(np.uint8).reshape(-1),bitorder='big').tobytes()
    text=base64.b64encode(raw).decode('ascii')
    return {'width':int(a.shape[1]),'height':int(a.shape[0]),'encoding':'packbits-big-base64',
            'chunks':[text[i:i+4096] for i in range(0,len(text),4096)],'sha256':sha256(raw).hexdigest()}


def decode_mask(value):
    if type(value) is not dict or set(value)!={'width','height','encoding','chunks','sha256'} or value['encoding']!='packbits-big-base64' or any(type(value[k]) is not int or not 2<=value[k]<=2048 for k in ('width','height')):
        raise ValueError('Invalid retained actual SAM selection')
    chunks=value['chunks']
    if type(chunks) is not list or not 1<=len(chunks)<=172 or any(type(c) is not str or not 1<=len(c)<=4096 for c in chunks):
        raise ValueError('SAM selection bytes exceed budget')
    try: raw=base64.b64decode(''.join(chunks),validate=True)
    except (ValueError,TypeError) as error: raise ValueError('Invalid SAM mask encoding') from error
    count=value['width']*value['height']
    if len(raw)!=(count+7)//8 or sha256(raw).hexdigest()!=E.digest(value['sha256']):
        raise ValueError('Actual selection pixels changed')
    bits=np.unpackbits(np.frombuffer(raw,np.uint8),bitorder='big')
    if bits[count:].any(): raise ValueError('Noncanonical SAM mask padding')
    return bits[:count].reshape(value['height'],value['width'])


def prompts(record,segment,scope):
    S.region(scope);S.axis(record,segment)
    a,b=(record['points'][i] for i in S.JOINTS[segment])
    # Centres guide selection only. No radius or contour is invented from pose.
    points=[{'x':a['x']+(b['x']-a['x'])*t,'y':a['y']+(b['y']-a['y'])*t,'label':1} for t in (.3,.5,.7)]
    points += [{'x':(r[0]+r[2])/2,'y':(r[1]+r[3])/2,'label':0} for r in scope['exclusions']]
    return P.check_prompts({'points':points,'box':scope['selection_box']})


def _mask_ownership(mask,scope):
    h,w=mask.shape;y,x=np.nonzero(mask)
    if len(x)<16: raise ValueError('SAM produced no reviewable arm selection')
    # Pixel-centre coordinates; no clipping/erasing is applied to a candidate.
    xn=(x+.5)/w;yn=(y+.5)/h;b=scope['selection_box']
    if np.any((xn<=b[0])|(xn>=b[2])|(yn<=b[1])|(yn>=b[3])):
        raise ValueError('SAM selected material outside the reviewed arm ownership window')
    for b in scope['exclusions']:
        if np.any((xn>=b[0])&(xn<=b[2])&(yn>=b[1])&(yn<=b[3])):
            raise ValueError('SAM selection contains reviewed torso/contact/other-person pixels')


def check_selection(value,record,segment,scope):
    keys={'version','binding','runtime_sha256','mask','source','body_ref','points_sha256','segment','score','actual_device','ownership'}
    if type(value) is not dict or set(value)!=keys or type(value['version']) is not int or value['version']!=1 or value['segment']!=segment or value['source']!=record['source'] or value['body_ref']!=record['body_ref'] or value['points_sha256']!=record['points_sha256']:
        raise ValueError('SAM selection belongs to another source/body/analysis/segment')
    binding=P.check_binding(value['binding'])
    expected={'id':M.MODEL_ID,'checkpoint_sha256':M.CHECKPOINT_SHA256,'config_sha256':M.CONFIG_SHA256,'code_revision':M.SOURCE_REVISION,'contract':P.CONTRACT}
    if binding['model']!=expected or binding['prompts']!=prompts(record,segment,scope):
        raise ValueError('SAM model or measured-point/explicit-scope prompts differ')
    E.digest(value['runtime_sha256'])
    if value['actual_device'] not in ('CPU','CUDA','ROCm') or (binding['device']=='cpu')!=(value['actual_device']=='CPU'):
        raise ValueError('SAM actual device receipt differs')
    if type(value['score']) not in (int,float) or not np.isfinite(value['score']) or not 0<=value['score']<=1:
        raise ValueError('Invalid SAM candidate score; it is not an arm confidence')
    mask=decode_mask(value['mask']);h,w=mask.shape
    source=record['source'];ratio=min(1,2048/max(source['width'],source['height']))
    if [w,h]!=[max(1,round(source['width']*ratio)),max(1,round(source['height']*ratio))]:
        raise ValueError('SAM selection is not at the declared producer inference dimensions')
    _mask_ownership(mask,scope)
    check_ownership(value['ownership'],record)
    reject_ownership(mask,value['ownership'])
    return deepcopy(value)


def measured_widths(selection,record,segment):
    """Trace each actual binary cross-section, refusing gaps/multiple objects.

    Half-inference-pixel sampling makes uncertainty explicit. The returned width
    is a model boundary observation, not an anatomical measurement or guarantee.
    """
    mask=decode_mask(selection['mask']);mh,mw=mask.shape
    start,u,length,scale=S.axis(record,segment);w,h=record['source']['width']-1,record['source']['height']-1
    n=np.array([-u[1],u[0]]); step=.5*max(w/max(1,mw-1),h/max(1,mh-1))
    distance=np.arange(0,length*.35+step,step)
    negative=[];positive=[]
    for t in S.STATIONS:
        center=np.array(start)+np.array(u)*length*t
        for sign,output in ((-1,negative),(1,positive)):
            q=center+sign*distance[:,None]*n
            x=np.rint(q[:,0]/w*(mw-1)).astype(int);y=np.rint(q[:,1]/h*(mh-1)).astype(int)
            if np.any(x<0)|np.any(y<0)|np.any(x>=mw)|np.any(y>=mh):
                raise ValueError('SAM cross-section is cropped; no hidden contour completion')
            inside=mask[y,x].astype(bool)
            if not inside[0]: raise ValueError('Observed arm axis is outside the actual SAM selection')
            exits=np.flatnonzero(~inside)
            if not len(exits): raise ValueError('SAM selection has no bounded transverse contour')
            first=int(exits[0])
            if first<2 or np.any(inside[first:]): raise ValueError('SAM contour contains holes, disconnected pieces or ambiguous overlap')
            width=(distance[first-1]+distance[first])*.5
            if width<2 or width>length*.3: raise ValueError('SAM contour is below model resolution or exceeds visible-arm policy')
            output.append(float(width/scale))
    return negative,positive


def propose(path,record,segment,scope,ownership,*,device='cpu',cancelled=lambda:False):
    """Run only as a cancellable owned job. No auto-install, no manual fallback.

    Callers must expose every candidate/refusal and exact source overlay. This
    returns proposals, never a support review or a rendered image.
    """
    from . import prompted_model_install as I
    record=E.check(record);scope=S.region(scope);S.axis(record,segment);check_ownership(ownership,record)
    source={k:record['source'][k] for k in ('sha256','width','height')}
    pixels=P.decode_source(path,source,device='cpu')
    runtime=I.installed_runtime_identity()
    predictor=P.Predictor(device);result=predictor.predict(pixels,prompts(record,segment,scope),cancelled=cancelled)
    if I.installed_runtime_identity()!=runtime: raise ValueError('SAM runtime changed during proposal')
    proposals=[]
    for candidate in range(3):
        selection={'version':1,'binding':{'prompts':prompts(record,segment,scope),'candidate':candidate,
                   'model':result['model'],'input_sha256':result['input_sha256'],'device':device},
                   'runtime_sha256':runtime['runtime_sha256'],'mask':encode_mask(result['masks'][candidate]),
                   'source':record['source'],'body_ref':record['body_ref'],'points_sha256':record['points_sha256'],
                   'segment':segment,'score':result['scores'][candidate],'actual_device':result['device'],'ownership':deepcopy(ownership)}
        try:
            check_selection(selection,record,segment,scope)
            negative,positive=measured_widths(selection,record,segment)
            proposals.append({'selection':selection,'negative':negative,'positive':positive,'refusal':None})
        except ValueError as error:
            proposals.append({'selection':selection,'negative':None,'positive':None,'refusal':str(error)})
    return {'version':1,'source':record['source'],'body_ref':record['body_ref'],
            'points_sha256':record['points_sha256'],'segment':segment,'region':scope,
            'proposals':proposals,'reviewed':False,'runtime_quality_accepted':False}


def support_from_proposal(proposal,candidate,confirmations):
    if type(candidate) is not int or not 0<=candidate<3: raise ValueError('Choose one actual SAM candidate')
    row=proposal['proposals'][candidate]
    if row['refusal'] is not None: raise ValueError(row['refusal'])
    return {'version':1,'segment':proposal['segment'],'strategy':'sam2-prompted-contour',
            'stations':list(S.STATIONS),'negative':deepcopy(row['negative']),'positive':deepcopy(row['positive']),
            'region':deepcopy(proposal['region']),'selection':deepcopy(row['selection']),
            'confirmations':deepcopy(confirmations)}


def verify_input(pixels,selection):
    """Reopening/export verifies the actual canonical inference input, no inference.

    Retained reviewed mask pixels are replayable assets. They are not a claim that
    a new inference ran; runtime/weights need not be installed for their replay.
    """
    _,digest=P.inference_image(pixels)
    if digest!=selection['binding']['input_sha256']:
        raise ValueError('Actual source inference pixels differ from the retained SAM selection')


def ownership_evidence(record,records,people_state=None):
    """Only actual visible observations may refute ownership; no hidden anatomy.

    An incomplete detector census is NEVER a guarantee of no other people. The
    explicit source review remains required even when these conservative gates pass.
    """
    source=record['source'];others=[]
    for other in records:
        other=E.check(other)
        if other['source']!=source or other['body_ref']==record['body_ref']:continue
        points=[p for p in other['points'] if p['visibility']>=.8 and p['presence']>=.8 and 0<p['x']<1 and 0<p['y']<1]
        if len(points)>=2:
            box=[min(p['x'] for p in points),min(p['y'] for p in points),max(p['x'] for p in points),max(p['y'] for p in points)]
            if box[0]<box[2] and box[1]<box[3]:others.append({'body_ref':other['body_ref'],'points_sha256':other['points_sha256'],'box':box})
    torso=[record['points'][i] for i in (11,12,24,23)]
    polygon=[[p['x'],p['y']] for p in torso] if all(p['visibility']>=.8 and p['presence']>=.8 and 0<p['x']<1 and 0<p['y']<1 for p in torso) else None
    faces=[]
    if people_state is not None:
        from .people_state import check as check_people
        people=check_people(people_state)
        faces=[{'face_instance_id':key,'box':deepcopy(face['box'])} for key,face in sorted(people['faces'].items()) if face['asset_sha256']==source['sha256']]
    return {'version':1,'asset_sha256':source['sha256'],'torso_polygon':polygon,
            'other_bodies':sorted(others,key=lambda x:x['body_ref']['body_instance_id']),'faces':faces}


def check_ownership(value,record):
    if type(value) is not dict or set(value)!={'version','asset_sha256','torso_polygon','other_bodies','faces'} or value['version']!=1 or value['asset_sha256']!=record['source']['sha256']:
        raise ValueError('SAM selection lacks source-owned contamination evidence')
    expected=ownership_evidence(record,[])['torso_polygon']
    if value['torso_polygon']!=expected:raise ValueError('Torso rejection polygon is not the actual visible pose observation')
    if type(value['other_bodies']) is not list or len(value['other_bodies'])>8 or type(value['faces']) is not list or len(value['faces'])>64:raise ValueError('SAM ownership observation budget exceeded')
    seen=set()
    for other in value['other_bodies']:
        if type(other) is not dict or set(other)!={'body_ref','points_sha256','box'}:raise ValueError('Invalid observed other-person exclusion')
        ref=E.ref(other['body_ref']);E.digest(other['points_sha256']);S.rectangle(other['box'])
        if ref['asset_sha256']!=value['asset_sha256'] or ref==record['body_ref'] or ref['body_instance_id'] in seen:raise ValueError('Invalid other-body exclusion source/identity')
        seen.add(ref['body_instance_id'])
    for face in value['faces']:
        if type(face) is not dict or set(face)!={'face_instance_id','box'}:raise ValueError('Invalid observed face exclusion')
        E.token(face['face_instance_id']);S.rectangle(face['box'])
    return deepcopy(value)


def reject_ownership(mask,evidence):
    y,x=np.nonzero(mask);h,w=mask.shape;x=(x+.5)/w;y=(y+.5)/h
    for item in evidence['other_bodies']+evidence['faces']:
        b=item['box']
        if np.any((x>=b[0])&(x<=b[2])&(y>=b[1])&(y<=b[3])):
            raise ValueError('Actual SAM candidate includes an observed other body or retained face')
    polygon=evidence['torso_polygon']
    if polygon is not None:
        inside=np.zeros(len(x),bool)
        for i,a in enumerate(polygon):
            b=polygon[(i+1)%len(polygon)]
            if a[1]==b[1]:continue
            crossing=((a[1]>y)!=(b[1]>y)) & (x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
            inside^=crossing
        if inside.any():raise ValueError('Actual SAM candidate contains the observed torso core; no cropping or manual fallback')
