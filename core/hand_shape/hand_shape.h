/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_HAND_SHAPE_H
#define LRT_HAND_SHAPE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_hand_shape_abi(void);
/* ABI 1; all lengths count f64 elements, not bytes. Rows contain 7 scalars:
 * cx, cy, longitudinal ux, uy, longitudinal radius, transverse radius, k.
 * Outputs inverse displacement q-source(q) and analytic inverse determinant.
 * Failures never modify either output. Buffers must be allocated, alive, and
 * non-overlapping with output buffers; no concurrent writes are permitted. */
int32_t lrt_hand_shape_evaluate(const double *primitives, size_t primitives_len,
    size_t count, uint32_t width, uint32_t height, double max_displacement,
    const double *points, size_t points_len, size_t n,
    double *out, size_t out_len, double *jac, size_t jac_len);
#ifdef __cplusplus
}
#endif
#endif
