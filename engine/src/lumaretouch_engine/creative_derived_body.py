"""Effective-source admission for existing measured body owners.

No landmarks, supports or reviews are manufactured here. The native body
adapters remain the sole mutation, review, publication and receipt owners.
"""
from . import body_pose_evidence as E

COMMANDS=frozenset(('shoulder_shape','leg_shape','arm_shape','waist_shape','leg_length','neck_shape','torso_length','waist_length','head_size'))
_TRANSPORTS=dict(zip(('shoulder_shape','leg_shape','arm_shape','waist_shape','leg_length','neck_shape','torso_length','waist_length','head_size'),
                    ('_body_transport','_leg_transport','_arm_transport','_waist_transport','_leg_length_transport','_neck_transport','_torso_length_transport','_waist_length_transport','_head_size_transport')))
_OWNERS=dict(zip(('shoulder_shape','leg_shape','arm_shape','waist_shape','leg_length','neck_shape','torso_length','waist_length','head_size'),
                ('_body_edit_owner','_leg_edit_owner','_arm_edit_owner','_waist_edit_owner','_leg_length_edit_owner','_neck_edit_owner','_torso_length_edit_owner','_waist_length_edit_owner','_head_size_edit_owner')))
_LEDGERS={'leg_shape':'_leg_receipts','waist_shape':'_waist_receipts',
          'leg_length':'_leg_length_receipts','neck_shape':'_neck_receipts','torso_length':'_torso_length_receipts','waist_length':'_waist_length_receipts','head_size':'_head_size_receipts'}


def validate(bank, source):
    """Check dormant observations/supports as well as the rendered winners.

    Old supports from explicit same-source reanalysis may remain immutable
    history assets. They must still name this source, not the original file.
    """
    from . import arm_shape_project as P, body_pose_operations as O
    from .body_pose_render import source as frame_source
    frame=frame_source(source);bank=P.check(bank);known=O.policies()
    if any(asset!=frame['sha256'] for asset in bank['analysis_runs']):
        raise ValueError('Derived body run belongs to another effective source')
    for row in bank['bodies'].values():
        record=row['record']
        if record['source']!=frame:
            raise ValueError('Derived body observation belongs to another effective source')
        E.whole_source_shape(frame,tuple(reversed(record['input_dimensions'])))
        if any(operation not in known for operation in row['operations']):
            raise ValueError('Derived body contains an unadapted operation, including dormant intent')
    for support in bank['support_assets'].values():
        if support['source']!=frame or support['operation_id'] not in known:
            raise ValueError('Derived body support belongs to another source or unadapted operation')
    return bank


def _retained(engine,name,message):
    """Let the existing owner return its exact receipt without new admission.

    No mutation is performed here. A retained ID with different bytes refuses;
    a released outer response still reaches the owner's query-only outcome.
    """
    digest=E.content_digest(message);owner=engine.__dict__.get(_TRANSPORTS[name])
    if owner is not None and message['request_id'] in owner.seen:
        if owner.seen[message['request_id']]!=digest:
            raise ValueError('Derived body transport ID was reused with different content')
        return True
    if message['action'] not in ('edit','execute'):return False
    request=message['request'];ident=E.token(request.get('request_id'));row=None
    ledger=engine.__dict__.get(_LEDGERS.get(name,''),{})
    if ident in ledger:row=ledger[ident]
    journal=engine.__dict__.get('_arm_receipt_journal') if name=='arm_shape' else None
    if journal is not None:row=journal.get(ident)
    if row is None:
        owner=engine.__dict__.get(_OWNERS[name])
        if owner is not None:row=owner.receipts.get(ident)
    if row is not None:
        if row['digest']!=E.content_digest(request):
            raise ValueError('Derived body edit ID was reused with different content')
        return True
    return False


def _payload(name,action,value):
    """Bound admitted actions; existing adapters validate numerical semantics."""
    if type(value) is not dict:raise ValueError('Body command needs explicit payload')
    if name=='arm_shape':
        fields={
            'recipe':{'base','recipe','targets','linked'},
            'support_review':{'segment','strategy','points_sha256','visible_anchors','ownership_confirmed','confirmations','manual','proposal_id','candidate'},
            'operation_status':{'segment','enabled'},
            'proposal':{'segment','region','device'},
        }
    elif name=='shoulder_shape':
        fields={'recipe':{'base','recipe'},'review':{'points_sha256','visible_anchors','ownership_confirmed'},
                'associate':{'person_id','user_confirmed'},'unlink':set(),
                'operation_status':{'operation_id','enabled'},'body_status':{'enabled'}}
    else:
        fields={'recipe':{'base','recipe'},'support_review':{'data','points_sha256','visible_anchors','ownership_confirmed'},
                'operation_status':{'enabled'}}
    if action not in fields or set(value)!=fields[action]:
        raise ValueError('Unadapted derived body action or payload')


def require_command(engine,name,message):
    """Exact existing transport plus actual current native envelope fences."""
    from .creative_derived_source import binding, verify
    from . import body_pose_state as B, body_pose_families as F
    if name not in COMMANDS or type(message) is not dict or set(message)!={'cmd','request_id','action','request'} or message['cmd']!=name:
        raise ValueError('Derived body requires its exact native transport envelope')
    E.token(message['request_id']);request=message['request'];action=message['action']
    if type(request) is not dict:raise ValueError('Derived body request must be explicit')
    # Queries/cancellation cannot acquire pixels or change body intent, and must
    # remain reachable after a document switch or uncertain publication.
    if action=='status':
        if set(request)!={'request_id'}:raise ValueError('Body status requires the original request ID')
        E.token(request['request_id']);return
    if name=='arm_shape' and action in ('proposal_status','proposal_cancel'):
        if set(request)!={'job_id'}:raise ValueError('Arm job query requires its exact ID')
        E.token(request['job_id']);return
    if _retained(engine,name,message):return
    source=binding(engine);bank=validate(engine._body_bank(),source)
    people=engine._people_owner().snapshot()
    from .creative_derived_effects import require_graph
    require_graph(people,source,document_id=engine._people_binding()['document_id'])
    if action=='view':
        if request!={}:raise ValueError('Body view cannot override source inputs')
    elif action in ('select','analyse','reanalyse') and (name!='arm_shape' or action=='select'):
        fields={'select':{'binding','body_ref'},'analyse':{'binding'},
                'reanalyse':{'binding','body_ref','candidate_ref','run_id','user_confirmed'}}[action]
        if set(request)!=fields or request['binding']!=engine._people_binding():
            raise ValueError('Derived body acquisition/selection binding changed')
        if action!='analyse':
            ref=E.ref(request['body_ref']);B.target(bank,ref)
            if ref['asset_sha256']!=source['sha256']:raise ValueError('Derived body selection names another source')
        if action=='reanalyse':
            if E.ref(request['candidate_ref'])['asset_sha256']!=source['sha256'] or request['user_confirmed'] is not True:
                raise ValueError('Derived body replacement needs explicit same-source ownership')
            E.token(request['run_id'])
    elif (name=='arm_shape' and action in ('execute','proposal_start')) or (name!='arm_shape' and action=='edit'):
        if request.get('request_id')==message['request_id']:
            raise ValueError('Body edit and transport request identities must differ')
        native=F.presenter(name)
        if name=='shoulder_shape':
            native.envelope(request,engine._people_binding(),bank)
            if request['people_association_revision']!=people['association_revision']:
                raise ValueError('Body person ownership changed')
        else:native.envelope(request,engine._people_binding(),bank,people)
        _payload(name,request['action'],request['payload'])
        if name=='arm_shape' and (request['action']=='proposal')!=(action=='proposal_start'):
            raise ValueError('Arm proposal and edit routes are distinct')
    else:raise ValueError('Unadapted derived body command')
    verify(source,engine)
