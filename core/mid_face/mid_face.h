/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_MID_FACE_H
#define LRT_MID_FACE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Private ABI 1. Lengths count double elements, not bytes.
 * points[N,2]: finite destination queries, N in 1..65536.
 * params[12]: [ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,
 *             plateau_end,tail,amount]. All finite; amount in [-1,1]; H>0;
 * 0<inner_x<outer_x; plateau_end in [1.25,8]; tail in [.25,4].
 * H measures upper-eye-boundary to nose. The host measures plateau_end to cover
 * retained lower-face points including chin, plus support padding. No anatomy
 * is inferred, and plateau_end is not assumed to equal a specific chin point.
 * Unit orthogonal axes within 1e-10, then normalized to unit right and signed
 * perpendicular down. Origin, widths, H and queries share coordinate units.
 * +amount lengthens, -amount shortens. gain=.08 is original numeric policy.
 * Forward: u'=u, v'=v+.08*amount*H*L(u)*V(v/H). L is a C2 lateral quintic.
 * V(t): zero t<=0; quintic rise 0<t<1; one 1<=t<=plateau_end; quintic neck
 * feather plateau_end<t<plateau_end+tail; zero afterward. Equal-u nose-to-chin
 * intervals translate equally. All targets in the lateral core share motion.
 * Determinant >=1-.08*abs(amount)*1.875/min(1,tail)>=.4 in real arithmetic.
 * Actual signed inverse shift is solved using safeguarded Newton/bisection,
 * with explicit residual and representable source roundtrip checks.
 * output[N,2]=down*d=q-source(q), NOT forward motion or source positions.
 * Exact positive zero at neutral, upper boundary and at/outside support.
 * Finite-precision inverse is tolerance-bounded, not exact. Supported edits
 * underflowing to zero are refused. Tiny nonzero deltas can disappear on source
 * subtraction or downstream float32 conversion; no changed-pixel guarantee.
 * No RGB sampling, models, fallback, runtime build or downloads.
 * Caller owns valid aligned live buffers, immutable inputs and exclusive output.
 * Output overlaps neither input. Address checks do not prove allocation extent
 * or lifetime. Every error leaves all output untouched. Scratch <=1 MiB payload.
 * Status: 0 success, 1 ABI/count/length/pointer/alias, 2 finite/range values,
 * 3 frame/H, 4 support/arithmetic/precision/residual, 5 allocation, 6 panic. */
uint32_t lrt_mid_face_abi(void);
int32_t lrt_mid_face_evaluate_v1(
    const double *points, size_t points_len,
    const double *params, size_t params_len, size_t count,
    double *output, size_t output_len);
#ifdef __cplusplus
}
#endif
#endif
