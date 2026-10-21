"""Read-only colour-scope request contract through narrow, injected ports."""
from dataclasses import dataclass
from typing import Callable
from .color_scopes_sampling import STAGES

@dataclass(frozen=True)
class ScopePorts:
    document_id:Callable[[],str]
    guard:Callable[[],str|None]
    sample:Callable[[str],object]
    analyze:Callable[[object],dict]


def handle_scopes(p:dict,ports:ScopePorts,emit:Callable[[dict],None]):
    request=p.get('request_id');document=p.get('document_id');stage=p.get('stage');ticket=p.get('ticket')
    result={'event':'color_scopes','request_id':request if type(request) is str and len(request)<=128 else None,
            'ticket':ticket if type(ticket) is str and len(ticket)<=20 else None,
            'document_id':ports.document_id(),'stage':stage if stage in STAGES else None}
    try:
        if set(p)-{'cmd','request_id','document_id','stage','ticket'}:raise ValueError('unknown colour-scope fields')
        if type(ticket) is not str or not ticket.isascii() or not ticket.isdigit() or not 1<=len(ticket)<=20:
            raise ValueError('invalid scope ticket')
        if type(request) is not str or not 1<=len(request)<=128:raise ValueError('invalid scope request identity')
        if type(document) is not str or not document or len(document)>64 or document!=ports.document_id():
            raise ValueError('document changed; refresh colour scopes')
        if stage not in STAGES:raise ValueError('unknown scope stage')
        reason=ports.guard()
        if reason:raise ValueError(reason)
        sample=ports.sample(stage)
        analysis=ports.analyze(sample)
        if document!=ports.document_id():raise ValueError('document changed during colour sampling')
        result.update(success=True,error=None,analysis=analysis,quality='sampled-proxy-float',
            profile='working-srgb',rgb_domain='srgb-display',luminance_domain='linear-srgb-y',
            lab_whitepoint='D65',alpha_policy='opaque-rgb',sampling='uniform-cell-centres',
            width=sample.width,height=sample.height,grid_width=sample.grid_width,grid_height=sample.grid_height,
            eligible_pixels=sample.width*sample.height,sampled_pixels=sample.grid_width*sample.grid_height)
    except Exception as error:result.update(success=False,error=str(error)[:2000])
    emit(result)
