"""Fail-closed native/derived export contract for reviewed ID background recipes."""
from . import id_background_state as S, id_background_assets as A


def check_spec(spec):
    value=S.check(spec.id_background);spec.id_background=value
    if value['background']['kind']=='asset':
        bundle=A.check_bundle(spec.id_background_bundle)
        if bundle is None or bundle['binding']!=value['background']['asset']:
            raise ValueError('证件照背景素材与保留配方身份不匹配')
    if getattr(spec,"creative_base",None) is not None or getattr(spec,"creative_id_background_context",None) is not None:
        from .creative_derived_id_background import verify_snapshot
        verify_snapshot({"creative_base":getattr(spec,"creative_base",None),"id_background":value,
            "id_background_bundle":spec.id_background_bundle,
            "creative_id_background_context":getattr(spec,"creative_id_background_context",None)},
            path=getattr(spec,"id_background_path",None))
    if not S.active(value):return
    from .studio_background_state import active as studio_active
    from .sky_replacement_state import check as sky_check
    if spec.bg_matte is not None or studio_active(spec.studio_background) or sky_check(spec.sky_replacement)['enabled']:
        raise ValueError('证件照换背景与旧换底、换天空和影棚背景调整不能同时启用')
    import os
    if (type(spec.id_background_path) is not str or not os.path.isabs(spec.id_background_path) or '\x00' in spec.id_background_path
            or type(spec.id_background_stamp) is not list or len(spec.id_background_stamp)!=5
            or any(type(v) is not int or v<0 for v in spec.id_background_stamp)):
        raise ValueError('证件照背景导出缺少已验证的原图路径与解码时间戳')
    source=value['source']
    if source['width']*source['height']>32_000_000:
        raise ValueError('证件照背景完整源域超过 32MP 预算；不会放大代理蒙版代替')


def admit_prepare(spec,shape,*,tile,bits):
    """Reserve full native support, asset decoding and output before allocation."""
    check_spec(spec)
    if not S.active(spec.id_background):return 0
    from .cpu_memory_budget import available_estimate
    h,w=shape;pixels=h*w
    asset=spec.id_background['background']['asset']
    asset_pixels=asset['width']*asset['height'] if spec.id_background['background']['kind']=='asset' else 0
    # Native's exact source-plus-shadow-halo estimate excludes the pipeline. Source is
    # already resident; reserve output and one conservative full-halo tile too.
    tile_pixels=min(h,int(tile)+512)*min(w,int(tile)+512)
    from .id_background_native import memory_estimate
    reserve=memory_estimate((h,w),spec.id_background)+asset_pixels*48+pixels*12*int(spec.scale)**2+tile_pixels*768+128*1024**2
    if reserve>available_estimate():
        raise ValueError('证件照背景完整原尺寸场、素材及输出超过可用内存；请减小瓦片或释放内存，不会放大代理蒙版')
    return reserve
