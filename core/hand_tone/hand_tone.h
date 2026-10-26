/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original manual hand mid-frequency luminance correction. AUTHORED / UNRUN. */
#ifndef LRT_HAND_TONE_H
#define LRT_HAND_TONE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* ABI/algorithm 1. Native-endian contiguous f32 source-grid linear working
 * sRGB-D65 SDR RGB [0,1], HWC. Host may supply the full source or an exact
 * unscaled source-grid ROI enclosing every positive target plus the full radius
 * halo. Host proves original coordinates, actual dimensions, same source/masks,
 * and scatters returned fields without resizing. No padded/reflected pixels.
 * A ROI clipped at an original source edge retains that edge: targets without
 * full radius context refuse just as in the full source. ABI does not prove ROI
 * provenance or supply missing halo. Different summation order may introduce
 * floating-point differences, especially at eligibility/gating thresholds. limb/target HW [0,1], target<=limb;
 * protect HW bytes exactly0/1. No automatic hand detector or inferred masks.
 * radius2..128 actual source pixels. Small radius=max(1,radius/4).
 * Output field HWC equal-channel log gains ±ln(1.08), eligible HW0/1.
 * counts[4]: unprotected painted targets, eligible targets, rejected context,
 * nonzero proposals (NOT visible changes). metrics[4]: maximum absolute coarse
 * minus small logY mean; max coarse logY sigma (both only valid contexts,
 * including contrast-rejected ones); max absolute emitted gain; minimum target
 * coarse support fraction (includes source-edge/ineligible windows).
 * Full coarse window required inside supplied actual source-grid bounds, no black/clipped/zero-support or
 * protected observations in window; >=95% weighted support at both scales.
 * LogY sigma gate smoothstep: full at<=0.08, zero at>=0.18. Gain is coarse-small,
 * capped ±ln1.08, multiplied by gate and target. High-frequency residual is not
 * explicitly blurred, but no guarantee of texture/anatomy preservation is made.
 * Return0 success;1 ABI/buffers;2 domain;3 radius/amount;4 no usable context;
 * 5 resources;6 cancellation;7 numerics;8 contained Rust panic.
 * Nonzero return leaves ALL outputs unchanged. Live aligned input arrays must
 * not overlap outputs; outputs pairwise disjoint. Callback cannot throw, mutate
 * buffers or reenter. Invalid foreign pointers/callback faults not contained.
 * Budget>=160*N+8MiB measure,>=80*N+1MiB apply, caller charges other residency.
 * All-zero/protected target succeeds with zero fields. No retained pointers.
 */
uint32_t lrt_hand_tone_abi(void);
uint32_t lrt_hand_tone_algorithm(void);
int32_t lrt_hand_tone_measure_v1(
 const float *rgb,size_t rgb_len,const float *limb,size_t limb_len,
 const float *target,size_t target_len,const uint8_t *protect,size_t protect_len,
 size_t width,size_t height,size_t radius,uint64_t byte_budget,
 float *field,size_t field_len,uint8_t *eligible,size_t eligible_len,
 uint64_t *counts,size_t counts_len,double *metrics,size_t metrics_len,
 int32_t (*cancel)(void *),void *context);
/* Apply frozen equal-channel field once, scaled linearly by amount0..1.
 * One common headroom factor prevents clipping without independent channel
 * clamps. Exact zero fields/amount retain input bits. Non-common fields refuse.
 * amount0 permits field=NULL,len0; current RGB still validated. Host must prove
 * source/mask/stage/review authority; this numerical ABI does not prove it. */
int32_t lrt_hand_tone_apply_v1(
 const float *current,size_t current_len,const float *field,size_t field_len,
 size_t width,size_t height,double amount,uint64_t byte_budget,
 float *output,size_t output_len,int32_t (*cancel)(void *),void *context);
#ifdef __cplusplus
}
#endif
#endif
