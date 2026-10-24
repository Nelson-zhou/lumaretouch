# SPDX-License-Identifier: GPL-3.0-or-later
"""Composite publication before current-only history, preserving family contracts.

The exact frozen plan and its family-specific ledger own all graph/current-state
writes. This helper only routes verified publication and retains receipt facts.
"""
from copy import deepcopy
from . import scope as SC, optics_auto_scope as OA


def publish(controller,p,portrait,record,mods,doc,row,identity,revision,previous,state,before,ops,source_proof):
    name=portrait.name
    if name not in ('eye_bag','face_decoration') or record[name]['version']!=2:
        raise SC.ScopeError('Only an exact version-two composite family may use alias publication')
    wrapper=record[name];marker_key=name+'_preset_alias_review'
    publisher=getattr(controller.ports,'publish_'+name+'_alias',None)
    if publisher is None or getattr(controller.ports,'verify_'+name+'_alias',None) is None:
        raise SC.ScopeError('Complete mixed preset alias publication is unavailable')
    try:
        options={'verify_images':lambda:portrait.store.verify_claimed(controller.reviews,p['preflight_token'],wrapper)}
        if name=='face_decoration':options['ack']=deepcopy(p[portrait.ack])
        bid,frame=publisher(row,previous,state,identity[2],str(revision),wrapper,mods,controller.request_id(p),**options)
        controller._effect_started=True
        # Preserve known ledger identity before any later status/frame operation.
        controller._scalar_receipt['batch_id']=bid
        aliases=[{'document_id':member['visual']['document_id'],
            'expected_revision':member['visual']['revision'],
            'result_revision':str(int(member['visual']['revision'])+1)} for member in wrapper['members']]
        marker={'version':1,**{key:wrapper[key] for key in ('review_sha256','preset_sha256','applies_sha256')},
            'current_document_id':aliases[0]['document_id'],'member_count':len(aliases),'selected_modules':ops}
        controller._scalar_receipt.update(alias_members=aliases,**{marker_key:marker})
        after=OA.before_params(state,ops);pid=doc['id']
        controller.last={'id':pid,'name':doc['name'],'ops':ops,'params':after}
        render_ms=frame.pop('render_ms',0)
        controller.emit({'event':'preset_applied','id':pid,'kind':doc['kind'],'name':doc['name'],
            'modules':ops,'before':before,'after':after,'render_ms':render_ms,'doc_state':controller.ports.status()})
        controller.emit(frame)
        return {'id':pid,'name':doc['name'],'module_scope':ops,'before':before,'after':after,
            'document_id':identity[2],'preflight_token':p['preflight_token'],
            'source_proof':source_proof,**deepcopy(controller._scalar_receipt)}
    except Exception as error:
        controller._effect_started=controller._effect_started or bool(getattr(error,'side_effects_started',False))
        if getattr(error,'batch_id',None) is not None:controller._scalar_receipt['batch_id']=error.batch_id
        for key in ('alias_members',marker_key):
            if getattr(error,key,None) is not None:controller._scalar_receipt[key]=deepcopy(getattr(error,key))
        raise
