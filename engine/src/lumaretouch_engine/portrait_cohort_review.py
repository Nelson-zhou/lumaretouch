# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-first complete portrait-cohort review, never a guessed named recipe.

Capsule v1 remains canonical scalar intent. Full thirty-key content keeps this
review mandatory through later generic updates/unlink, including zero values.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
from . import face_style_recipes as RECIPES
from .portrait_review_render import image, preview_size, snapshot_key

MAX_TARGETS=16
FIELDS={'version','document_id','revision','source_proof','before_state_sha256','candidate_state_sha256',
        'before_people_sha256','candidate_people_sha256','source_size','before_output_size','after_output_size',
        'before','after','cohort_sha256'}


def content_required(intent):
    owned={(op,path) for op,paths in RECIPES.catalogue()['owned_parameters'].items() for path in paths}
    return type(intent) is list and owned<={(leaf.get('op'),leaf.get('path')) for leaf in intent if type(leaf) is dict}


def required(endpoints,selected,review):
    if content_required(review['intent']):return True
    association=selected['association_id']
    return any(content_required(person.get('cross_owner',{}).get('intent'))
               for item in endpoints for key in ('before','candidate') for person in item[key]['persons'].values()
               if person.get('cross_owner',{}).get('association_id')==association)


def digest(selected,review):
    from .people_cross_owner import descriptor
    from .face_style_batch_review import recipe
    if (type(review) is not dict or set(review)!={'version','operation','association_id','generation','members','intent'}
            or type(review['version']) is not int or review['version']!=1
            or review['operation']!=selected['operation'] or review['association_id']!=selected['association_id']):
        raise ValueError('Exact immutable association review required')
    capsule=descriptor(review['association_id'],selected['source']['document']['document_id'],review['members'],review['intent'])
    if capsule['generation']!=review['generation']:raise ValueError('Cohort scalar generation differs from its reviewed content')
    named=recipe(selected['face_style']) if 'face_style' in selected else None
    value={'review':review,'face_style':named}
    return sha256(b'lumaretouch-portrait-cohort-v1\0'+json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:raise ValueError('Exact cohort SHA256 required')


def checked(value):
    from .creative_derived_source import check_row_proof
    if type(value) is not dict or set(value)!=FIELDS or type(value['version']) is not int or value['version']!=1:
        raise ValueError('Missing complete portrait-cohort visual')
    if type(value['document_id']) is not str or not 1<=len(value['document_id'])<=128:raise ValueError('Invalid cohort document')
    if (type(value['revision']) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})',value['revision']) is None
            or int(value['revision'])>2**64-1):raise ValueError('Invalid cohort revision')
    proof=check_row_proof(value['source_proof'])
    for key in ('before_state_sha256','candidate_state_sha256','before_people_sha256','candidate_people_sha256','cohort_sha256'):_hash(value[key])
    for key in ('source_size','before_output_size','after_output_size'):preview_size(value[key])
    if proof['creative_source'] is not None and value['source_size']!=[proof['creative_source']['width'],proof['creative_source']['height']]:raise ValueError('Derived cohort canvas mismatch')
    for side in ('before','after'):
        item=value[side]
        if (type(item) is not dict or set(item)!={'mime','width','height','sha256'} or item['mime']!='image/png'
                or type(item['width']) is not int or type(item['height']) is not int
                or (item['width'],item['height'])!=preview_size(value[side+'_output_size'])):raise ValueError('Exact cohort display dimensions required')
        _hash(item['sha256'])
    return deepcopy(value)


def acknowledgments(raw,records):
    records=[checked(item) for item in records]
    expected=[{'document_id':r['document_id'],'revision':r['revision'],'before_sha256':r['before']['sha256'],
               'after_sha256':r['after']['sha256'],'cohort_sha256':r['cohort_sha256']} for r in records]
    if (type(raw) is not list or len(raw)!=len(expected) or not 2<=len(raw)<=MAX_TARGETS
            or len({r['document_id'] for r in records})!=len(records)
            or len({r['cohort_sha256'] for r in records})!=1
            or any(type(a) is not dict or set(a)!=set(b) or a!=b for a,b in zip(raw,expected))):
        raise ValueError('Read and acknowledge source first and every exact portrait-cohort member')
    return deepcopy(expected)


def _identities(engine,item,cohort_digest):
    from .full_candidate_render import identity
    from .ops.geometry import out_size
    row=item['row'];doc=item['proof']['document'];document=doc['document_id'];revision=str(doc['revision'])
    a,_,_=identity(engine,row,row['state'],document,revision,people_graph=item['before'])
    b,_,_=identity(engine,row,row['state'],document,revision,people_graph=item['candidate'])
    if any(a[k]!=b[k] for k in ('document_id','revision','source_proof','candidate_sha256')):raise ValueError('Cohort changed source or nonportrait state')
    if a['source_proof']!=item['proof']['source_proof']:raise ValueError('Cohort source differs from reviewed endpoint')
    derived=a['source_proof']['creative_source']
    size=[derived['width'],derived['height']] if derived is not None else [row['src_w'],row['src_h']]
    output=list(out_size(*size,row['state']['_crop_rect'],row['state']['_crop_rotation']))
    return {'version':1,'document_id':document,'revision':revision,'source_proof':a['source_proof'],
            'before_state_sha256':a['candidate_sha256'],'candidate_state_sha256':b['candidate_sha256'],
            'before_people_sha256':a['people_sha256'],'candidate_people_sha256':b['people_sha256'],
            'source_size':size,'before_output_size':output,'after_output_size':output,'cohort_sha256':cohort_digest}


def snapshots(engine,item):
    return {key:snapshot_key(engine,item['row'],item['row']['state'],item[graph])
            for key,graph in (('before','before'),('after','candidate'))}


def verify(engine,item,frozen,cohort_digest):
    record=checked(frozen.get('portrait_visual'))
    if snapshots(engine,item)!=frozen.get('portrait_snapshots'):raise ValueError('Complete cohort source, repair, context or graph changed')
    if any(record[k]!=v for k,v in _identities(engine,item,cohort_digest).items()):raise ValueError('Cohort image no longer describes this exact member')
    return record


def prepare(engine,endpoints,selected,review,*,existing_displays=None):
    if not 2<=len(endpoints)<=MAX_TARGETS:raise ValueError('Review every source and target cohort member')
    cohort_digest=digest(selected,review);displays={}
    for item in endpoints:
        doc=item['proof']['document'];document=doc['document_id'];revision=str(doc['revision'])
        keys=snapshots(engine,item);base=_identities(engine,item,cohort_digest)
        if existing_displays is not None:
            # Reuse the same actual full-source pair already rendered for an
            # independently mandatory collarbone review, never a proxy/overlay.
            display=existing_displays[document];prior=item['collarbone_visual']
            if any(prior[k]!=v for k,v in base.items() if k!='cohort_sha256'):
                raise ValueError('Dual review does not share the identical complete source and graph pair')
            a,b=prior['before'],prior['after']
        else:
            a,left,pa=image(engine,item['row'],item['row']['state'],item['before'],document,revision)
            b,right,pb=image(engine,item['row'],item['row']['state'],item['candidate'],document,revision)
            for side,proof in (('before',pa),('after',pb)):
                if (proof['source_proof']!=base['source_proof'] or proof['source_size']!=base['source_size']
                        or proof['output_size']!=base[side+'_output_size']
                        or proof['candidate_sha256']!=base['before_state_sha256' if side=='before' else 'candidate_state_sha256']
                        or proof['people_sha256']!=base['before_people_sha256' if side=='before' else 'candidate_people_sha256']):
                    raise ValueError('Cohort render changed during preparation')
            display={'revision':revision,'before':left,'after':right}
        item['portrait_visual']=checked({**base,'before':a,'after':b});item['portrait_snapshots']=keys
        displays[document]=display
    for item in endpoints:verify(engine,item,item,cohort_digest)
    return displays


def evidence(item,*,private=False):
    fields=('portrait_visual','portrait_snapshots') if private else ('portrait_visual',)
    return {key:deepcopy(item[key]) for key in fields if key in item}
