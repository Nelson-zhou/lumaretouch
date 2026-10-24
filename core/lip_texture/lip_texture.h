/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_LIP_TEXTURE_H
#define LRT_LIP_TEXTURE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. ABI1: encoded working-sRGB-D65 SDR float32 HWC RGB/HW
 * coverage. Lengths count float elements, not bytes. Immutable source/coverage;
 * exclusively writable output overlaps neither input. Strict amount [0,1],
 * measured unit mouth across axis (norm tolerance 1e-4), integer radius 1..12.
 * Entire real source window, or true 3*radius+1 halo before crop, is required.
 * Entire square of radius 3*radius needs coverage >=0.999; no edge replication.
 * 0 success,1 ABI,2 settings,3 pixels/numerics,4 cancelled,5 resources,6 panic.
 * Output is unchanged on nonzero return and must nevertheless not be published.
 * Cancellation polled before final copy, not during commit. Caller must not
 * inspect output concurrently. Callback cannot unwind/reenter/mutate buffers. */
uint32_t lrt_lip_texture_abi(void);
int32_t lrt_lip_texture_apply_v1(
    const float *source, size_t source_len, const float *coverage, size_t coverage_len,
    size_t width, size_t height, float amount, float across_x, float across_y, size_t radius,
    float *output, size_t output_len, int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
