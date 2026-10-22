"""Thin adapters for the single scope contract; no second preset wire format."""
from . import sky_replacement_state as S, sky_replacement_assets as A
from . import sky_replacement_scope as C


def extract(value):
    recipe=C.params_of({'_sky_replacement':S.check(value)})['recipe']
    if recipe['enabled']:A.verify(recipe['asset'])
    return recipe


def check(value):
    return C.check_params({'recipe':value})['recipe']


def apply(preset,target,source_path,source_shape,*,background_active=False):
    """Validate before the caller's atomic history transaction, never copy masks."""
    state={'_sky_replacement':S.check(target),'_bg':{'active':background_active}}
    C.install(state,{'recipe':preset})
    C.validate_target(state['_sky_replacement'],source_path,source_shape)
    return state['_sky_replacement']


def preflight(preset,targets):
    preset=check(preset);rows=[]
    for target in targets:
        try:
            value=apply(preset,target['sky_replacement'],target['path'],target['shape'],
                        background_active=bool(target.get('background_active')))
            rows.append({'document_id':target['document_id'],'ready':True,'value':value,'error':None})
        except Exception as error:
            rows.append({'document_id':target.get('document_id'),'ready':False,'value':None,'error':str(error)[:2000]})
    return rows
