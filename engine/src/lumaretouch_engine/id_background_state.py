"""PC-32475 canonical ID-background intent. Numeric scales are our own.

Source-reviewed masks never transfer to another photograph. File locators are
not asset identities; immutable content belongs in the sibling project bundle.
Legacy v1/v2 records are preserved exactly by validation. Spill edits explicitly
upgrade to v2; original-shadow edits explicitly upgrade to v3. Existing derived
source recipe hashes are never silently rewritten by merely reading a record.
"""
from copy import deepcopy
import os
import re
from .local_mask_recipe import number
from . import local_mask_state as M

VERSION = 1
SPILL_VERSION = 2
ORIGINAL_SHADOW_VERSION = 3
MAX_ASSET_BYTES = 10_000_000
MAX_ASSET_PIXELS = 32_000_000
CATEGORIES = ('subject', 'contact', 'all')
# Original plain colours, not a copied/licensed stock-image collection.
PRESETS = ((255,255,255), (238,242,246), (54,126,204), (34,88,170), (197,40,49), (100,100,100))


def colour(raw):
    if type(raw) is not list or len(raw) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in raw):
        raise ValueError('背景颜色需要三个 0–255 整数 RGB 通道')
    return raw[:]


def parse_hex(raw):
    if type(raw) is not str or not re.fullmatch('#?[0-9a-fA-F]{6}', raw):
        raise ValueError('背景 HEX 需要六位 RGB 颜色')
    raw = raw.lstrip('#')
    return [int(raw[i:i+2], 16) for i in (0,2,4)]


def favourites(raw):
    if type(raw) is not list or len(raw) > 6:
        raise ValueError('最多收藏六种背景颜色')
    out = [colour(v) for v in raw]
    if len({tuple(v) for v in out}) != len(out):
        raise ValueError('背景收藏颜色重复')
    return out


def asset(raw):
    if raw is None: return None
    fields = {'path','sha256','width','height','bits','working_color','icc_sha256','pixels_sha256','alpha_sha256'}
    if (type(raw) is not dict or set(raw) != fields or type(raw['path']) is not str
            or not os.path.isabs(raw['path']) or len(raw['path']) > 4096 or '\x00' in raw['path']
            or raw['working_color'] != 'linear-srgb-f32' or type(raw['bits']) is not int or raw['bits'] not in (8,16)
            or any(type(raw[k]) is not int or raw[k] < 1 for k in ('width','height'))
            or raw['width'] * raw['height'] > MAX_ASSET_PIXELS):
        raise ValueError('背景素材尺寸、位深或颜色空间身份无效')
    for key in ('sha256','pixels_sha256','icc_sha256','alpha_sha256'):
        if key in ('icc_sha256','alpha_sha256') and raw[key] is None: continue
        if type(raw[key]) is not str or not re.fullmatch('[0-9a-f]{64}',raw[key]):
            raise ValueError('背景素材内容或 ICC 摘要无效')
    return deepcopy(raw)


def shadow_defaults():
    return {'kind':'none','blend':'normal','opacity':.35,'blur':12.,'gradient':0.,
            'x':0.,'y':0.,'distance':20.,'angle':45.,'color':[0,0,0]}


def shadow(raw):
    if (type(raw) is not dict or set(raw) != set(shadow_defaults())
            or raw['kind'] not in ('none','soft','hard','silhouette')
            or raw['blend'] not in ('normal','multiply','softlight')):
        raise ValueError('新阴影类型、混合模式或字段无效')
    limits = {'opacity':(0,1),'blur':(0,256),'gradient':(0,1),'x':(-8192,8192),
              'y':(-8192,8192),'distance':(0,8192),'angle':(-180,180)}
    return {**{k:raw[k] for k in ('kind','blend')}, 'color':colour(raw['color']),
            **{k:number(raw[k],*bounds) for k,bounds in limits.items()}}


def background(raw, *, unresolved_asset=False):
    fields = {'kind','color','asset','fit','x','y','scale'}
    if (type(raw) is not dict or set(raw) != fields or raw['kind'] not in ('none','solid','asset')
            or raw['fit'] not in ('center','stretch')):
        raise ValueError('背景类型、布局或字段无效')
    out = {'kind':raw['kind'],'color':None if raw['color'] is None else colour(raw['color']),
           'asset':asset(raw['asset']),'fit':raw['fit'],'x':number(raw['x'],-2,2),
           'y':number(raw['y'],-2,2),'scale':number(raw['scale'],.05,10)}
    if out['fit'] == 'stretch' and (out['x'] != 0 or out['y'] != 0 or out['scale'] != 1):
        raise ValueError('拉伸布局不能调整位置或大小')
    if out['kind'] == 'asset' and out['asset'] is None and not unresolved_asset:
        raise ValueError('素材背景需要已经验证的本地素材')
    if out['kind'] in ('solid','asset') and out['color'] is None:
        raise ValueError('纯色背景需要颜色选择')
    if out['kind'] == 'none' and (out['color'] is not None or out['asset'] is not None):
        raise ValueError('清除背景选择不能保留活动颜色或素材')
    return out


def empty():
    return {'version':VERSION,'enabled':False,'source':None,
            'background':{'kind':'solid','color':[255,255,255],'asset':None,'fit':'center','x':0.,'y':0.,'scale':1.},
            'support':{k:None for k in CATEGORIES},'selected_support':'subject','edge':0.,'opacity':1.,
            'shadow':shadow_defaults(),'favourites':[]}


def check(raw):
    if raw is None: return empty()
    if type(raw) is not dict: raise ValueError('证件照背景配方必须是对象')
    version = raw.get('version')
    fields = set(empty()) | ({'spill'} if version in (SPILL_VERSION, ORIGINAL_SHADOW_VERSION) else set())
    if version == ORIGINAL_SHADOW_VERSION: fields.add('original_shadow')
    if (set(raw) != fields or type(version) is not int
            or version not in (VERSION, SPILL_VERSION, ORIGINAL_SHADOW_VERSION) or type(raw['enabled']) is not bool
            or type(raw['support']) is not dict or set(raw['support']) != set(CATEGORIES)
            or raw['selected_support'] not in CATEGORIES):
        raise ValueError('证件照背景配方版本、保留范围或字段无效')
    source = M.check({'recipe':M.empty()['recipe'],'source':raw['source'],'semantic_owner':None})['source']
    from .id_background_support import check_binding
    support = {k:check_binding(raw['support'][k],k) if raw['support'][k] is not None else None for k in CATEGORIES}
    if any(v is not None and v['mask']['source'] != source for v in support.values()):
        raise ValueError('独立审核的背景保留范围必须绑定同一原照片')
    out = {'version':version,'enabled':raw['enabled'],'source':source,'background':background(raw['background']),
           'support':support,'selected_support':raw['selected_support'],'edge':number(raw['edge'],-20,20),
           'opacity':number(raw['opacity'],0,1),'shadow':shadow(raw['shadow']),'favourites':favourites(raw['favourites'])}
    if version in (SPILL_VERSION, ORIGINAL_SHADOW_VERSION):
        from . import spill_removal_state as SP
        out['spill'] = SP.check(raw['spill'])
        coverage = out['spill']['coverage']
        if coverage is not None and coverage['mask']['source'] != source:
            raise ValueError('祛染色手工覆盖度与证件照背景必须属于同一有效源图')
    if version == ORIGINAL_SHADOW_VERSION:
        from . import original_shadow_state as OS
        intent = out['original_shadow'] = OS.check(raw['original_shadow'])
        if any(intent[key] is not None and intent[key]['mask']['source'] != source
               for key in ('lit_floor', 'retention')):
            raise ValueError('原阴影的明亮地面与保留范围必须绑定同一有效源图')
        if OS.active(intent):
            if out['selected_support'] != 'subject':
                raise ValueError('原阴影需要独立审核的主体范围；不能重复保留接触地面或原背景')
            subject = support['subject']
            if subject is None or any(obj['kind'] not in OS.KINDS for obj in subject['mask']['recipe']['objects']):
                raise ValueError('原阴影需要完整源图手工矢量主体范围；不能放大提示模型代理 alpha 作为源图证据')
            if out['shadow']['kind'] != 'none' and out['shadow']['opacity'] > 0:
                raise ValueError('原阴影提取与新投影阴影不能同时启用，避免重复阴影')
    if out['enabled'] and (source is None or support[out['selected_support']] is None or out['background']['kind'] == 'none'):
        raise ValueError('请先选择背景，并审核绑定原照片的保留范围')
    return deepcopy(out)


def spill_of(raw):
    """Read old recipes as neutral without rewriting old saved hash content."""
    from . import spill_removal_state as SP
    value = check(raw)
    return deepcopy(value['spill']) if value['version'] in (SPILL_VERSION, ORIGINAL_SHADOW_VERSION) else SP.neutral()


def with_spill(raw, spill):
    """Explicit spill edits introduce v2, without downgrading a v3 sibling."""
    from . import spill_removal_state as SP
    value = check(raw)
    value.update(version=max(value['version'], SPILL_VERSION), spill=SP.check(spill))
    return check(value)


def original_shadow_of(raw):
    """Legacy v1/v2 remain byte-for-byte canonical, without implicit upgrade."""
    from . import original_shadow_state as OS
    value = check(raw)
    return deepcopy(value['original_shadow']) if value['version'] == ORIGINAL_SHADOW_VERSION else OS.neutral()


def with_original_shadow(raw, original_shadow):
    """Only an explicit photographed-shadow edit introduces the v3 sibling."""
    from . import original_shadow_state as OS
    value = check(raw)
    value.update(spill=spill_of(value), original_shadow=OS.check(original_shadow),
                 version=ORIGINAL_SHADOW_VERSION)
    return check(value)


def active(raw):
    value = check(raw)
    return value['enabled'] and value['opacity'] > 0


def check_saved_record(raw):
    if type(raw) is not dict: raise ValueError('保存的证件照背景配方不能缺失或为 null')
    return check(raw)


def portable(raw):
    value = check(raw)
    out = {k:deepcopy(value[k]) for k in ('version','enabled','background','selected_support','edge','opacity','shadow','favourites')}
    out['requires_target_asset'] = out['background']['kind'] == 'asset'
    out['background']['asset'] = None
    if value['version'] in (SPILL_VERSION, ORIGINAL_SHADOW_VERSION):
        from . import spill_removal_state as SP
        out['spill'] = SP.portable(value['spill'])
    if value['version'] == ORIGINAL_SHADOW_VERSION:
        from . import original_shadow_state as OS
        out['original_shadow'] = OS.portable(value['original_shadow'])
    return check_portable(out)


def check_portable(raw):
    fields = {'version','enabled','background','selected_support','edge','opacity','shadow','favourites','requires_target_asset'}
    if type(raw) is not dict: raise ValueError('证件照背景预设必须是对象')
    version = raw.get('version')
    if version in (SPILL_VERSION, ORIGINAL_SHADOW_VERSION): fields.add('spill')
    if version == ORIGINAL_SHADOW_VERSION: fields.add('original_shadow')
    if (set(raw) != fields or type(version) is not int or version not in (VERSION, SPILL_VERSION, ORIGINAL_SHADOW_VERSION)
            or type(raw['enabled']) is not bool or type(raw['requires_target_asset']) is not bool
            or raw['selected_support'] not in CATEGORIES):
        raise ValueError('证件照背景预设字段不兼容')
    bg = background(raw['background'],unresolved_asset=True)
    if bg['asset'] is not None or raw['requires_target_asset'] != (bg['kind'] == 'asset'):
        raise ValueError('背景预设只使用目标照片自己的素材，不携带其他照片素材身份')
    if raw['enabled'] and bg['kind'] == 'none':
        raise ValueError('未选择背景的预设不能启用')
    out = {'version':version,'enabled':raw['enabled'],'background':bg,'selected_support':raw['selected_support'],
            'edge':number(raw['edge'],-20,20),'opacity':number(raw['opacity'],0,1),'shadow':shadow(raw['shadow']),
            'favourites':favourites(raw['favourites']),'requires_target_asset':raw['requires_target_asset']}
    if version in (SPILL_VERSION, ORIGINAL_SHADOW_VERSION):
        from . import spill_removal_state as SP
        out['spill'] = SP.check_portable(raw['spill'])
    if version == ORIGINAL_SHADOW_VERSION:
        from . import original_shadow_state as OS
        out['original_shadow'] = OS.check_portable(raw['original_shadow'])
    return out


def apply_portable(target,raw):
    proposal = check_portable(raw); out = check(target)
    from . import original_shadow_state as OS
    retained_original_shadow = original_shadow_of(out)
    # No cross-target visual review exists for a photographed shadow. Even a
    # neutral source preset cannot disable or change its target-owned sibling.
    if retained_original_shadow != OS.neutral():
        raise ValueError('目标保留原阴影审核意图；完整背景预设不能绕过目标独立审核')
    retained_asset = out['background']['asset']
    # A legacy preset disables spill, but never destroys target-owned vectors.
    # Once v2 intent exists, keep it versioned even when the new source preset
    # was v1. A v1 target remains v1 when both sides lack spill intent.
    target_version = out['version']
    retained_spill = spill_of(out)
    out.update({k:deepcopy(v) for k,v in proposal.items() if k not in ('requires_target_asset', 'spill', 'original_shadow')})
    if max(proposal['version'], target_version) >= SPILL_VERSION:
        from . import spill_removal_state as SP
        params = proposal.get('spill', SP.portable(SP.neutral()))
        out['version'] = max(proposal['version'], target_version)
        out['spill'] = SP.apply_portable(retained_spill, params)
    if out['version'] == ORIGINAL_SHADOW_VERSION:
        out['original_shadow'] = retained_original_shadow
    if proposal['requires_target_asset']:
        if retained_asset is None:
            raise ValueError('素材背景预设要求目标照片先选择自己的素材；不会复制另一照片素材')
        out['background']['asset'] = retained_asset
    # Source, independent reviews and manual spill coverage remain target-owned.
    return check(out)


def clear_choice(raw):
    out = check(raw); out['enabled'] = False
    out['background'] = {'kind':'none','color':None,'asset':None,'fit':'center','x':0.,'y':0.,'scale':1.}
    return check(out)
