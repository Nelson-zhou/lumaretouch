"""Invert a presented repair-input brush without accepting display-space RLE."""
from copy import deepcopy
from .clone_stamp_geometry import inverse_stroke as inverse_clone
from .ops.heal_vector import VERSION,check_recipe,admit_memory
from .repair_record import DEFAULT_REPAIR


def inverse_stroke(spec,stroke,valid,full_source):
    if type(stroke) is not dict or set(stroke)!={'points','size','hardness','opacity'}:
        raise ValueError('Invalid reviewed heal stroke fields')
    points=stroke['points']
    if not isinstance(points,(list,tuple)) or not points:
        raise ValueError('Heal stroke requires normalized points')
    # Zero offset uses clone's exact affine footprint/padding validation, without
    # sampling or persisting a donor. It executes no clone pixel operator.
    try:
        mapped,weight=inverse_clone(spec,{**stroke,'source':points[0]},valid,full_source)
    except ValueError as error:
        message=str(error).replace('Clone','Heal').replace('clone','heal').replace('source footprint','brush footprint').replace('source path','brush path')
        raise ValueError(message) from error
    recipe=check_recipe({'version':VERSION,**{k:mapped[k] for k in ('points','axes','hardness','opacity')},
        'reference_size':[spec.width,spec.height],'solver':deepcopy(DEFAULT_REPAIR)})
    admit_memory((full_source[1],full_source[0]),recipe)
    return recipe,weight
