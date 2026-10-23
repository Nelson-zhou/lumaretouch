"""Small host port; source rendering remains in the canonical export chain."""
from . import fringe_repair_state as S


class FringeRepairHostMixin:
    def cmd_fringe_repair_preview(self,p):
        from .fringe_repair_review import controller
        controller(self,self._fringe_emit).handle(p)
    def cmd_fringe_repair(self,p):
        from .fringe_repair_controller import controller
        controller(self,self._fringe_emit).handle(p)
    @staticmethod
    def _fringe_emit(value):
        from .server import emit
        emit(value)
    def _fringe_active(self):
        from .fringe_repair_render import active
        return active(self)
    def _fringe_cancel_preview(self):
        owner=self.__dict__.get('_fringe_repair_preview_owner')
        if owner is not None:owner.cancel()
    def _fringe_status(self):
        from .fringe_repair_native import available
        return {'recipe':S.check(getattr(self,S.KEY,None)),'available':available(),
            'algorithm':S.ALGORITHM,'quality_acceptance':'UNRUN',
            'scope':'guided-newly-introduced-achromatic-halos; baked-in-halos-not-guaranteed'}


def require_derived(engine,name,request):
    """Only the real canonical source is eligible; never original-image analyses."""
    from .creative_document_host import require_photo_return
    from .creative_derived_source import record,binding
    from .creative_derived_repair_runtime import verify_pipeline
    if name not in ('fringe_repair','fringe_repair_preview'):raise ValueError('Invalid fringe route')
    if request.get('action')=='cancel':return
    require_photo_return(record(engine))
    verify_pipeline(engine._vram,binding(engine))
    S.verify_source(S.check(engine._fringe_repair),engine)


def dispatch_rejected(request,error,started,emit):
    """Known pre-controller refusal differs from an interrupted commit."""
    base={'protocol':1,**{key:request.get(key) for key in ('preview_id','session_id','document_id')},
        'success':False,'error':str(error)[:2000]}
    if request.get('cmd')=='fringe_repair_preview':
        emit({'event':'fringe_repair_preview','state':'failed',**base})
    else:
        emit({'event':'fringe_repair_result','action':'apply','request_id':request.get('request_id'),
            'outcome_unknown':bool(started),'requires_reload':bool(started),'no_change':False,'history':None,**base})
