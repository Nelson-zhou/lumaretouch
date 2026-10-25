/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original Lumaretouch donor-expression core. Source authored; all tests UNRUN.
 * Lengths count native-endian float32 values. Read ABI.md before calling.
 */
#ifndef LRT_EXPRESSION_BLEND_H
#define LRT_EXPRESSION_BLEND_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define LRT_EXPRESSION_ABI 1u
#define LRT_EXPRESSION_LANDMARK_FLOATS 1434u
#define LRT_EXPRESSION_RECEIPT_FLOATS 16u
#define LRT_EXPRESSION_SAME_PERSON 1u
#define LRT_EXPRESSION_SAME_SESSION 2u
#define LRT_EXPRESSION_TARGET_REAL_LANDMARKS 4u
#define LRT_EXPRESSION_DONOR_REAL_LANDMARKS 8u
#define LRT_EXPRESSION_POSE_REVIEWED 16u
#define LRT_EXPRESSION_TARGET_UNOCCLUDED 32u
#define LRT_EXPRESSION_DONOR_UNOCCLUDED 64u
#define LRT_EXPRESSION_REQUIRED_REVIEWS 127u
#define LRT_EXPRESSION_CAP_MANUAL_DONOR 1u
#define LRT_EXPRESSION_CAP_EDITABLE_FUSION 2u
#define LRT_EXPRESSION_CAP_MULTIBAND 4u
#define LRT_EXPRESSION_CAP_COLOUR_OFFSET 8u
#define LRT_EXPRESSION_CAP_ATOMIC_OUTPUT 16u
#define LRT_EXPRESSION_CAP_CANCELLATION 32u
/* No auto-selection, identity, expression-generation, pose-inference or HDR bit. */
typedef int32_t (*lrt_expression_cancel_fn)(void);
uint32_t lrt_expression_blend_abi(void);
uint64_t lrt_expression_blend_capabilities_v1(void);
size_t lrt_expression_blend_max_side_v1(void);
size_t lrt_expression_blend_max_levels_v1(void);
int32_t lrt_expression_blend_v1(
    const float *target, size_t target_len, size_t target_width, size_t target_height,
    const float *donor, size_t donor_len, size_t donor_width, size_t donor_height,
    const float *target_landmarks, size_t target_landmarks_len,
    const float *donor_landmarks, size_t donor_landmarks_len,
    const float *target_allowed, size_t target_allowed_len,
    const float *donor_allowed, size_t donor_allowed_len,
    const float *target_protection, size_t target_protection_len,
    const float *donor_protection, size_t donor_protection_len,
    const float *fusion, size_t fusion_len,
    /* NULL + length 0 is valid only when colour_strength == 0. */
    const float *colour_reference, size_t colour_reference_len,
    uint32_t reviews,
    float density, float colour_strength, size_t levels,
    float *output, size_t output_len,
    float *effective_fusion, size_t effective_fusion_len,
    float *receipt, size_t receipt_len,
    lrt_expression_cancel_fn cancel);
#ifdef __cplusplus
}
#endif
#endif
