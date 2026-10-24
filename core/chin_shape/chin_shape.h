/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_CHIN_SHAPE_H
#define LRT_CHIN_SHAPE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Private ABI 1. Lengths count double elements, not bytes.
 * points[N,2]: finite destination queries; N=1..65536.
 * params[11]=[ox,oy,right_x,right_y,down_x,down_y,H,inner_x,outer_x,left,right].
 * All finite; H>0; inner_x>0; outer_x==2*inner_x EXACTLY; left/right in [-1,1].
 * Unit orthogonal axes within 1e-10, then normalized right and signed-normal down.
 * Origin, H, widths and points share source units. u>0 uses subject left;
 * u<0 uses subject right. Host supplies anatomy, measured below-lips origin and
 * tip152-centered u. Positive contracts horizontal chin width, negative expands.
 * Forward u'=u*(1-.08*a_side*V(v/H)*L(abs(u))); v'=v. Centerline fixed.
 * S(z)=z^3*(10-15z+6z^2); L=1 below inner, S((outer-r)/inner) in feather,
 * zero at/above outer. V=S(t) for 0<t<1; S((1.5-t)/.5) for 1<=t<1.5;
 * zero otherwise. No center blend/dead zone. Unequal sides give a derivative
 * cusp at u=0, but continuity and horizontal bi-Lipschitz bounds [.7,1.3].
 * Determinant bound holds away from cusp; not a global C1/condition guarantee.
 * Actual inverse uses safeguarded Newton/bisection, a displacement-relative
 * residual and coordinate-scale representable-source roundtrip tolerance.
 * output=q-source(q) algebraically, NOT forward motion. A nonzero stored delta
 * may round away in q-delta; coordinate/pixel movement is not guaranteed.
 * Exact positive zero for neutral sides, u=0 and at/outside support. Supported
 * motion underflowing to zero is refused, never silently neutralized.
 * Finite precision and downstream float32 may erase effective pixel movement.
 * No image sampling, inference, runtime builds, downloads or fallback.
 * Caller owns aligned live buffers of declared extents, immutable inputs and
 * exclusive output. Output may overlap neither input; inputs may overlap.
 * Checked addresses do not prove provenance, allocation extent or lifetime.
 * All failures leave output untouched. Private scratch <=1 MiB f64 payload.
 * Status: 0 success; 1 ABI/count/length/pointer/alias; 2 finite/range values;
 * 3 frame/H; 4 support/arithmetic/precision/residual; 5 allocation; 6 panic. */
uint32_t lrt_chin_shape_abi(void);
int32_t lrt_chin_shape_evaluate_v1(
    const double *points, size_t points_len,
    const double *params, size_t params_len, size_t count,
    double *output, size_t output_len);
#ifdef __cplusplus
}
#endif
#endif
