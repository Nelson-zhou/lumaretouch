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
            if set(request)!={'cmd','action','request_id','preflight_token'}:
                raise ValueError('Derived transfer accepts only its frozen token; no unreviewed commit')
        elif action in ('undo','redo'):
            if set(request)!={'cmd','action','request_id','batch_id'}:
                raise ValueError('Derived transfer history requires one protected ledger identity')
        elif set(request)-{'cmd','action','request_id','docs','module_scope','conflict_policy',
                          'local_mask_transfer','reference_color','people_transfer'}:
            raise ValueError('Invalid reviewed transfer options')
        return
    if name=='preset' and action in ('preflight','apply','save','list','import','delete','xmp_inspect'):
        return  # Preset owner validates exact schema and actual stored modules.
    raise ValueError('Unsupported derived transfer route')
