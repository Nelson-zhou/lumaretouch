/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_LOWER_FACE_H
#define LRT_LOWER_FACE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Private ABI 1. Lengths count double elements, not bytes.
 * points[N,2]: finite destination queries, N in 1..65536.
 * params[11]: [ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,tail,amount].
 * All values finite; amount in [-1,1], H>0, 0<inner_x<outer_x, tail in [.25,1].
 * Unit orthogonal axes within 1e-10, then normalized to unit right and signed
 * perpendicular down. Origin, widths, H and queries share coordinate units.
 * +amount lengthens, -amount shortens. Runtime policy tail=.5, gain=.08.
 * Forward preserves u and changes v by .08*amount*H*L(u)*V(v/H).
 * L is a C2 quintic lateral feather; V rises 0..H and falls H..(1+tail)*H.
 * Forward axial derivative >=.4 in real arithmetic. Monotone inverse is solved
 * with bounded bracketed iterations; residual and representable source checked.
 * output[N,2]=q-source(q), NOT forward motion or source positions. Exact positive
 * zero at neutral, upper boundary and at/outside support. Floating-point inverse
 * is tolerance-bounded, not exact. Underflowed supported edits are refused.
 * No RGB sampling, models, identity pins, fallback, runtime build or downloads.
 * Caller owns valid aligned live buffers, immutable inputs and exclusive output.
 * Output overlaps neither input. Address checks do not prove allocation extent
 * or lifetime. Every error leaves all output untouched. Scratch <=1 MiB payload.
 * Status: 0 success, 1 ABI/count/length/pointer/alias, 2 finite/range values,
 * 3 frame/H, 4 support/arithmetic/precision/residual, 5 allocation, 6 panic. */
uint32_t lrt_lower_face_abi(void);
int32_t lrt_lower_face_evaluate_v1(
    const double *points, size_t points_len,
    const double *params, size_t params_len, size_t count,
    double *output, size_t output_len);
#ifdef __cplusplus
}
#endif
#endif
