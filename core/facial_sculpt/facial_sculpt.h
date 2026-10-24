/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_FACIAL_SCULPT_H
#define LRT_FACIAL_SCULPT_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_facial_sculpt_abi(void);
/* All input RGB is encoded working-sRGB-D65 SDR float32. Output is HW log gain.
   Coverage is finite [0,1], target <= support. Caller owns all live buffers.
   Output must not alias inputs. No partial output on an error return. */
int lrt_facial_sculpt_field_v1(const float *source, size_t source_len,
    const float *support, size_t support_len, const float *target, size_t target_len,
    size_t width, size_t height, float highlight, float shadow, size_t radius,
    float *output, size_t output_len, int (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
