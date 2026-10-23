/* SPDX-License-Identifier: GPL-3.0-or-later
 * AUTHORED UNRUN. See docs/fringe-repair/KERNEL.md for the complete contract.
 */
#ifndef LRT_FRINGE_REPAIR_H
#define LRT_FRINGE_REPAIR_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

uint32_t lrt_fringe_repair_abi(void);
int32_t lrt_fringe_validate_rgb(const float *input, size_t length,
    size_t width, size_t height);
int32_t lrt_fringe_validate_coverage(const float *input, size_t length,
    size_t width, size_t height);
/* Processing-raster pixels, not original-source pixels. Zero means invalid. */
size_t lrt_fringe_required_halo(float radius_source, float scale);

/* The caller owns valid aligned full-raster immutable input buffers. RGB is
 * interleaved float32, with the same working encoding and registration in both
 * frames. Lengths count floats. NULL coverage requires coverage_length == 0.
 * Output must be disjoint from every input. Cancellation must not unwind or
 * mutate inputs. Every nonzero return leaves every output byte unchanged.
 * Source and guide may alias each other because both are immutable.
 * 0 success; 1 layout; 2 settings; 3 pixel; 4 allocation; 5 numeric result;
 * 6 panic contained; 7 cancelled. Never compile with panic=abort when relying
 * on panic containment. No hidden morphology, chromatic repair, or clipping.
 */
int32_t lrt_fringe_repair_tile(
    const float *edited, size_t edited_length,
    const float *guide, size_t guide_length,
    size_t width, size_t height,
    const float *coverage, size_t coverage_length,
    size_t tile_x, size_t tile_y, size_t tile_width, size_t tile_height,
    float strength, float radius_source, float scale, float threshold,
    float *output, size_t output_length,
    int32_t (*cancel)(void *), void *cancel_context);

#ifdef __cplusplus
}
#endif
#endif
