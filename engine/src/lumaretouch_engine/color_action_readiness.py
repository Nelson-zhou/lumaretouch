"""An action sample may reuse current rendering caches, never start cold filters.

The serial action owner must keep the recipe fixed from this check through retouch.
This avoids unbounded-by-projection-plan integral-image work inside an eyedropper.
"""
from .ops.guided import (DEFAULT_RADIUS, DEFAULT_EPS, DEFAULT_DETAIL_GAIN,
                         DEFAULT_MID_GAIN, DEFAULT_BROAD_GAIN, DEFAULT_TEXTURE_RADIUS)


def require_warm_prefix(pipeline, strength, params):
    r,e,rf,g,mg,bg = pipeline._filter_parameters(
        params.get('radius',DEFAULT_RADIUS),params.get('eps',DEFAULT_EPS),
        params.get('detail_gain',DEFAULT_DETAIL_GAIN),params.get('mid_gain',DEFAULT_MID_GAIN),
        params.get('broad_gain',DEFAULT_BROAD_GAIN),params.get('texture_radius',DEFAULT_TEXTURE_RADIUS))
    if strength != 0:
        key = (r,e,rf,bg,mg,g,pipeline.repair_version)
        if pipeline.retouched is None or pipeline.filter_key != key:
            raise ValueError('Wait for the current photo preview before using the WB picker (filter cache)')
    if pipeline.has_light():
        suffix=(pipeline.light_version,float(pipeline.light_exposure),int(pipeline.light_radius))
        if pipeline.light_src is None or pipeline.light_src_key != (pipeline.repair_version,*suffix):
            raise ValueError('Wait for the current photo preview before using the WB picker (source light cache)')
        if strength != 0 and (pipeline.light_res is None or pipeline.light_res_key != (pipeline.filter_key,*suffix)):
            raise ValueError('Wait for the current photo preview before using the WB picker (filtered light cache)')
    from .brow_shape_runtime import has_brow
    if pipeline.has_deform() or has_brow(pipeline):
        key=(pipeline.deform_version,tuple(sorted(pipeline.deform_amounts.items())),pipeline.high_precision_warp)
        if has_brow(pipeline): key += (pipeline.brow_shape_version,)
        if pipeline._deform_warp_key != key:
            raise ValueError('Wait for the current photo preview before using the WB picker (deformation cache)')
