/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_BROW_ENHANCE_H
#define LRT_BROW_ENHANCE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Encoded working-sRGB-D65 float32 SDR HWC source RGB,
 * separate disjoint HW target and actual adjacent-forehead reference coverage.
 * Lengths count floats, output overlaps no input. Amount [-1,1], radius [2,128].
 * Caller owns pointers, immutable input lifetime and anatomical provenance.
 * Status 0 success; 1 ABI; 2 settings; 3 pixels/overlap/numerics; 4 cancelled;
 * 5 resource; 6 panic; 7 insufficient/heterogeneous actual local reference.
 * Returned errors/cancellation leave output untouched. Final successful copy
 * follows the last cancellation poll and is not interruptible. No retained data.
 * Callback must not unwind, reenter, free allocations or mutate these buffers. */
uint32_t lrt_brow_enhance_abi(void);
int32_t lrt_brow_enhance_apply_v1(
    const float *source, size_t source_len,
    const float *target, size_t target_len,
    const float *reference, size_t reference_len,
    size_t width, size_t height, float amount, size_t radius,
    float *output, size_t output_len,
    int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
