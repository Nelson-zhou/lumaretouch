"""Pure, atomic creative document commands; no renderer or second history owner.

Layer arrays are bottom-to-top within each parent. Groups are isolated and have
identity geometry; image transforms map source coordinates to canvas coordinates.
Deletion is recoverable through the host's unified snapshot history, never by
removing immutable source bytes. Safety limits are not vendor parameter claims.
"""
from __future__ import annotations
from copy import deepcopy
import math
import uuid
from .creative_document_assets import MAX_PIXELS, dimension

BLENDS = ('normal','multiply','screen','lighten','darken')
MAX_LAYERS = 1024
MAX_DEPTH = 32
TRANSFORM = {'x':0.0,'y':0.0,'scale_x':1.0,'scale_y':1.0,'rotation':0.0,'flip_x':False,'flip_y':False}
ROOT_KEYS = {'schema','document_id','source_uid','source_asset','revision','canvas','selected_id','layers'}
LAYER_KEYS = {'id','kind','name','parent_id','asset_id','visible','locked','opacity','blend','mask_id','transform'}


def _text(value, maximum=256):
    if type(value) is not str or not value.strip() or len(value) > maximum or '\x00' in value:
        raise ValueError('Invalid creative name or identity')
    return value


def _number(value, lower, upper):
    if type(value) not in (int,float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('Creative numeric value outside finite safety bounds')
    return value


def _transform(t):
    if type(t) is not dict or set(t) != set(TRANSFORM):
        raise ValueError('Malformed creative transform')
    for k in ('x','y'): _number(t[k], -1e9, 1e9)
    for k in ('scale_x','scale_y'): _number(t[k], 1e-6, 1e4)
    _number(t['rotation'], -360000, 360000)
    if any(type(t[k]) is not bool for k in ('flip_x','flip_y')):
        raise ValueError('Invalid creative flip')


def validate(document, assets):
    if type(document) is not dict or set(document) != ROOT_KEYS or type(document['schema']) is not int or document['schema'] != 1:
        raise ValueError('Malformed or unsupported creative document')
    for k in ('document_id','source_uid','source_asset'): _text(document[k])
    assets.get(document['source_asset'], 'rgba')
    if type(document['revision']) is not int or not 0 <= document['revision'] < 2**53:
        raise ValueError('Invalid creative revision')
    c = document['canvas']
    if type(c) is not dict or set(c) != {'width','height','dpi'}:
        raise ValueError('Malformed creative canvas')
    if dimension(c['width']) * dimension(c['height']) > MAX_PIXELS:
        raise ValueError('Creative canvas pixel budget exceeded')
    _number(c['dpi'], 1e-6, 1e6)
    layers = document['layers']
    if type(layers) is not list or len(layers) > MAX_LAYERS:
        raise ValueError('Creative layer budget exceeded')
    ids = {}
    for layer in layers:
        if type(layer) is not dict or set(layer) != LAYER_KEYS:
            raise ValueError('Malformed creative layer')
        identity = _text(layer['id'])
        if identity in ids: raise ValueError('Duplicate creative layer identity')
        ids[identity] = layer
        _text(layer['name'])
        if layer['kind'] not in ('image','group') or layer['blend'] not in BLENDS:
            raise ValueError('Unsupported creative layer or blend')
        if any(type(layer[k]) is not bool for k in ('visible','locked')):
            raise ValueError('Invalid creative layer flag')
        _number(layer['opacity'], 0, 1)
        _transform(layer['transform'])
        if layer['kind'] == 'image':
            image = assets.get(layer['asset_id'], 'rgba')
        elif layer['asset_id'] is not None or layer['transform'] != TRANSFORM:
            raise ValueError('Group assets/transforms are unsupported, not ignored')
        if layer['mask_id'] is not None:
            mask = assets.get(layer['mask_id'], 'mask')
            if layer['kind'] == 'image' and (mask['width'],mask['height']) != (image['width'],image['height']):
                raise ValueError('Image mask must match source image dimensions')
    for layer in layers:
        parent = layer['parent_id']; seen = {layer['id']}
        while parent is not None:
            if parent in seen or parent not in ids or ids[parent]['kind'] != 'group':
                raise ValueError('Cyclic or missing creative group parent')
            seen.add(parent)
            if len(seen) > MAX_DEPTH: raise ValueError('Creative group depth budget exceeded')
            parent = ids[parent]['parent_id']
    if document['selected_id'] is not None and document['selected_id'] not in ids:
        raise ValueError('Missing selected creative layer')
    return document


def _layer(kind, name, asset_id=None, parent_id=None):
    return {'id':uuid.uuid4().hex,'kind':kind,'name':name,'parent_id':parent_id,
            'asset_id':asset_id,'visible':True,'locked':False,'opacity':1.0,
            'blend':'normal','mask_id':None,'transform':deepcopy(TRANSFORM)}


def create(source_uid, source_asset, assets, *, document_id=None, dpi=72.0):
    source = assets.get(source_asset, 'rgba')
    base = _layer('image','基础图',source_asset)
    document = {'schema':1,'document_id':document_id or uuid.uuid4().hex,
                'source_uid':source_uid,'source_asset':source_asset,'revision':0,
                'canvas':{'width':source['width'],'height':source['height'],'dpi':dpi},
                'selected_id':base['id'],'layers':[base]}
    return validate(document,assets)


def references(document):
    result = {document['source_asset']}
    for layer in document['layers']:
        result.update(x for x in (layer['asset_id'],layer['mask_id']) if x is not None)
    return result


def affine(transform, width=0, height=0):
    """Forward (a,b,c,d,e,f), scale followed by center flip/rotation.

    x/y locate the unrotated scaled rectangle. Flip and rotation retain its
    center, avoiding the off-canvas jump caused by flipping about the origin.
    No destructive resampling until tile rendering/export.
    """
    t = transform; angle = math.radians(t['rotation'])
    cs, sn = math.cos(angle), math.sin(angle)
    sx = t['scale_x'] * (-1 if t['flip_x'] else 1)
    sy = t['scale_y'] * (-1 if t['flip_y'] else 1)
    a,b,d,e = cs*sx,-sn*sy,sn*sx,cs*sy
    c = t['x'] + width*t['scale_x']/2 - (a*width+b*height)/2
    f = t['y'] + height*t['scale_y']/2 - (d*width+e*height)/2
    return (a,b,c,d,e,f)


def inverse(transform, width=0, height=0):
    a,b,c,d,e,f = affine(transform,width,height); determinant = a*e-b*d
    return (e/determinant,-b/determinant,(b*f-e*c)/determinant,
            -d/determinant,a/determinant,(d*c-a*f)/determinant)


def bounds(layer, assets):
    source = assets.get(layer['asset_id'],'rgba'); a,b,c,d,e,f = affine(layer['transform'],source['width'],source['height'])
    points = [(a*x+b*y+c,d*x+e*y+f) for x,y in
              ((0,0),(source['width'],0),(0,source['height']),(source['width'],source['height']))]
    return min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)


_FIELDS = {
    'select':{'layer_id'}, 'rename':{'layer_id','name'}, 'duplicate':{'layer_id'},
    'delete':{'layer_id'}, 'lock':{'layer_id','locked'}, 'visibility':{'layer_id','visible'},
    'opacity':{'layer_id','opacity'}, 'blend':{'layer_id','blend'},
    'transform':{'layer_id','transform'}, 'align':{'layer_id','alignment'},
    'canvas':{'width','height','dpi'}, 'add_image':{'asset_id','name','parent_id'},
    'group':{'name','layer_ids'}, 'ungroup':{'layer_id'},
    'move':{'layer_id','parent_id','index'}, 'add_mask':{'layer_id','mask_id'},
    'remove_mask':{'layer_id'},
}


def apply(document, command, assets):
    """Return privately owned next state, never mutate input on failure or no-op.

    Caller must capture and commit unified history once. Expected revision and
    pending ownership are checked by the controller before entering this function.
    """
    validate(document,assets)
    if type(command) is not dict or command.get('action') not in _FIELDS:
        raise ValueError('Unknown creative action')
    action = command['action']
    if set(command)-({'action'}|_FIELDS[action]): raise ValueError('Unknown creative command field')
    out = deepcopy(document); layers = out['layers']; by_id = {x['id']:x for x in layers}
    def find(identity):
        if identity not in by_id: raise ValueError('No creative layer selected')
        return by_id[identity]
    def unlocked(layer, *, own=True):
        current = layer if own else by_id.get(layer['parent_id'])
        while current is not None:
            if current['locked']: raise ValueError('Creative layer or ancestor is locked')
            current = by_id.get(current['parent_id'])
    def subtree(identity):
        wanted = {identity}
        for _ in range(MAX_DEPTH):
            more = {x['id'] for x in layers if x['parent_id'] in wanted}
            if more <= wanted: break
            wanted |= more
        return wanted
    if action == 'select':
        identity = command['layer_id']
        if identity is not None: find(identity)
        out['selected_id'] = identity
    elif action == 'canvas':
        if out['selected_id'] is not None: raise ValueError('Deselect layer before canvas editing')
        for key in ('width','height','dpi'):
            if key in command: out['canvas'][key] = command[key]
    elif action == 'add_image':
        asset = assets.get(command['asset_id'],'rgba')
        parent_id = command.get('parent_id')
        if parent_id is not None:
            parent = find(parent_id); unlocked(parent)
            if parent['kind'] != 'group': raise ValueError('Image parent must be a group')
        layer = _layer('image',command.get('name','导入图层'),asset['id'],parent_id)
        layers.append(layer); out['selected_id'] = layer['id']
    elif action == 'group':
        identities = command.get('layer_ids',[])
        if type(identities) is not list or len(set(identities)) != len(identities):
            raise ValueError('Invalid creative group selection')
        chosen = [find(x) for x in identities]
        for layer in chosen: unlocked(layer)
        parents = {x['parent_id'] for x in chosen}
        if len(parents) > 1: raise ValueError('Group selection must share a parent')
        parent_id = chosen[0]['parent_id'] if chosen else None
        # Only contiguous siblings can be grouped without silently changing visual order.
        siblings = [x for x in layers if x['parent_id'] == parent_id]
        positions = sorted(siblings.index(x) for x in chosen)
        if positions and positions != list(range(positions[0],positions[-1]+1)):
            raise ValueError('Only contiguous sibling layers can be grouped')
        group = _layer('group',command.get('name','图层组'),parent_id=parent_id)
        insertion = min((layers.index(x) for x in chosen), default=len(layers))
        layers.insert(insertion,group)
        for layer in chosen: layer['parent_id'] = group['id']
        out['selected_id'] = group['id']
    else:
        layer = find(command.get('layer_id',out['selected_id']))
        unlocked(layer,own=action != 'lock')
        if action == 'rename': layer['name'] = command['name']
        elif action == 'lock': layer['locked'] = command['locked']
        elif action == 'visibility': layer['visible'] = command['visible']
        elif action == 'opacity': layer['opacity'] = command['opacity']
        elif action == 'blend': layer['blend'] = command['blend']
        elif action == 'transform':
            if layer['kind'] != 'image' or type(command['transform']) is not dict:
                raise ValueError('Transforms require an image layer')
            if set(command['transform'])-set(TRANSFORM): raise ValueError('Unknown transform field')
            layer['transform'].update(command['transform'])
        elif action == 'align':
            if layer['kind'] != 'image': raise ValueError('Alignment requires an image layer')
            l,t,r,b = bounds(layer,assets); canvas = out['canvas']; alignment = command['alignment']
            if alignment == 'left': layer['transform']['x'] -= l
            elif alignment == 'hcenter': layer['transform']['x'] += (canvas['width']-l-r)/2
            elif alignment == 'right': layer['transform']['x'] += canvas['width']-r
            elif alignment == 'top': layer['transform']['y'] -= t
            elif alignment == 'vcenter': layer['transform']['y'] += (canvas['height']-t-b)/2
            elif alignment == 'bottom': layer['transform']['y'] += canvas['height']-b
            else: raise ValueError('Unknown creative alignment')
        elif action == 'add_mask':
            if layer['mask_id'] is not None: raise ValueError('Layer already has a mask')
            assets.get(command['mask_id'],'mask'); layer['mask_id'] = command['mask_id']
        elif action == 'remove_mask':
            if layer['mask_id'] is None: raise ValueError('Layer has no mask')
            layer['mask_id'] = None
        elif action == 'delete':
            removed = subtree(layer['id'])
            for child in layers:
                if child['id'] in removed: unlocked(child)
            out['layers'] = [x for x in layers if x['id'] not in removed]
            if out['selected_id'] in removed: out['selected_id'] = None
        elif action == 'duplicate':
            chosen = subtree(layer['id']); originals = [layer] + [x for x in layers if x['id'] in chosen and x is not layer]
            remap = {x['id']:uuid.uuid4().hex for x in originals}
            copies = deepcopy(originals)
            for copy in copies:
                copy['id'] = remap[copy['id']]
                copy['parent_id'] = remap.get(copy['parent_id'],copy['parent_id'])
            next(x for x in copies if x['id'] == remap[layer['id']])['name'] += ' 副本'
            insertion = layers.index(layer)+1
            layers[insertion:insertion] = copies; out['selected_id'] = remap[layer['id']]
        elif action == 'move':
            parent_id = command['parent_id']; index = command['index']
            if parent_id is not None:
                parent = find(parent_id); unlocked(parent)
                if parent['kind'] != 'group' or parent_id in subtree(layer['id']):
                    raise ValueError('Invalid creative group destination')
            siblings = [x for x in layers if x['parent_id'] == parent_id and x is not layer]
            if type(index) is not int or not 0 <= index <= len(siblings):
                raise ValueError('Invalid creative sibling index')
            layers.remove(layer); layer['parent_id'] = parent_id
            insertion = layers.index(siblings[index]) if index < len(siblings) else (layers.index(siblings[-1])+1 if siblings else len(layers))
            layers.insert(insertion,layer)
        elif action == 'ungroup':
            if layer['kind'] != 'group': raise ValueError('Selected layer is not a group')
            if layer['mask_id'] is not None or layer['opacity'] != 1 or layer['blend'] != 'normal' or not layer['visible']:
                raise ValueError('Ungroup would discard group appearance; reset group properties first')
            children = [x for x in layers if x['parent_id'] == layer['id']]
            if any(x['blend'] != 'normal' for x in children):
                raise ValueError('Ungroup would change isolated child blending')
            for child in children: unlocked(child)
            insertion = layers.index(layer)
            for child in children: layers.remove(child); child['parent_id'] = layer['parent_id']
            layers.remove(layer); layers[insertion:insertion] = children
            out['selected_id'] = children[-1]['id'] if children else None
    validate(out,assets)
    if out == document: return out
    out['revision'] += 1
    return validate(out,assets)
