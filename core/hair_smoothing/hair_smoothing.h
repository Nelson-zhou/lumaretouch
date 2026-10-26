/* SPDX-License-Identifier: GPL-3.0-or-later
 * AUTHORED / UNRUN. Original visible-owned-hair directional smoothing ABI. */
#ifndef LRT_HAIR_SMOOTHING_H
#define LRT_HAIR_SMOOTHING_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Measure: full canonical encoded working-sRGB D65 SDR f32 RGB, target/context
 * f32 HW [0,1], protection u8 HW exactly 0/1. Target must be within context or
 * protected. Context is already intersected with exact owned visible hair.
 * Output signed natural-log luminance gain <= ln(1.10), separate eligible u8 HW.
 * All central derivative, tensor and bilinear dependencies must be owned and
 * unprotected. Complete conservative square halo is reported by plan.
 * Counts[4]: supported, context-rejected, directional, nonzero-proposal pixels.
 * Metrics[2]: maximum abs stored gain, maximum admitted center coherence.
 * Eligibility does NOT assert signal, visible change or physical hair detection.
 * Compose: CURRENT LINEAR SDR RGB, same frozen field, common RGB headroom gain.
 * No per-channel clamp, source-RGB replacement, inference or geometry.
 * All buffers exact size, live/aligned/input-stable and pairwise DISJOINT.
 * Foreign callback must not unwind, mutate buffers or reenter. No pointer kept.
 * On error/cancel every caller output stays untouched; OOM admission is checked
 * but foreign invalid pointers/callback faults cannot be caught.
 * Source max 32 MP; dims 1..65536, observed source texture scale 1..8 pixels.
 * Byte budget includes caller input/output, wrapper snapshots/retention and
 * native scratch, not unrelated host/analysis/other-operator residents.
 * Status: 0 success incl no signal; 1 ABI/layout/alias; 2 invalid input;
 * 3 scale; 4 no complete context; 5 memory/budget; 6 canceled; 7 numerics;
 * 8 contained panic. All claims source-only, authored/unrun.
 */
uint32_t lrt_hair_smoothing_abi(void);
uint32_t lrt_hair_smoothing_algorithm(void);
int32_t lrt_hair_smoothing_plan_v1(size_t width,size_t height,double texture_scale,
    uint64_t *values,size_t values_len); /* exactly [required,retained,halo] */
int32_t lrt_hair_smoothing_measure_v1(
    const float *rgb,size_t rgb_len,const float *target,size_t target_len,
    const float *context_weight,size_t context_len,const uint8_t *protect,size_t protect_len,
    size_t width,size_t height,double texture_scale,uint64_t byte_budget,
    float *output,size_t output_len,uint8_t *eligible,size_t eligible_len,
    uint64_t *counts,size_t counts_len,double *metrics,size_t metrics_len,
    int32_t (*cancel)(void *),void *context);
int32_t lrt_hair_smoothing_compose_v1(
    const float *current_linear_rgb,size_t rgb_len,const float *field,size_t field_len,
    size_t width,size_t height,double amount,uint64_t byte_budget,
    float *output,size_t output_len,int32_t (*cancel)(void *),void *context);
#ifdef __cplusplus
}
#endif
#endif
