"""Correlated organisation port. Catalogue edits never touch image history/pixels."""
from . import preset_store as PS
from .preset_organisation_store import OrganisationStore, OrganisationError


def handle(request,emit):
    rid=request.get('request_id'); action=request.get('action')
    result={'event':'preset_organisation_result','protocol':1,'request_id':rid,'action':action,
            'success':False,'outcome_unknown':False}
    try:
        if type(rid) is not str or not 0<len(rid)<=128: raise OrganisationError('目录请求身份无效')
        if request.get('cmd')!='preset_organisation': raise OrganisationError('目录命令无效')
        store=OrganisationStore(PS.preset_dir(),PS.raw_list_all)
        payload={k:v for k,v in request.items() if k!='cmd'}
        if action=='snapshot':
            if set(payload)!={'action','request_id'}: raise OrganisationError('目录快照字段无效')
            result['catalog']=store.snapshot()
        elif action=='receipt':
            if set(payload)!={'action','request_id','target_request_id'} or type(payload['target_request_id']) is not str or not 0<len(payload['target_request_id'])<=128:
                raise OrganisationError('回执查询字段无效')
            receipt=store.receipt(payload['target_request_id'])
            result['target_request_id']=payload['target_request_id']; result['receipt']=receipt
            result['found']=receipt is not None
        else: result['receipt']=store.transact(payload)
        result['success']=True
    except Exception as error:
        result['error']=str(error)[:2000]
        result['outcome_unknown']=bool(getattr(error,'outcome_unknown',False))
    emit(result)


class PresetOrganisationHostMixin:
    def cmd_preset_organisation(self,p):
        # Engine dispatcher calls cmd_* for catalogue-only commands, before photo history.
        from .server import emit
        handle(p,emit)
