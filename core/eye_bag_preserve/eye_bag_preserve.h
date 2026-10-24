/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_EYE_BAG_PRESERVE_H
#define LRT_EYE_BAG_PRESERVE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Float32 encoded-working-sRGB SDR HWC source/corrected RGB,
 * HW protection coverage. All values and preserve must be finite [0,1].
 * Lengths count floats. Output overlaps no input; read-only inputs may overlap.
 * Protection=1 and preserve=1 copies source bits exactly. Numerical zero delta
 * copies source bits, including signed zero. Fractional coverage is a bounded
 * source/corrected blend, not anatomical segmentation or physical relighting.
 * Host authenticates source ownership and must supply only this bag correction,
 * never the aggregate of independent eye controls or already-composited output.
 * Status 0 success; 1 ABI; 2 settings; 3 pixels/numerics; 4 cancelled;
 * 5 resource; 6 panic. Returned errors/cancellation leave output untouched.
 * Successful final copy follows the last cancellation poll and is not interruptible.
 * Callback must not unwind, reenter, free allocations or mutate these buffers. */
uint32_t lrt_eye_bag_preserve_abi(void);
int32_t lrt_eye_bag_preserve_apply_v1(
    const float *source, size_t source_len,
    const float *corrected, size_t corrected_len,
    const float *protection, size_t protection_len,
    size_t width, size_t height, float preserve,
    float *output, size_t output_len,
    int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
