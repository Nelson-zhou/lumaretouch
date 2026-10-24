# SPDX-License-Identifier: GPL-3.0-or-later
"""Separate immutable display namespace on the existing frozen batch store."""
import json
import re
from .collarbone_visual_store import _Images, REQUEST_FIELDS
from .face_style_batch_review import checked, required


def _records(plan):
    if not required(plan):raise ValueError('Token is not a named face-style plan')
    result={}
    for target in plan.targets:
        if target.blocked:continue
        record=checked(json.loads(target.people_json)['face_style_visual'])
        if (record['document_id']!=target.document_id or record['revision']!=str(target.revision)
                or target.document_id in result):raise ValueError('Face-style target image identity changed')
        result[target.document_id]=record
    return result


def prune(store):
    cache=getattr(store,'_face_style_batch_images',None)
    if cache is not None:cache.prune(store.pending)


def attach(store,plan,displays):
    store._prune(store.clock());prune(store)
    if store.pending.get(plan.token) is not plan:raise ValueError('Actual live face-style plan required')
    cache=getattr(store,'_face_style_batch_images',None)
    if cache is None:
        cache=_Images(records=_records);store._face_style_batch_images=cache
    cache.attach(plan,displays)


def verify_available(store,plan):
    store._prune(store.clock());prune(store)
    if store.pending.get(plan.token) is not plan:raise ValueError('Face-style plan expired or consumed')
    cache=getattr(store,'_face_style_batch_images',None)
    if cache is None:raise ValueError('Face-style images unavailable')
    for doc,record in _records(plan).items():
        for side in ('before','after'):cache.read(plan,doc,record['revision'],side,record[side]['sha256'])


def retrieve(controller,request):
    if (type(request) is not dict or set(request)!=REQUEST_FIELDS or request.get('cmd')!='batch'
            or request.get('action')!='face_style_visual' or request.get('side') not in ('before','after')
            or any(type(request.get(k)) is not str or not 1<=len(request[k])<=128 for k in ('request_id','document_id'))
            or type(request.get('revision')) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})',request['revision']) is None
            or int(request['revision'])>2**64-1 or type(request.get('sha256')) is not str
            or re.fullmatch('[a-f0-9]{64}',request['sha256']) is None):raise ValueError('Exact face-style image coordinates required')
    try:plan=controller.store.get(request['preflight_token'],controller.versions.workspace)
    finally:prune(controller.store)
    cache=getattr(controller.store,'_face_style_batch_images',None)
    if cache is None:raise ValueError('Face-style images no longer retained')
    pixels=cache.read(plan,request['document_id'],request['revision'],request['side'],request['sha256'])
    return {'event':'batch_result','action':'face_style_visual','success':True,
            **{k:request[k] for k in ('request_id','preflight_token','document_id','revision','side','sha256')},
            'compact':{k:v for k,v in pixels.items() if k!='base64'},'image':pixels}
