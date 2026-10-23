"""Additive v22 recipe validation, including nested history and immutable bytes.

Old projects with no ID-background key remain unchanged. Present malformed
records fail closed. Background images are bundled; path is only a locator.
"""
import base64
import hashlib
from . import id_background_state as S, id_background_assets as A


def _bundle(raw, assets):
    if type(raw) is not dict or set(raw)!={'binding','content'} or type(raw['content']) is not list:
        raise ValueError('证件照背景项目素材记录缺失或格式无效')
    chunks=[]
    for chunk in raw['content']:
        if isinstance(chunk,bytes):chunks.append(chunk);continue
        if type(chunk) is not dict or set(chunk) not in ({'__asset__'},{'__asset__','at'}) or assets is None:
            raise ValueError('证件照背景项目素材块缺失')
        identity=chunk['__asset__'];asset=assets.get(identity)
        if type(asset) is not dict or asset.get('kind')!='bytes':raise ValueError('证件照背景素材块类型错误')
        data=base64.b64decode(asset['b64'],validate=True)
        if len(data)!=asset['bytes'] or identity!='sha256:'+hashlib.sha256(data).hexdigest():
            raise ValueError('证件照背景项目素材块摘要不匹配')
        chunks.append(data)
    return A.check_bundle({'binding':raw['binding'],'content':chunks})


def validate_records(value,assets=None):
    if isinstance(value,dict):
        if "_bg" in value:
            from .common_background_source import check as check_common
            check_common(value["_bg"])
        if '_effect_recovery' in value or 'effect_recovery' in value:
            from .id_background_recovery import validate_state
            from .effect_recovery_state import check
            if ('_effect_recovery' in value and 'effect_recovery' in value
                    and check(value['_effect_recovery']) != check(value['effect_recovery'])):
                raise ValueError('Conflicting saved ID recovery state aliases')
            validate_state(value,value.get('_effect_recovery',value.get('effect_recovery')))
        if '_id_background' in value:
            if value['_id_background'] is None:raise ValueError('已保存的证件照背景配方不能为 null')
            recipe=S.check(value['_id_background']);raw=value.get('_id_background_bundle')
            bundle=_bundle(raw,assets) if raw is not None else None
            if recipe['background']['kind']=='asset':
                if bundle is None or bundle['binding']!=recipe['background']['asset']:
                    raise ValueError('证件照背景项目缺少匹配的原始素材字节')
        for child in value.values():validate_records(child,assets)
    elif isinstance(value,list):
        for child in value:validate_records(child,assets)
