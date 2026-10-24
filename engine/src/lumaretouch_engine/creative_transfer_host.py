"""Route reviewed transfers to their owners, never exempt arbitrary edits.

Actual stored/frozen module admission, source proofs, target preparation and
receipt replay live in the batch/preset controllers. This is only a narrow
transport gate and deliberately admits no legacy unreviewed batch commit.
"""
import re


def face_style_preflight_read_only(request):
    """Exact target-owned named-style review, not arbitrary people preflight.

    This checks only detached request metadata. Actual source/graph ownership
    and existing mutation fences remain the controller's responsibility.
    """
    fields={'cmd','action','request_id','docs','module_scope','people_transfer'}
    if (type(request) is not dict or not fields<=set(request)
            or set(request)-(fields|{'conflict_policy'}) or request.get('cmd')!='batch'
            or request.get('action')!='preflight'
            or request.get('conflict_policy','skip_and_report') not in ('skip_and_report','recheck')):
        return False
    identity=request['request_id'];docs=request['docs'];value=request['people_transfer']
    if (type(identity) is not str or not identity.strip() or len(identity)>128
            or any(ord(char)<32 or 0x7f<=ord(char)<=0x9f for char in identity)
            or type(docs) is not list or not 1<=len(docs)<=16
            or any(type(doc) is not str or re.fullmatch('[0-9a-f]{32}',doc) is None for doc in docs)
            or len(set(docs))!=len(docs) or type(value) is not dict
            or value.get('target_policy')!='explicit_face_map' or 'face_style' not in value):
        return False
    try:
        from .face_style_batch_review import selection
        from .people_transfer_inventory import check_proof
        from .people_batch_transfer import options
        if request['module_scope']!=list(selection(value['face_style'])):return False
        source=check_proof(value.get('source'))
        checked=options(value,request['module_scope'],source['source_proof']['asset_sha256'])
        targets=checked['targets']
        if set(docs)!={item['target']['document']['document_id'] for item in targets}:return False
        for endpoint in [source]+[item['target'] for item in targets]:
            if (re.fullmatch('[0-9a-f]{32}',endpoint['document']['document_id']) is None
                    or any(endpoint[key]>2**53-1 for key in ('state_revision','association_revision'))
                    or endpoint['document']['revision']>2**53-1):return False
        refs=[checked['source_ref']]+[ref for item in targets for ref in item['target_refs']]
        return all(ref['analysis_revision']<=2**53-1 for ref in refs) and len(identity.encode('utf-8'))<=128
    except (ValueError,TypeError,KeyError,UnicodeError):
        return False


def face_style_image_read_only(request):
    """Only a cached image read, never a recipe, graph or apply exemption."""
    fields={'cmd','action','request_id','preflight_token','document_id','revision','side','sha256'}
    if (type(request) is not dict or set(request)!=fields or request.get('cmd')!='batch'
            or request.get('action')!='face_style_visual' or request.get('side') not in ('before','after')):
        return False
    for key in ('request_id','document_id'):
        value=request[key]
        if type(value) is not str or not 1<=len(value)<=128:return False
    token=request['preflight_token'];revision=request['revision'];digest=request['sha256']
    return (type(token) is str and re.fullmatch('[a-f0-9]{32}',token) is not None
            and type(revision) is str and re.fullmatch('(0|[1-9][0-9]{0,19})',revision) is not None
            and int(revision)<=2**64-1 and type(digest) is str
            and re.fullmatch('[a-f0-9]{64}',digest) is not None)


def portrait_cohort_preflight_read_only(request):
    """Only an explicit named persistent review is metadata-provably read-only.

    A generic patch/unlink cannot prove its prior saved full-portrait intent
    from this envelope, so it deliberately keeps the existing guarded route.
    """
    fields={'cmd','action','request_id','docs','module_scope','people_transfer'}
    if (type(request) is not dict or not fields<=set(request)
            or set(request)-(fields|{'conflict_policy'}) or request.get('cmd')!='batch'
            or request.get('action')!='preflight' or request.get('conflict_policy','recheck')!='recheck'):
        return False
    identity=request['request_id'];docs=request['docs'];value=request['people_transfer']
    if (type(identity) is not str or not identity.strip() or len(identity)>128
            or any(ord(char)<32 or 0x7f<=ord(char)<=0x9f for char in identity)
            or type(docs) is not list or not 1<=len(docs)<=15
            or any(type(doc) is not str or re.fullmatch('[0-9a-f]{32}',doc) is None for doc in docs)
            or len(set(docs))!=len(docs) or type(value) is not dict
            or value.get('target_policy')!='persistent_association'
            or value.get('operation') not in ('create','patch') or 'face_style' not in value):
        return False
    try:
        from .face_style_batch_review import selection
        from .people_cross_owner_workflow import options
        if request['module_scope']!=list(selection(value['face_style'])):return False
        checked=options(value,request['module_scope']);targets=checked['targets']
        if set(docs)!={item['target']['document']['document_id'] for item in targets}:return False
        proofs=[checked['source']]+[item['target'] for item in targets]
        refs=[checked['source_ref']]+[item['target_refs'][0] for item in targets]
        if len({proof['people_scope'] for proof in proofs})!=len(proofs):return False
        for proof,ref in zip(proofs,refs):
            if (re.fullmatch('[0-9a-f]{32}',proof['document']['document_id']) is None
                    or any(proof[key]>2**53-1 for key in ('state_revision','association_revision'))
                    or proof['document']['revision']>2**53-1 or ref['analysis_revision']>2**53-1
                    or ref['asset_sha256']!=proof['source_proof']['asset_sha256']):return False
        return len(identity.encode('utf-8'))<=128
    except (ValueError,TypeError,KeyError,UnicodeError):
        return False


def portrait_cohort_image_read_only(request):
    """Same exact cached-image coordinates, in a separate full-cohort family."""
    return (type(request) is dict and request.get('action')=='portrait_cohort_visual'
            and face_style_image_read_only({**request,'action':'face_style_visual'}))


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
        if action=='portrait_cohort_visual':
            if not portrait_cohort_image_read_only(request):raise ValueError('Portrait cohort image read requires its exact bounded identity')
            return  # Actual frozen cohort validates every source and target member.
        if action=='face_style_visual':
            if not face_style_image_read_only(request):raise ValueError('Face-style image read requires its exact bounded identity')
            return  # Frozen image owner verifies its token; no original graph is interpreted.
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
            portrait=required|{'module_scope','portrait_cohort_ack'}
            if set(request) not in (required,required|{'head_review_ack'},required|{'face_style_review_ack'},
                                    portrait,portrait|{'collarbone_review_ack'}):
                raise ValueError('Derived transfer accepts only its frozen token; no unreviewed commit')
        elif action in ('undo','redo'):
            if set(request)!={'cmd','action','request_id','batch_id'}:
                raise ValueError('Derived transfer history requires one protected ledger identity')
        elif set(request)-{'cmd','action','request_id','docs','module_scope','conflict_policy',
                          'local_mask_transfer','reference_color','people_transfer'}:
            raise ValueError('Invalid reviewed transfer options')
        return
    if name=='preset' and action=='eye_bag_visual':
        from .eye_bag_preset_store import image_read_only
        if not image_read_only(request):raise ValueError('Eye-bag preset image requires its exact bounded identity')
        return  # Frozen image retrieval cannot authorize an active recipe write.
    if name=='preset' and action=='collarbone_visual':
        from .collarbone_preset_store import image_read_only
        if not image_read_only(request):raise ValueError('Preset image read requires its exact bounded identity')
        return  # Never an apply exemption; actual preset owner checks the token.
    if name=='preset' and action in ('preflight','apply','save','list','import','delete','xmp_inspect'):
        return  # Preset owner validates exact schema and actual stored modules.
    raise ValueError('Unsupported derived transfer route')
