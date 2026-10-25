# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit v2 manual-plane candidate; v1 math and saved recipe stay separate."""
import hashlib
import struct
import uuid
from . import lens_blur_stage as S
from . import lens_cohort_native as native
from . import lens_cohort_refinement as refinement

MATH_IDENTITY = 'cohort-fft-f64-v2-00020001'


def prepare_validated(command, source, depth, settings, *, budget, cancelled):
    """Called only after the common stage freezes and validates the exact command."""
    S._require_source(source)
    asset_depth = S._require_depth(depth, source, command['session_id'])
    if (command['recipe']['version'] != 2 or command['recipe']['math_identity'] != MATH_IDENTITY
            or asset_depth['provenance']['method'] != 'user_defined_plane' or depth.session_id is None):
        raise ValueError('V2 rendering requires an explicitly acknowledged source-owned constant plane')
    # Verify actual retained raster, not only its method label.
    S._depth_wire(asset_depth, source, manual_plane=True)
    width, height = source.owner['source']['width'], source.owner['source']['height']
    manual = struct.unpack_from('<H', depth.raster_bytes)[0] / 65535.0
    manual_f32 = struct.unpack('<f', struct.pack('<f', manual))[0]
    brush = refinement.estimate(command['recipe']['refinements'], width, height)
    if type(budget) is not S.Budget or brush['pixels_examined'] > budget.max_refinement_pixels:
        raise MemoryError('V2 source brush scan budget exceeded; no vectors or feather pixels omitted')
    retained_other = source.retained_bytes-len(source.content)+depth.retained_bytes
    reserve = S.DISPLAY_RESERVE+32*1024*1024
    with S._job(budget, cancelled) as poll:
        S._admit(source.retained_bytes+depth.retained_bytes+brush['peak_bytes']+reserve, budget)
        correction = refinement.rasterize(command['recipe']['refinements'], width, height,
            max_bytes=brush['peak_bytes'], max_pixels_examined=budget.max_refinement_pixels, cancelled=poll)
        limits = native.default_budgets(width, height)
        limits['max_direct_pairs'] = min(limits['max_direct_pairs'], budget.max_candidate_taps)
        limits['reserved_repair_pairs'] = min(limits['reserved_repair_pairs'], limits['max_direct_pairs'])
        result = native.render(source.content, width, height, settings,
            manual_depth=manual_f32, manual_depth_acknowledged=True,
            refinement=correction, budgets=limits, max_live_bytes=budget.max_bytes-retained_other-reserve,
            cancelled=poll)
        if result.abi != 2 or result.math_identity != 0x00020001:
            raise ValueError('V2 candidate returned a different renderer identity')
        correction_hash = None if correction is None else S._hash(correction)
        del correction
        poll()
        content = result.rgba
        no_change = content == source.content
        from .creative_document_assets import make_asset
        asset = source.asset if no_change else make_asset('rgba', width, height, content,
                                                         original=source.original, icc=source.icc)
        after_png, dw, dh = ((source.png, source.display_width, source.display_height) if no_change
                            else S._display_png(content, width, height, poll))
        before, after = source.source_image, S._png_record(after_png, dw, dh)
        recipe_hash = S._hash(b'lrt-lens-recipe-v2\0'+S._json(command['recipe']))
        token = S._hash(b'lrt-lens-candidate-v2\0'+uuid.uuid4().bytes+S._json({
            'session_id': command['session_id'], 'owner': source.owner, 'recipe_sha256': recipe_hash,
            'output_asset_id': asset['id'], 'before_sha256': before['sha256'], 'after_sha256': after['sha256']}))
        plan = result.plan
        review = {'version': S.WIRE_PROTOCOL, 'request_id': command['request_id'],
            'session_id': command['session_id'], 'token': token, 'owner': source.owner,
            'recipe': command['recipe'], 'recipe_sha256': recipe_hash,
            'result_source_sha256': asset['id'][7:], 'before': before, 'after': after, 'notes': [
                '显式 v2 光圈求和路径；不是旧版逐点求和的逐位重放，未修改原文档。',
                '真实完整来源与完整输出，不以显示采样代替最终像素；对比 PNG 仅为 SDR 显示。',
                '人工恒定基准面，不是测量或 AI 景深；只接收不透明 SDR。',
                '羽化残差全部计算或明确拒绝，不量化半径、不省略笔画、不缩小结果。',
                '规划 FFT 蝶形次数 '+str(plan['fft_butterflies'])+'；残差候选对 '+str(plan['residual_candidate_pairs'])+'。这是静态工作计数，不是耗时或质量验收。']}
        # Same conceptual full f32 plane identity without a full-sized depth allocation.
        depth_hash = hashlib.sha256()
        block = struct.pack('<f', manual_f32)*65536
        remaining = width*height
        while remaining:
            poll(); count = min(remaining, 65536)
            depth_hash.update(block if count == 65536 else block[:count*4]); remaining -= count
        header, content, original, icc = S._asset_parts(asset)
        poll()
        return S.Candidate(S._json(review), header, content, original, icc, no_change,
                           correction_hash, depth_hash.hexdigest(), S._SEAL)
