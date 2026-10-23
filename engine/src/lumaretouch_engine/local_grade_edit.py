"""History-bearing independent-group edits through the existing capture proof."""
from types import SimpleNamespace
from . import local_grade_layers as L, local_mask_state as M


def prepare(engine, capture, mutation):
    if type(mutation) is not dict: raise ValueError('Invalid group mutation')
    action = mutation.get('action')
    fields = {'layer_update': {'action','id','name','enabled','grade'},
              'layer_delete': {'action','id'}, 'layer_move': {'action','id','index'},
              'layer_mask': {'action','id','mutation'}}
    if action not in fields or set(mutation) != fields[action]: raise ValueError('Invalid group mutation fields')
    groups = L.check(getattr(engine, '_local_grade_layers', None))
    layers = groups['layers']
    index = next((i for i, layer in enumerate(layers) if layer['id'] == mutation['id']), None)
    if index is None: raise ValueError('局部调色组已不存在')
    if action == 'layer_update':
        layers[index] = L.check_layer({**layers[index], **{key:mutation[key] for key in ('name','enabled','grade')}})
    elif action == 'layer_delete': layers.pop(index)
    elif action == 'layer_move':
        target = mutation['index']
        if type(target) is not int or not 0 <= target < len(layers): raise ValueError('Invalid group order')
        layers.insert(target, layers.pop(index))
    else:
        from .local_mask_controller import prepare_mutation
        inner = mutation['mutation']
        if type(inner) is not dict or inner.get('action') not in ('upsert','delete','move'):
            raise ValueError('Group mask edit must retain the group binding')
        view = SimpleNamespace(**vars(engine))
        view._local_masks, view._grade_scope = layers[index]['mask'], 'objects'
        owner = layers[index]['mask']['semantic_owner']
        from .creative_derived_source import record
        if owner is not None and record(engine) is None:
            from .local_grade_semantics import model_bytes
            model_bytes(owner)  # Existing group owns the exact model, not the selected face.
        layers[index]['mask'], _ = prepare_mutation(view, capture, inner, semantic_owner=owner)
    full = capture['descriptor']['full_source']
    L.validate_budget(groups, (full[1], full[0]))
    return L.check(groups)
