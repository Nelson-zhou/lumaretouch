"""Portable custom filter module for existing transactional preset/batch pathways."""
from .custom_lut_asset import CustomCube
from .ops.lut import check_amount
OP='lnx.custom_lut.v1'
FIELDS=('_lut','_lut_amount','_lut_preset')
def check_params(raw):
    if not isinstance(raw,dict) or set(raw)!={'asset','amount'}:raise ValueError('自定义 LUT 预设字段无效')
    amount=check_amount(raw['amount']);asset=raw['asset']
    if asset is not None:
        if isinstance(asset,dict) and set(asset)=={'sha256','name'}:
            from .custom_lut_library import digest_id,display_name
            asset={'sha256':digest_id(asset['sha256']),'name':display_name(asset['name'])}
        else: asset=CustomCube.restore(asset).portable()
    return {'asset':asset,'amount':amount}
def params_of(state):
    from .custom_lut_library import default_library
    cube=state.get('_lut');asset=None
    if isinstance(cube,CustomCube):
        lib=default_library()
        if not lib.contains(cube.asset_id):lib.import_bytes(cube.content,cube.title)
        asset={'sha256':cube.asset_id,'name':cube.title}
    return {'asset':asset,'amount':float(state.get('_lut_amount',1.))}
def portable(params):
    from .custom_lut_library import default_library
    clean=check_params(params)
    if clean['asset'] is not None and 'cube_base64' not in clean['asset']:
        clean['asset']=default_library().portable(clean['asset']['sha256'])
    return clean

def install(state,params):
    from .custom_lut_library import default_library
    clean=check_params(params);asset=clean['asset'];cube=None
    if asset is not None:
        cube=CustomCube.restore(asset) if 'cube_base64' in asset else CustomCube(default_library().content(asset['sha256']),asset['sha256'],asset['name'])
    if cube is not None or isinstance(state.get('_lut'),CustomCube):
        state.update(_lut=cube,_lut_amount=clean['amount'],_lut_preset=None)
def public_view(value):
    """Protocol summaries omit LUT bytes; project/preset files keep verified bytes.

    Clients never submit these read-only summaries as a recipe; apply uses preset
    identity or batch preflight token, with authoritative full assets held in engine.
    """
    if isinstance(value,dict):
        if set(value)=={'version','source_sha256','filename','source_base64','selected','report'}:
            from .xmp_adaptation import public
            return public(value)
        if set(value)=={'schema','sha256','name','cube_base64'} and value.get('schema')==1 and isinstance(value.get('cube_base64'),str):
            return {'schema':1,'sha256':value['sha256'],'name':value['name'],'embedded_base64_bytes':len(value['cube_base64']),'read_only_summary':True}
        return {k:public_view(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [public_view(v) for v in value]
    return value
