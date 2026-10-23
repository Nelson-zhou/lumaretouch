#ifndef LRT_SPILL_REMOVAL_H
#define LRT_SPILL_REMOVAL_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* All arrays span the complete render domain. Straight linear-sRGB-D65 SDR
 * source RGB is interleaved HWC; alpha/confidence are HW. Pointers may not
 * overlap. Inputs are immutable. Output scratch is valid only on status 0.
 * confidence includes strength ONCE; delta does not. Cancellation may be NULL.
 * Status: 0 success; 1 parameter/shape; 2 unsupported/non-finite pixels;
 * 3 cancellation; 4 memory; 5 numerical failure. */
uint32_t lrt_spill_removal_abi(void);
int32_t lrt_spill_removal_prepare(const float *source, const float *alpha,
    float *delta, float *confidence, size_t width, size_t height,
    float strength, float render_scale, int32_t (*cancelled)(void));
#ifdef __cplusplus
}
#endif
#endif
