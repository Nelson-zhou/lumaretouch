"""Host hooks for canonical project/history/export persistence. No second graph."""
from copy import deepcopy
from . import hair_colour_assets as A, hair_colour_analysis as E, hair_colour_evidence as SAVED

KEY = 'hair_colour_assets'


def store(engine):
    return engine.__dict__.setdefault('_hair_colour_assets', {})


def save(engine, project):
    project[KEY] = A.verify_graph(engine._people_owner().snapshot(), store(engine))
    project[SAVED.KEY] = SAVED.verify_assets(project[KEY], engine.__dict__.get('_hair_colour_evidence', {}))


def validate(project, *, allowed=True):
    from . import people_state as P
    from . import hair_colour_state as S
    if not allowed:
        def reject_new(value):
            if isinstance(value,dict):
                if KEY in value or SAVED.KEY in value or value.get('operation_id')==S.OPERATION or A.KIND in value.get('local_assets',{}):
                    raise ValueError('Hair colour data requires project v14; older schema cannot silently ignore its ownership')
                for child in value.values():reject_new(child)
            elif isinstance(value,(list,tuple)):
                for child in value:reject_new(child)
        reject_new(project)
    assets = A.verify_graph(project.get('people_graph', P.empty()), project.get(KEY, {}))
    SAVED.verify_assets(assets, project.get(SAVED.KEY, {}))
    def check_references(value):
        if isinstance(value,dict):
            if 'face_instance_id' in value and 'local_assets' in value and A.KIND in value['local_assets']:
                graph=P.empty();graph['faces'][value['face_instance_id']]=value
                A.resolve(P.check(graph),assets,P.face_ref(value))
            for child in value.values():check_references(child)
        elif isinstance(value,(list,tuple)):
            for child in value:check_references(child)
    check_references(project) # Includes inactive versions, undo/redo and batch graph patches.
    return assets


def load(engine, project):
    engine._hair_colour_assets = validate(project)
    engine._hair_colour_evidence = SAVED.check_store(project.get(SAVED.KEY, {}))
    engine.__dict__.pop('_hair_colour_reviews', None)
    engine.__dict__.pop('_hair_colour_receipts', None)


def capture(engine, snapshot, precompute, binding, *, source_path):
    """Append exact owned vectors and measured source semantics to people snapshot."""
    from . import hair_colour_state as S, people_resolver as R, people_state as P
    state = snapshot['state']; asset = snapshot['asset_sha256']
    needed = any(face['asset_sha256'] == asset and face['enabled'] and S.active(R.materialize(
        R.resolve(state, face['face_instance_id'], {S.OPERATION: {'/style': S.neutral()['style'], '/strength': 0., '/gloss': 0.}}),
        S.OPERATION, S.neutral(), S.check)) for face in state['faces'].values())
    snapshot[KEY] = A.check_store(store(engine))
    snapshot['hair_colour_evidence'] = SAVED.current(engine, binding, precompute) if needed else None
    snapshot['hair_colour_source_path'] = source_path
    snapshot['hair_colour_source_stamp'] = None
    if needed:
        from .local_mask_state import file_stamp,source_digest
        if not source_path:raise ValueError('Hair export requires the exact retained source path')
        before=file_stamp(source_path)
        if source_digest(source_path)!=binding['sha256'] or file_stamp(source_path)!=before:
            raise ValueError('Hair source changed while freezing export inputs')
        snapshot['hair_colour_source_stamp']=list(before)
    return snapshot


def verify_snapshot(snapshot):
    if snapshot.get('hair_colour_evidence') is None:return
    from .local_mask_state import file_stamp
    path=snapshot.get('hair_colour_source_path');stamp=snapshot.get('hair_colour_source_stamp')
    if not path or list(file_stamp(path))!=stamp:
        raise ValueError('Hair source changed after retained export inputs were frozen')


def verify_render_source(spec):
    snapshot=getattr(spec,'people',None)
    if snapshot is not None:verify_snapshot(snapshot)


def kwargs(snapshot):
    verify_snapshot(snapshot)
    return {'hair_assets': A.check_store(snapshot.get(KEY, {})),
            'hair_evidence': E.freeze(snapshot.get('hair_colour_evidence')),
            'hair_source_path': snapshot.get('hair_colour_source_path')}


def preview_kwargs(engine, candidate=None):
    from . import hair_colour_state as S, people_algorithms as PA, people_resolver as R
    graph = engine._people_owner().snapshot() if candidate is None else candidate
    binding = engine._people_source(); asset = binding['sha256']
    needed = any(face['asset_sha256'] == asset and face['enabled'] and S.active(R.materialize(
        R.resolve(graph, face['face_instance_id'], PA.defaults()), S.OPERATION, S.neutral(), S.check)) for face in graph['faces'].values())
    return {'hair_assets': A.check_store(store(engine)),
            'hair_evidence': SAVED.current(engine, binding) if needed else None,
            'hair_source_path': engine._doc_path}
