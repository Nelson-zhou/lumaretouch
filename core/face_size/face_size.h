/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_FACE_SIZE_H
#define LRT_FACE_SIZE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Private ABI 1. All lengths count double elements.
 * points[N,2]: finite destination query coordinates, N in 1..65536.
 * params[11]: [cx,cy,right_x,right_y,up_x,up_y,hx,hy,inner,outer,scale].
 * Unit orthogonal axes (1e-6 tolerance); hx,hy > 0; 0 < inner < outer;
 * scale in [0.94,1.06]. All parameters finite. The implementation rejects
 * transition bands whose conservative inverse-derivative floor is below 0.2.
 * output[N,2] = q - source(q), NOT forward displacement/source coordinates.
 * Radius is hypot(dot(q-c,right)/hx, dot(q-c,up)/hy).
 * Uniform inverse scale inside inner; C2 quintic fade; exact zero at/outside
 * outer. No feature pins, contour deformation, anatomy inference or sampling.
 * Caller owns valid aligned live buffers, immutable inputs and exclusive
 * writable output; output overlaps neither input. Address checks do not prove
 * allocation extent or lifetime. Every error leaves all output untouched.
 * Status: 0 success, 1 ABI/count/length/pointer/alias, 2 finite/range values,
 * 3 head frame/extents, 4 support/fold-risk/arithmetic, 5 allocation, 6 panic.
 * Bounded allocated scratch: at most 1 MiB. No model, build or network work. */
uint32_t lrt_face_size_abi(void);
int32_t lrt_face_size_evaluate_v1(
    const double *points, size_t points_len,
    const double *params, size_t params_len, size_t count,
    double *output, size_t output_len);
#ifdef __cplusplus
}
#endif
#endif
