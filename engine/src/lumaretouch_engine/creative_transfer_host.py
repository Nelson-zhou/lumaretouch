"""Route reviewed transfers to their owners, never exempt arbitrary edits.

Actual stored/frozen module admission, source proofs, target preparation and
receipt replay live in the batch/preset controllers. This is only a narrow
transport gate and deliberately admits no legacy unreviewed batch commit.
"""

def inventory_read_only(request):
    if (type(request) is not dict or set(request)!={'cmd','action','request_id','docs'}
            or request.get('cmd')!='batch' or request.get('action')!='people_targets'):
        return False
    identity=request['request_id'];docs=request['docs']
    return (type(identity) is str and 1<=len(identity)<=128 and type(docs) is list
        and 1<=len(docs)<=16 and all(type(value) is str and 1<=len(value)<=128 for value in docs)
        and len(set(docs))==len(docs))


def head_preflight_read_only(request):
    """Photo-read-only head review, never an apply/commit or arbitrary scope.

    A preset's request scope is only an expectation: its owner separately
    compares it with the actual stored modules before producing any proof.
    This predicate never clears a pre-existing recovery/receipt mutation fence.
    """
    if (type(request) is not dict or request.get('action')!='preflight'
            or request.get('module_scope')!=['lnx.head_size.v1']):
        return False
    def bounded_text(value):
        if type(value) is not str or not value.strip():return False
        try: bounded=len(value.encode('utf-8'))<=128
        except UnicodeError:return False
        return bounded and not any(ord(char)<32 or 0x7f<=ord(char)<=0x9f for char in value)
    if not bounded_text(request.get('request_id')):return False
    required={'cmd','action','request_id','module_scope'}
    if request.get('cmd')=='preset':
        if set(request)!=required|{'id','document_id'}:return False
        return all(bounded_text(request[key]) for key in ('id','document_id'))
    if request.get('cmd')!='batch' or not (required|{'docs'})<=set(request):return False
    if set(request)-(required|{'docs','conflict_policy'}):return False
    if request.get('conflict_policy','skip_and_report') not in ('skip_and_report','recheck'):return False
    docs=request['docs']
    return (type(docs) is list and 1<=len(docs)<=8
            and all((type(value) is int and 0<=value<=2**53-1)
                    or bounded_text(value) for value in docs)
            and len(set(docs))==len(docs))


def require_route(name,request):
    if type(request) is not dict or request.get('cmd')!=name:
        raise ValueError('Invalid reviewed transfer request')
    action=request.get('action')
    if name=='batch':
        if action=='people_targets':
            if not inventory_read_only(request):raise ValueError('Face inventory requires bounded exact document identities')
            return
        if action=='state':
            if set(request)-{'cmd','action','request_id'}:raise ValueError('Invalid batch status envelope')
            return
        if action not in ('preflight','commit','undo','redo'):
            raise ValueError('Derived transfer requires a reviewed native batch route')
        rid=request.get('request_id')
        if type(rid) is not str or not 1<=len(rid)<=128:
            raise ValueError('Derived transfer requires its correlated receipt identity')
        if action=='commit':
            required={'cmd','action','request_id','preflight_token'}
            if set(request) not in (required,required|{'head_review_ack'}):
                raise ValueError('Derived transfer accepts only its frozen token; no unreviewed commit')
        elif action in ('undo','redo'):
            if set(request)!={'cmd','action','request_id','batch_id'}:
                raise ValueError('Derived transfer history requires one protected ledger identity')
        elif set(request)-{'cmd','action','request_id','docs','module_scope','conflict_policy',
                          'local_mask_transfer','reference_color','people_transfer'}:
            raise ValueError('Invalid reviewed transfer options')
        return
    if name=='preset' and action=='collarbone_visual':
        from .collarbone_preset_store import image_read_only
        if not image_read_only(request):raise ValueError('Preset image read requires its exact bounded identity')
        return  # Never an apply exemption; actual preset owner checks the token.
    if name=='preset' and action in ('preflight','apply','save','list','import','delete','xmp_inspect'):
        return  # Preset owner validates exact schema and actual stored modules.
    raise ValueError('Unsupported derived transfer route')
