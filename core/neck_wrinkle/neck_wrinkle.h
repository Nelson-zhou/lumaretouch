/* SPDX-License-Identifier: AGPL-3.0-only
 * Copyright Chris Cork. Adapted for LumaRetouch, 2026-10-25. See NOTICE/LICENSE. */
#ifndef LRT_NECK_WRINKLE_H
#define LRT_NECK_WRINKLE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Measurement RGB is full-source encoded working-sRGB-D65
 * SDR native float32 HWC; weight float32 HW; protection uint8 HW exactly 0/1.
 * Apply RGB is CURRENT LINEAR SDR native float32 HWC. No encoded RGB in apply.
 * All arrays finite, live/aligned, input-stable, disjoint; no retained pointers.
 * window is full-source y,x,height,width enclosing all positive unprotected mask.
 * No resolution reduction, context replication, clipping, alpha or chroma donor.
 * Half-width 1.4..12 source pixels, amount 0..1. Field natural-log gain >=0,
 * <=ln(1.25)+1e-8. Counts[4]: context-supported, context-rejected, line, positive
 * proposal pixels. These are NOT a rendered-current-pixel or visual-change claim.
 * Eligible output uint8 HW is actual complete-context support, 0/1, not signal.
 * Metrics[2]: maximum proposed L* lift, maximum stored log gain.
 * Status: 0 success (including no signal), 1 ABI/buffer, 2 input, 3 scale,
 * 4 context, 5 budget, 6 cancelled, 7 numerics, 8 contained panic.
 * On nonzero status output/counts/metrics are untouched. Callback cannot unwind,
 * mutate buffers or reenter. Foreign pointer/callback faults are not caught.
 * budget is total operation-accounted bytes, including caller input residents
 * and wrapper snapshots; host must additionally charge unrelated resident data.
 */
uint32_t lrt_neck_wrinkle_abi(void);
uint32_t lrt_neck_wrinkle_algorithm(void);
int32_t lrt_neck_wrinkle_measure_v1(
    const float *rgb, size_t rgb_len, const float *weight, size_t weight_len,
    const uint8_t *protect, size_t protect_len, size_t width, size_t height,
    size_t window_y, size_t window_x, size_t window_height, size_t window_width,
    double half_width, uint64_t byte_budget, float *output, size_t output_len,
    uint8_t *eligible, size_t eligible_len,
    uint64_t *counts, size_t counts_len, double *metrics, size_t metrics_len,
    int32_t (*cancel)(void *), void *context);
int32_t lrt_neck_wrinkle_apply_v1(
    const float *current_linear_rgb, size_t rgb_len, const float *field, size_t field_len,
    size_t width, size_t height, double amount, float *output, size_t output_len,
    int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
