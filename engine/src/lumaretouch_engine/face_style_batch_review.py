# SPDX-License-Identifier: GPL-3.0-or-later
"""Named local compositions, target-owned full graph image evidence. UNRUN."""
from copy import deepcopy
from hashlib import sha256
import re
import struct
from . import face_style_recipes as R
from .portrait_review_render import image, preview_size

MAX_TARGETS=16
FIELDS={'version','document_id','revision','source_proof','before_state_sha256','candidate_state_sha256',
        'before_people_sha256','candidate_people_sha256','source_size','before_output_size','after_output_size',
        'before','after','recipe_sha256'}


def recipe(value):
    if type(value) is not dict or set(value)!={'version','style','amount'} or type(value['version']) is not int or value['version']!=1:
        raise ValueError('Named face style needs its exact version, style and shared amount')
    R.patches(value['style'],value['amount'])
    return deepcopy(value)


def recipe_digest(value):
    value=recipe(value)
    return sha256(b'lumaretouch.face-style.v1\0'+value['style'].encode('ascii')+b'\0'
                  +struct.pack('>d',float(value['amount']) if value['amount'] else 0.0)).hexdigest()


def parameters(value):
    value=recipe(value)
    return sorted(({key:p[key] for key in ('operation_id','parameter_path','value')}
                   for p in R.patches(value['style'],value['amount'])),key=lambda p:(p['operation_id'],p['parameter_path']))


def selection(value):
    result={}
    for item in parameters(value):result.setdefault(item['operation_id'],[]).append(item['parameter_path'])
    return result


def check_selection(value,selected):
    expected=selection(value)
    if (type(selected) is not dict or set(selected)!=set(expected)
            or any(type(paths) is not list or len(paths)!=len(set(paths)) or sorted(paths)!=expected[op] for op,paths in selected.items())):
        raise ValueError('Named face-style batch replaces exactly its thirty owned leaves; mixed selections are not allowed')


def required(plan):
    value=plan.params().get('_people_transfer')
    return type(value) is dict and type(value.get('options')) is dict and 'face_style' in value['options']


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:raise ValueError('Exact face-style SHA256 required')


def checked(value):
    from .creative_derived_source import check_row_proof
    if type(value) is not dict or set(value)!=FIELDS or type(value['version']) is not int or value['version']!=1:
        raise ValueError('Missing complete face-style target visual')
    if type(value['document_id']) is not str or not 1<=len(value['document_id'])<=128:raise ValueError('Invalid target document')
    if (type(value['revision']) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})',value['revision']) is None
            or int(value['revision'])>2**64-1):raise ValueError('Invalid target revision')
    proof=check_row_proof(value['source_proof'])
    for key in ('before_state_sha256','candidate_state_sha256','before_people_sha256','candidate_people_sha256','recipe_sha256'):_hash(value[key])
    for key in ('source_size','before_output_size','after_output_size'):preview_size(value[key])
    if proof['creative_source'] is not None and value['source_size']!=[proof['creative_source']['width'],proof['creative_source']['height']]:raise ValueError('Derived canvas mismatch')
    for side in ('before','after'):
        item=value[side]
        if (type(item) is not dict or set(item)!={'mime','width','height','sha256'} or item['mime']!='image/png'
                or type(item['width']) is not int or type(item['height']) is not int
                or (item['width'],item['height'])!=preview_size(value[side+'_output_size'])):raise ValueError('Exact target display dimensions required')
        _hash(item['sha256'])
    return deepcopy(value)


def acknowledgments(raw,records):
    records=[checked(item) for item in records]
    expected=[{'document_id':r['document_id'],'revision':r['revision'],'before_sha256':r['before']['sha256'],
               'after_sha256':r['after']['sha256'],'recipe_sha256':r['recipe_sha256']} for r in records]
    if (type(raw) is not list or len(raw)!=len(expected) or len(raw)>MAX_TARGETS
            or len({r['document_id'] for r in records})!=len(records)
            or any(type(a) is not dict or set(a)!=set(b) or a!=b for a,b in zip(raw,expected))):
        raise ValueError('Read and acknowledge every exact target face-style image pair')
    return deepcopy(expected)


def _identity(engine,row,before,candidate,document,revision,value):
    from .full_candidate_render import identity
    from .ops.geometry import out_size
    a,_,_=identity(engine,row,row['state'],document,str(revision),people_graph=before)
    b,_,_=identity(engine,row,row['state'],document,str(revision),people_graph=candidate)
    if any(a[k]!=b[k] for k in ('document_id','revision','source_proof','candidate_sha256')):raise ValueError('Face-style review changed source or nonportrait state')
    derived=a['source_proof']['creative_source']
    size=[derived['width'],derived['height']] if derived is not None else [row['src_w'],row['src_h']]
    output=list(out_size(*size,row['state']['_crop_rect'],row['state']['_crop_rotation']))
    return {'version':1,'document_id':document,'revision':str(revision),'source_proof':a['source_proof'],
            'before_state_sha256':a['candidate_sha256'],'candidate_state_sha256':b['candidate_sha256'],
            'before_people_sha256':a['people_sha256'],'candidate_people_sha256':b['people_sha256'],
            'source_size':size,'before_output_size':output,'after_output_size':output,'recipe_sha256':recipe_digest(value)}


def verify(engine,row,before,candidate,document,revision,value,record):
    record=checked(record);actual=_identity(engine,row,before,candidate,document,revision,value)
    if any(record[k]!=v for k,v in actual.items()):raise ValueError('Target full source, support, graph or recipe changed; review again')
    return record


def prepare(engine,row,before,candidate,document,revision,value):
    frozen=_identity(engine,row,before,candidate,document,revision,value)
    a,left,pa=image(engine,row,row['state'],before,document,revision)
    b,right,pb=image(engine,row,row['state'],candidate,document,revision)
    for side,proof in (('before',pa),('after',pb)):
        if (proof['source_proof']!=frozen['source_proof'] or proof['source_size']!=frozen['source_size']
                or proof['output_size']!=frozen[side+'_output_size']
                or proof['candidate_sha256']!=frozen['before_state_sha256' if side=='before' else 'candidate_state_sha256']
                or proof['people_sha256']!=frozen['before_people_sha256' if side=='before' else 'candidate_people_sha256']):
            raise ValueError('Rendered target changed while preparing review')
    record=checked({**frozen,'before':a,'after':b})
    verify(engine,row,before,candidate,document,revision,value,record)
    return record,{'revision':str(revision),'before':left,'after':right}
