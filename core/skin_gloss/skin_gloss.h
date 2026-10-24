/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_SKIN_GLOSS_H
#define LRT_SKIN_GLOSS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Encoded working-sRGB-D65 SDR float32 HWC RGB, HW coverage.
 * Immutable ORIGINAL reference and current finish image share the same grid.
 * Lengths count floats, output overlaps no input. Amount [-1,1], radius [2,256].
 * Full domain or true 2*radius halo is required. No implied edge replication.
 * Status 0 success; 1 ABI; 2 settings; 3 pixels; 4 cancelled; 5 resource; 6 panic.
 * Output is private scratch and must be discarded on any nonzero status.
 * Caller owns allocations/lifetimes. Callback must not unwind or mutate buffers. */
uint32_t lrt_skin_gloss_abi(void);
int32_t lrt_skin_gloss_apply_v1(
    const float *current, size_t current_len,
    const float *reference, size_t reference_len,
    const float *coverage, size_t coverage_len,
    size_t width, size_t height, float amount, size_t radius,
    float *output, size_t output_len,
    int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
