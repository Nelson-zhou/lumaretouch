# SPDX-License-Identifier: GPL-3.0-or-later
"""Family-qualified reads over bounded shared cohort image bytes."""
import re
from .collarbone_visual_store import REQUEST_FIELDS


def _records(plan):
    from .batch_preflight import portrait_cohort_records
    rows=portrait_cohort_records(plan)
    if rows is None:raise ValueError('Token is not a complete portrait-cohort review')
    return {row['document_id']:row for row in rows}


def prune(store):
    cache=getattr(store,'_portrait_cohort_images',None)
    if cache is not None:cache.prune(store.pending)


def attach(store,plan,displays):
    from .cohort_image_cache import cache as shared_cache
    store._prune(store.clock());prune(store)
    if store.pending.get(plan.token) is not plan:raise ValueError('Actual pending cohort required')
    records=_records(plan);cache=shared_cache(store)
    if plan.token not in cache.plans:
        cache.attach(plan,displays);return
    # A mandatory collarbone review may already own these exact immutable
    # pixels. Compare every byte-bearing DTO instead of writing duplicate PNGs.
    if type(displays) is not dict or set(displays)!=set(records):raise ValueError('Complete source-first cohort display set required')
    for doc,record in records.items():
        display=displays[doc]
        if type(display) is not dict or set(display)!={'revision','before','after'} or display['revision']!=record['revision']:
            raise ValueError('Dual cohort display identity changed')
        for side in ('before','after'):
            if cache.read(plan,doc,record['revision'],side,record[side]['sha256'])!=display[side]:
                raise ValueError('Dual cohort pixels differ; no implicit image replacement')


def verify_available(store,plan):
    store._prune(store.clock());prune(store)
    if store.pending.get(plan.token) is not plan:raise ValueError('Cohort expired or consumed')
    cache=getattr(store,'_portrait_cohort_images',None)
    if cache is None:raise ValueError('Cohort images unavailable')
    for doc,record in _records(plan).items():
        for side in ('before','after'):cache.read(plan,doc,record['revision'],side,record[side]['sha256'])


def retrieve(controller,request):
    if (type(request) is not dict or set(request)!=REQUEST_FIELDS or request.get('cmd')!='batch'
            or request.get('action')!='portrait_cohort_visual' or request.get('side') not in ('before','after')
            or any(type(request.get(k)) is not str or not 1<=len(request[k])<=128 for k in ('request_id','document_id'))
            or type(request.get('revision')) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})',request['revision']) is None
            or int(request['revision'])>2**64-1 or type(request.get('sha256')) is not str
            or re.fullmatch('[a-f0-9]{64}',request['sha256']) is None):raise ValueError('Exact portrait-cohort image coordinates required')
    try:plan=controller.store.get(request['preflight_token'],controller.versions.workspace)
    finally:prune(controller.store)
    records=_records(plan)
    if request['document_id'] not in records:raise ValueError('Image is not a reviewed cohort member')
    cache=getattr(controller.store,'_portrait_cohort_images',None)
    if cache is None:raise ValueError('Cohort images no longer retained')
    pixels=cache.read(plan,request['document_id'],request['revision'],request['side'],request['sha256'])
    return {'event':'batch_result','action':'portrait_cohort_visual','success':True,
            **{k:request[k] for k in ('request_id','preflight_token','document_id','revision','side','sha256')},
            'compact':{k:v for k,v in pixels.items() if k!='base64'},'image':pixels}
