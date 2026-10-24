/* SPDX-License-Identifier: GPL-3.0-or-later
 * AUTHORED / UNRUN. Numeric coordinate ABI only, never an image sampler.
 * Pointers are live aligned f64 arrays, exact length, mutually disjoint.
 * Caller snapshots inputs and must not mutate them concurrently.
 */
#ifndef LRT_BODY_SLIM_H
#define LRT_BODY_SLIM_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_body_slim_abi(void);
int32_t lrt_body_slim_prepare(const double *points, size_t points_len,
    const double *amounts, size_t amounts_len, const double *support, size_t support_len,
    double width, double height, double *state, size_t state_len);
int32_t lrt_body_slim_describe(const double *state, size_t state_len, double *facts, size_t facts_len);
int32_t lrt_body_slim_evaluate(const double *state, size_t state_len,
    const double *xy, size_t xy_len, size_t count,
    double *delta_xy, size_t delta_len, double *inverse_determinants, size_t determinants_len);
#ifdef __cplusplus
}
#endif
#endif
