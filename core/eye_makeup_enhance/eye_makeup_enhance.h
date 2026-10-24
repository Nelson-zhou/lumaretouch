/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_EYE_MAKEUP_ENHANCE_H
#define LRT_EYE_MAKEUP_ENHANCE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_eye_makeup_enhance_abi(void);
int lrt_eye_makeup_enhance_apply_v1(const float *rgb,size_t rgb_count,
 const float *coverage,size_t coverage_count,const float *reference_a,size_t reference_a_count,
 const float *reference_b,size_t reference_b_count,size_t width,size_t height,
 float amount,float saturation,float brightness,float structure,size_t radius,
 float *output,size_t output_count,int (*cancel)(void *),void *context);
#ifdef __cplusplus
}
#endif
#endif
