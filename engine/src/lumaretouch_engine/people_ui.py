"""Authoritative people UI state, independent from selected-face render output."""
from . import people_state as S, people_algorithms as A
from .people_resolver import resolve


def report(state, asset_sha256, selected_face_id=None, *, refusals=()):
    state = S.check(state); S.digest(asset_sha256)
    visible = {key:face for key,face in state['faces'].items() if face['asset_sha256'] == asset_sha256}
    if selected_face_id is not None and selected_face_id not in visible:
        raise ValueError('Selected editing cursor is not a face in this source asset')
    run = state['analysis_runs'].get(asset_sha256)
    return {'revision':state['revision'],'association_revision':state['association_revision'],
            'faces':[{'face_ref':S.face_ref(face),'enabled':face['enabled'],'box':face['box'],
                      'manual':face['manual'],'labels':face['labels'],'analysis_status':face['evidence']['status']} for key,face in sorted(visible.items())],
            'groups':state['groups'],'persons':state['persons'],'links':state['links'],
            'analysis_notice':run['notice'] if run else '此图尚无完整人物分析记录',
            'refusals':list(refusals),
            'selected_face_id':selected_face_id,
            'resolved':resolve(state,selected_face_id,A.defaults()) if selected_face_id else None}
