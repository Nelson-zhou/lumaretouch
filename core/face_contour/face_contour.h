/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_FACE_CONTOUR_H
#define LRT_FACE_CONTOUR_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. All lengths count double elements. N is 1..256.
 * Points[N,2]; roles[N,3]=(temple,cheekbone,jaw), each in [0,1].
 * Sides[N]=+1 subject-left/-1 subject-right, not viewer-relative left.
 * Frame[7]=[right_x,right_y,up_x,up_y,center_x,center_y,face_width].
 * Values[6]=[temple_left,temple_right,cheekbone_left,cheekbone_right,
 *             jaw_left,jaw_right], each in [-1,1].
 * Output[N,2] is FORWARD control displacement, not an image or inverse map.
 * Output must overlap no input. Caller owns valid aligned allocations and
 * immutable inputs. Error leaves output untouched; this cannot validate pointer
 * lifetime, anatomical provenance or actual allocation extent.
 * Status: 0 success, 1 ABI, 2 values, 3 frame, 4 displacement, 5 Rust panic. */
uint32_t lrt_face_contour_abi(void);
int32_t lrt_face_contour_controls_v1(
    const double *points, size_t points_len,
    const double *roles, size_t roles_len,
    const double *sides, size_t sides_len,
    const double *frame, size_t frame_len,
    const double *values, size_t values_len, size_t count,
    double *output, size_t output_len);
#ifdef __cplusplus
}
#endif
#endif
