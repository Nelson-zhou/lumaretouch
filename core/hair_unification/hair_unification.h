/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original manually referenced chromatic hair unification. AUTHORED / UNRUN.
 * All lengths count float elements, not bytes. See docs/hair-unification/ABI.md.
 */
#ifndef LRT_HAIR_UNIFICATION_H
#define LRT_HAIR_UNIFICATION_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { LRT_HAIR_UNIFICATION_ABI_V1 = 1 };
enum { LRT_HAIR_REFERENCE_TIPS = -1, LRT_HAIR_REFERENCE_NEUTRAL = 0,
       LRT_HAIR_REFERENCE_ROOTS = 1 };
enum { LRT_HAIR_OK = 0, LRT_HAIR_ABI_ERROR = 1, LRT_HAIR_VALUE_ERROR = 2,
       LRT_HAIR_LIMIT_ERROR = 3, LRT_HAIR_CANCELLED = 4,
       LRT_HAIR_ALLOCATION_ERROR = 5, LRT_HAIR_PANIC_ERROR = 6,
       LRT_HAIR_UNRELIABLE_REFERENCE = 7, LRT_HAIR_AMBIGUOUS_REFERENCE = 8,
       LRT_HAIR_RESULT_ERROR = 9 };

typedef struct {
    uint64_t max_source_pixels, max_tile_pixels, max_work_units, max_working_bytes;
} LrtHairUnificationLimitsV1;
typedef struct {
    uint32_t abi_version, struct_size;
    int32_t direction;
    uint32_t reserved;
    uint32_t source_width, source_height;
    uint64_t selected_pixels, reliable_pixels;
    double selected_weight, reliable_weight, effective_samples;
    double retained_fraction, dispersion;
    double chroma_ratio[3];
} LrtHairUnificationReferenceV1;
typedef uint32_t (*LrtHairUnificationCancelV1)(void *context);

uint32_t lrt_hair_unification_abi(void);
int32_t lrt_hair_unification_measure_v1(
    const float *source_rgb, uint64_t source_rgb_len,
    const float *hair, uint64_t hair_len,
    const float *roots, uint64_t roots_len,
    const float *tips, uint64_t tips_len,
    uint32_t source_width, uint32_t source_height, float signed_amount,
    const LrtHairUnificationLimitsV1 *limits,
    LrtHairUnificationReferenceV1 *reference_out,
    LrtHairUnificationCancelV1 cancel, void *cancel_context);
int32_t lrt_hair_unification_compose_v1(
    const float *current_rgb, uint64_t current_rgb_len,
    const float *hair, uint64_t hair_len,
    uint32_t tile_x, uint32_t tile_y, uint32_t tile_width, uint32_t tile_height,
    float signed_amount, const LrtHairUnificationReferenceV1 *reference,
    const LrtHairUnificationLimitsV1 *limits,
    float *output_rgb, uint64_t output_rgb_len,
    LrtHairUnificationCancelV1 cancel, void *cancel_context);

/* NULL limits uses {64000000,262144,1000000000,8388608}.
 * Limits can only reduce these hard ceilings. NULL cancel disables cancellation.
 * Source RGB is genuine encoded working-sRGB float32 in [0,1], not an 8-bit proxy.
 * Active masks are finite [0,1]. roots/tips must be <= hair and not overlap.
 * Negative amount selects tips, positive selects roots. Amount is in [-1,1].
 * Reference is a full-source measurement; compose inputs are tightly packed
 * CURRENT-stage tile RGB/coverage, with tile coordinates in that source grid.
 * chroma_ratio is q = linear RGB / Y - 1, with weighted sum(q) approximately 0.
 * Current-stage luminance/detail are preserved; no blur, invented hair or delta.
 * Zero compose ignores reference and hair, preserves every current float bit.
 * Zero measure ignores source and masks, writes an unusable neutral reference.
 * All calls validate basic shape, limits, and required output pointer on zero.
 * Inputs may alias each other. Every output span must be disjoint from every
 * accessed input, reference and limits span. Even exact in-place RGB is rejected.
 * All buffers must be aligned, live and immutable for the complete call.
 * Callback/context must be live, non-throwing and must not mutate ABI buffers.
 * Every nonzero return leaves all output bytes unchanged. Commit is not polled.
 * Caller must discard superseded results and bind evidence to source/person.
 * Compile with panic=unwind; aborting builds cannot contain panics.
 */
#ifdef __cplusplus
}
#endif
#endif
