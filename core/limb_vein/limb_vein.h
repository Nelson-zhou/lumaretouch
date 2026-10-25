/* SPDX-License-Identifier: GPL-3.0-or-later
 * LumaRetouch original reference-assisted limb correction. AUTHORED / UNRUN. */
#ifndef LRT_LIMB_VEIN_H
#define LRT_LIMB_VEIN_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* ABI 1, algorithm 1. Native-endian f32, contiguous FULL source grid.
 * RGB: linear working-sRGB-D65 SDR [0,1], HWC. No gamma-encoded RGB or proxy.
 * limb/target/reference: HW [0,1]. target/reference <= limb, mutually
 * disjoint. protect: HW bytes exactly 0 or 1, excluded from target AND donors.
 * radius 2..128 real source pixels. Output field: HWC log RGB gains, range
 * [-0.303949046,0.303949046]; eligible: HW 0/1. Current implementation uses full grid.
 * counts[4]: painted unprotected target, eligible target, context rejected,
 * positive-or-negative proposal count. metrics[4]: clean reference mass,
 * maximum reference channel log standard deviation, max absolute log gain,
 * minimum target local support fraction. These are NOT visible-change counts.
 * Reference: mass >=16, each admitted ref channel strictly (1e-5,0.995),
 * max per-channel log std <=0.35. Radius-normalized local donor mass >=75% of
 * actual source-clipped box area; no image-edge replication or proxy fit.
 * Caller arrays must be live, aligned, stable during call, correctly sized and
 * disjoint from ALL outputs. Output buffers disjoint from each other.
 * Return 0 success; 1 ABI/buffers; 2 input/domain; 3 radius/amount; 4 reference/context;
 * 5 resource/budget; 6 cancellation; 7 numerics; 8 contained Rust panic.
 * Nonzero result leaves every output untouched. Foreign pointer/callback faults
 * cannot be caught. Callback cannot throw, mutate arrays, or reenter.
 * Budget >=128*N+8MiB for measure, >=80*N+1MiB for apply; host charges unrelated
 * resident data separately. Zero-mask measure succeeds with zero fields without
 * demanding a clean reference. No pointers are retained.
 */
uint32_t lrt_limb_vein_abi(void);
uint32_t lrt_limb_vein_algorithm(void);
int32_t lrt_limb_vein_measure_v1(
 const float *rgb, size_t rgb_len,
 const float *limb, size_t limb_len,
 const float *target, size_t target_len,
 const float *reference, size_t reference_len,
 const uint8_t *protect, size_t protect_len,
 size_t width, size_t height, size_t radius, uint64_t byte_budget,
 float *field, size_t field_len, uint8_t *eligible, size_t eligible_len,
 uint64_t *counts, size_t counts_len, double *metrics, size_t metrics_len,
 int32_t (*cancel)(void *), void *context);
/* Apply a frozen measured field once to CURRENT linear SDR RGB, same grid.
 * amount 0..1: min(2*amount,1) scales zero-mean log chroma;
 * max(2*amount-1,0) scales common log tone. Measured common tone is capped
 * at ln(1.12); chroma components are clamped at ln(1.10) then re-centered.
 * One scalar t limits all effective channel log gains to RGB headroom; no
 * independent RGB clipping. Exact zeros in field and amount preserve input bits.
 * amount==0 permits field=NULL,field_len=0, but still validates current RGB.
 * This is not an authority check: host binds source, masks, review and stage.
 */
int32_t lrt_limb_vein_apply_v1(
 const float *current, size_t current_len, const float *field, size_t field_len,
 size_t width, size_t height, double amount, uint64_t byte_budget,
 float *output, size_t output_len, int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
