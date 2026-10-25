# SPDX-License-Identifier: GPL-3.0-or-later
"""Honest early bounds for the current full-grid aperture path, not a fallback."""

def source_admission(asset, budget, *, display_reserve):
    width,height=asset['width'],asset['height']
    pixels=width*height
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


def source_notice(source,budget):
    width,height=source['width'],source['height']
    pixels=width*height
    maximum=.5
    for halo in range(2,130):
        if pixels*min(width,2*halo+1)*min(height,2*halo+1)>budget.max_candidate_taps:break
        maximum=min(128.,halo-.5)
    return (' 当前来源的邻域预算半径上界约 '+str(maximum)+' 像素；实际还需满足内存、笔画和协作式截止检查，'
            '不是性能承诺。高分辨率照片和较大半径尚未全面支持。')
