"""Legacy face event/view adapter backed by stable instances, not box identity."""
import uuid
from . import people_state as S,people_edit as EDIT
from .people_host_commands import checked,select,publish,analyse


def report(engine):
    source=engine._people_source();state=engine._people_owner().snapshot();asset=source['sha256']
    selected=engine._people_cursors.get(asset);faces=[]
    for index,(key,face) in enumerate(sorted(state['faces'].items())):
        if face['asset_sha256']!=asset:continue
        faces.append({'index':len(faces),'face_instance_id':key,'box':face['box'],'manual':face['manual'],
                      'disabled':not face['enabled'],'analysis_status':face['evidence']['status']})
    current=next((f for f in faces if f['face_instance_id']==selected),None)
    enabled=[f['index'] for f in faces if not f['disabled']]
    run=state['analysis_runs'].get(asset,{})
    return {'index':current['index'] if current else 0,'explicit':current is not None,'box':current['box'] if current else None,
        'num_faces':len(faces),'faces':faces,'enabled':enabled,'disabled_count':len(faces)-len(enabled),
        'probed':len([f for f in faces if not f['manual']]),'blocked':current is None,
        'scope_block':'multi_face' if len(faces)>1 else None,'max_faces_probed':run.get('detector_limit',32),
        'manual':{'disabled':[f['box'] for f in faces if f['disabled']], 'added':[f['box'] for f in faces if f['manual']],
                  'stale':[],'lost':[],'new_faces':[],'preview':run.get('notice','人物区域不代表完整人数统计')},
        'selection_only':True,'census_complete':False}


def apply(engine,p,emit):
    action=p.get('action','list')
    if action=='list':
        state=report(engine);emit({'event':'face_list','face':state,**state});return
    context=p.get('people_context')
    if type(context) is not dict:raise ValueError('Legacy face changes require captured stable people context')
    envelope={**context,'request_id':uuid.uuid4().hex};before,binding,target=checked(engine,envelope)
    if action=='add':
        source=engine._people_source();command={**envelope,'action':'manual_add','payload':{'box':p.get('rect')}}
        result=EDIT.stage(command,before,**{k:binding[k] for k in ('document_id','document_epoch','document_revision')},asset_sha256=source['sha256'],source_dimensions=(source['width'],source['height']))
        candidate,ref=analyse(engine,result['state'],S.face_ref(result['state']['faces'][result['created_id']]))
        _,frame=publish(engine,before,candidate,envelope['request_id'])
        select(engine,engine._people_owner().snapshot(),source['sha256'],{'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref})
        state=report(engine)
        if frame is not None:frame['doc_state']=engine.doc_state();emit(frame)
        emit({'event':'face_manual','action':'add','face':state,**state,'doc_state':engine.doc_state()});return
    raise ValueError('Use stable people selection/status controls; index-only mutation cannot reassign retained faces')
