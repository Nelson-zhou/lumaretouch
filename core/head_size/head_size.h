/* SPDX-License-Identifier: GPL-3.0-or-later */
/* ABI 1, AUTHORED / UNRUN. All lengths are counts of doubles, never bytes.
 * Unsafe caller contract: live aligned disjoint buffers, immutable for call.
 * Outputs remain untouched on refusal under that contract. See numerical doc. */
#ifndef LRT_HEAD_SIZE_H
#define LRT_HEAD_SIZE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_head_size_abi(void);
int32_t lrt_head_size_prepare(
    const double *points, size_t points_len,
    const double *recipe, size_t recipe_len,
    const double *support, size_t support_len,
    double width, double height, double *state, size_t state_len);
int32_t lrt_head_size_describe(
    const double *state, size_t state_len, double *facts, size_t facts_len);
int32_t lrt_head_size_evaluate(
    const double *state, size_t state_len,
    const double *xy, size_t xy_len, size_t count,
    double *displacement, size_t displacement_len,
    double *inverse_determinant, size_t determinant_len);
#ifdef __cplusplus
}
#endif
#endif
