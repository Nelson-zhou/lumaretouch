# SPDX-License-Identifier: GPL-3.0-or-later
"""Honest early bounds for the current full-grid aperture path, not a fallback."""

def source_admission(asset, budget, *, display_reserve, renderers=('direct-v1',), retained_limit=None):
    width,height=asset['width'],asset['height']
    pixels=width*height
    if retained_limit is not None and (2*len(asset['content'])+len(asset['original'])+len(asset['icc'])+32*1024*1024 > retained_limit):
        raise MemoryError('完整来源与实际新候选的保留数据超出会话预算；不会开始无法保留结果的涂抹')
    if 'cohort-fft-v2' in renderers:
        from .lens_cohort_native import memory_estimate
        plan = memory_estimate(width, height)
        retained_other = len(asset['original'])+len(asset['icc'])
        if plan['peak_live_bytes']+retained_other+display_reserve+40*1024*1024 <= budget.max_bytes:
            return
        # Acquisition needs at least one feasible explicitly advertised path,
        # not the largest scratch reservation of every installed renderer.
        # The chosen preview still performs its own exact strict admission.
        if 'direct-v1' not in renderers:
            raise MemoryError('V2 完整来源与输出工作集仍超出预算；不会缩小最终图像')
    if 'direct-v1' not in renderers:
        raise ValueError('No explicitly advertised lens renderer can admit this source')
    # A definite lower bound of the existing stage's simultaneous reservation.
    # Reject impossible sources before presenting a painting session. This does
    # not replace the later exact source/depth/candidate allocation admission.
    minimum=len(asset['content'])+pixels*128+display_reserve+32*1024*1024
    if minimum>budget.max_bytes:
        raise MemoryError('当前完整来源超过本版镜头渲染工作集；尚不支持此分辨率，不会缩小结果或开始无法提交的涂抹会话')
    # Radius<=0.5 is numerically neutral. At least a one-pixel real aperture
    # must fit, rather than enabling a tool that can only save unchanged copies.
    if pixels*min(width,5)*min(height,5)>budget.max_candidate_taps:
        raise MemoryError('当前分辨率连最小实际镜头散焦也超过本版运算预算；高分辨率渲染仍待实现，不会以预览图代替')


def source_notice(source,budget,*,renderers=('direct-v1',)):
    if 'cohort-fft-v2' in renderers:
        return (' 可显式选择 v2 完整光圈渲染；仅人工恒定基准面。羽化残差、笔画扫描、FFT、保留数据和协作式截止均有独立预算，超过即拒绝，不简化或缩图。'
                '原始 JPEG/PNG 的已支持全局调色可走分阶段完整来源捕获；颜色分级与可选颜色沿用原核心并分块处理。任意角裁剪旋转仅在后置效果均中性时使用有预算的原采样公式。活动人像、重型全局效果、RAW/TIFF 等仍受原有预算限制。不是任意 24MP 工作流或性能验收。')
    width,height=source['width'],source['height']
    pixels=width*height
    maximum=.5
    for halo in range(2,130):
        if pixels*min(width,2*halo+1)*min(height,2*halo+1)>budget.max_candidate_taps:break
        maximum=min(128.,halo-.5)
    return (' 当前来源的邻域预算半径上界约 '+str(maximum)+' 像素；实际还需满足内存、笔画和协作式截止检查，'
            '不是性能承诺。高分辨率照片和较大半径尚未全面支持。')
