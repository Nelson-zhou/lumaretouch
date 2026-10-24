/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_SKIN_EVENNESS_H
#define LRT_SKIN_EVENNESS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. RGB: encoded working-sRGB-D65 SDR float32 HWC3.
 * prepare: immutable full same-face source window + actual HW skin permission,
 * amount[0,1], measured source-grid radius[4,256] -> HWC2 log-chroma field.
 * apply: actual current-stage RGB + HWC2 field, Euclidean norm <= .09 (+1e-7
 * float tolerance), -> RGB at each current pixel's own linear luminance.
 * Lengths count floats. Output must overlap no input. Status: 0 success,
 * 1 ABI/length/dimensions/alias, 2 settings, 3 pixels/numerical refusal,
 * 4 cancellation, 5 resources, 6 panic, 7 insufficient own-source reference,
 * 8 insufficient supported guided context.
 * All nonzero returns leave output untouched. Publication is a final unchecked
 * non-cancellable memory copy, NOT concurrent synchronization or crash safety.
 * Caller owns valid buffers, immutable inputs, exclusive output and callback
 * lifetime. Callback must not unwind, reenter or mutate the buffers. */
uint32_t lrt_skin_evenness_abi(void);
int32_t lrt_skin_evenness_prepare_v1(
    const float *source, size_t source_len, const float *coverage, size_t coverage_len,
    size_t width, size_t height, float amount, size_t radius,
    float *output, size_t output_len, int32_t (*cancel)(void *), void *context);
int32_t lrt_skin_evenness_apply_v1(
    const float *current, size_t current_len, const float *shift, size_t shift_len,
    size_t width, size_t height, float *output, size_t output_len,
    int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
