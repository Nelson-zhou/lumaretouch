/* SPDX-License-Identifier: GPL-3.0-or-later */
/* ABI 1. AUTHORED / UNRUN. Lengths count doubles, not bytes.
 * recipe4=[1,crown,left,right]; support24=three normalized x4+y4 profiles.
 * Inactive profiles must be zero. state30 and facts19 layouts are documented.
 * Caller owns live aligned disjoint allocations and excludes concurrent writes.
 * Refusal writes neither output. No source/person claim is made by this ABI. */
#ifndef LRT_HAIR_VOLUME_H
#define LRT_HAIR_VOLUME_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_hair_volume_abi(void);
int32_t lrt_hair_volume_prepare(const double *recipe, size_t recipe_len,
    const double *support, size_t support_len, double width, double height,
    double *state, size_t state_len);
int32_t lrt_hair_volume_describe(const double *state, size_t state_len,
    double *facts, size_t facts_len);
int32_t lrt_hair_volume_evaluate(const double *state, size_t state_len,
    const double *xy, size_t xy_len, size_t count,
    double *displacement, size_t displacement_len,
    double *inverse_determinant, size_t determinant_len);
#ifdef __cplusplus
}
#endif
#endif
