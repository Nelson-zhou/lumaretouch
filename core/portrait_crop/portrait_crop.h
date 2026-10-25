/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original portrait-composition scalar ABI 1. AUTHORED / UNRUN.
 */
#ifndef LRT_PORTRAIT_CROP_H
#define LRT_PORTRAIT_CROP_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define LRT_PORTRAIT_CROP_ABI 1u
#define LRT_PORTRAIT_CROP_REVIEWED_ANCHORS 1u
#define LRT_PORTRAIT_CROP_NO_PADDING 2u
#define LRT_PORTRAIT_CROP_TIES_EVEN_EDGES 4u
#define LRT_PORTRAIT_CROP_ACHIEVED_METRICS 8u
#define LRT_PORTRAIT_CROP_RESULT_LEN 20u

uint32_t lrt_portrait_crop_abi(void);
uint64_t lrt_portrait_crop_capabilities(void);
size_t lrt_portrait_crop_result_len(void);

/* width/height: 1..INT32_MAX. No image-memory admission is implied.
 * anchors[6]: crown x/y, chin x/y, face-center x/y, full source-edge pixels.
 * rules[4]: W/H, headroom/H, crown-to-chin-height/H, horizontal face position.
 * output[20]:
 *  0..3 continuous requested left/top/right/bottom source-pixel edges;
 *  4..7 pixel-rounded canonical normalized rect for existing lnx.crop.v1;
 *  8..11 actual integer left/top/right/bottom edges, represented as doubles;
 * 12..16 achieved aspect/headroom/head fraction/horizontal/vertical position;
 * 17 crown-to-chin pixel height; 18 output width; 19 output height.
 * No independent vertical-position control; it follows headroom/head fraction.
 * Every pointer must denote a valid, aligned, live buffer of the exact length.
 * Output must not overlap either input. Inputs may alias each other.
 * No concurrent mutation. All nonzero returns leave output unchanged.
 * Codes: 0 success; 1 ABI/span; 2 invalid geometry; 3 infeasible/no padding;
 * 4 rounding collapsed/excluded anchor; 5 contained panic. Panic containment
 * requires unwind, not panic=abort. No authority/source proof crosses this ABI.
 */
int32_t lrt_portrait_crop_plan_v1(uint32_t width, uint32_t height,
    const double *anchors, size_t anchors_len,
    const double *rules, size_t rules_len,
    double *output, size_t output_len);

#ifdef __cplusplus
}
#endif
#endif
