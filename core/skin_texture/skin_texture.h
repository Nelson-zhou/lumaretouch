/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_SKIN_TEXTURE_H
#define LRT_SKIN_TEXTURE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Encoded working-sRGB-D65 SDR float32 HWC RGB/HW coverage.
 * ORIGINAL reference and CURRENT colour->finish->gloss image share the same grid.
 * Lengths count floats. Texture[-1,1], clarity[0,1], coarse radius[4,256].
 * Full domain or true 2*radius halo required. Output overlaps no input.
 * Status: 0 success; 1 ABI; 2 settings; 3 pixels; 4 cancel; 5 resource; 6 panic.
 * Discard output after any nonzero status. Callback must not unwind or reenter.
 * Caller owns allocations, valid pointers, immutable inputs and exclusive output. */
uint32_t lrt_skin_texture_abi(void);
int32_t lrt_skin_texture_apply_v1(
    const float *current, size_t current_len,
    const float *reference, size_t reference_len,
    const float *coverage, size_t coverage_len,
    size_t width, size_t height, float texture, float clarity, size_t radius,
    float *output, size_t output_len,
    int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
