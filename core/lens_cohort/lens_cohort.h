/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_LENS_COHORT_H
#define LRT_LENS_COHORT_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. ABI 2; math ID 0x00020001, not ABI1 output identity.
 * Source: tightly packed linear-sRGB D65 f32 RGBA, RGB [0,1], alpha exactly1.
 * No HDR/partial alpha/varying depth support. Never coerce them into this scope.
 * Refinement: optional tightly packed f32 [-1,1], same full source dimensions.
 * Input allocations MUST remain immutable, live and disjoint from all writes,
 * including callback writes, until destroy. Single-thread/non-reentrant handle.
 * No full output allocation in core. Caller owns private transactional sink:
 * reserve plan.sink_bytes, append successful row-major tiles exactly once,
 * publish only after finish success, otherwise discard ALL preceding tiles.
 * Pointer validation cannot establish live allocations/immutability/provenance.
 * Callback must not unwind, free/mutate inputs, destroy/reenter job or output.
 * Every failed create leaves out_job/out_plan unchanged. Every failed tile
 * leaves output unchanged. Processing failure poisons job; malformed pointer
 * spans rejected before processing need not poison it. Cancellation uses status4.
 * Status: 0 success; 1 ABI; 2 settings; 3 unsupported/invalid pixel;
 * 4 cancelled; 5 resource; 6 caught panic; 7 numerical result; 8 job state.
 */
typedef struct lrt_lens_cohort_job lrt_lens_cohort_job;
typedef struct {
    uint32_t abi_version;        /* exactly2 */
    uint32_t struct_size;        /* sizeof this struct */
    uint32_t aperture;           /* original0 disk,1 rim,2 pentagon,3 octagon,4 cat-eye */
    float max_radius_px;         /* [0,128], SOURCE grid */
    float focus_near;
    float focus_far;
    float depth_falloff;
    float occlusion_tolerance;
    float rotation_radians;
    float manual_depth;         /* explicit single f32 constant, [0,1] */
    uint32_t manual_depth_ack;   /* exactly1; host authenticates user acknowledgement */
} lrt_lens_cohort_settings_v2;
typedef struct {
    uint32_t abi_version;
    uint32_t struct_size;
    uint64_t max_fft_butterflies;
    uint64_t max_kernel_quadrature_evals;
    uint64_t max_classification_pixels;
    uint64_t max_support_probes;
    uint64_t max_direct_pairs;          /* <=250000000, residual+repair */
    uint64_t reserved_repair_pairs;     /* consumed only by exact gather repair */
    uint64_t max_scratch_bytes;         /* core-owned plan+scratch, not borrowed source */
    uint64_t max_sink_bytes;            /* external private sink, required16*N */
} lrt_lens_cohort_budget_v2;
typedef struct {
    uint32_t abi_version;
    uint32_t struct_size;
    uint32_t math_identity;             /* 0x00020001 */
    uint32_t non_delta_cohort_count;
    uint64_t width;
    uint64_t height;
    uint64_t source_pixels;
    uint64_t validation_pixels;
    uint64_t classification_pixels;
    uint64_t repeated_halo_classification_pixels;
    uint64_t tile_width;                /*254 or image width, whichever smaller */
    uint64_t tile_height;               /*254 or image height, whichever smaller */
    uint64_t tile_columns;
    uint64_t tile_count;
    uint64_t fft_width;
    uint64_t fft_height;
    uint64_t kernel_quadrature_evals;
    uint64_t fft_transform_count;
    uint64_t fft_butterflies;
    uint64_t residual_emitters;
    uint64_t residual_candidate_pairs;
    uint64_t residual_quadrature_upper_bound;
    uint64_t support_probe_upper_bound;
    uint64_t repair_candidate_reservation;
    uint64_t direct_pair_upper_bound;
    uint64_t owned_plan_bytes;
    uint64_t required_scratch_bytes;     /* includes owned_plan_bytes */
    uint64_t borrowed_source_bytes;
    uint64_t borrowed_refinement_bytes;
    uint64_t sink_bytes;
    uint64_t output_tile_bytes;
} lrt_lens_cohort_plan_v2;
uint32_t lrt_lens_cohort_abi(void);
uint32_t lrt_lens_cohort_math_identity(void);
int32_t lrt_lens_cohort_create_v2(
    const float *source, size_t source_len,
    const float *refinement, size_t refinement_len,
    size_t width, size_t height,
    lrt_lens_cohort_settings_v2 settings, lrt_lens_cohort_budget_v2 budget,
    lrt_lens_cohort_job **out_job, lrt_lens_cohort_plan_v2 *out_plan,
    int32_t (*cancel)(void *), void *context);
int32_t lrt_lens_cohort_render_next_v2(
    lrt_lens_cohort_job *job, uint64_t tile_index,
    float *output, size_t output_len, int32_t (*cancel)(void *), void *context);
int32_t lrt_lens_cohort_finish_v2(const lrt_lens_cohort_job *job);
void lrt_lens_cohort_destroy_v2(lrt_lens_cohort_job *job);
#ifdef __cplusplus
}
#endif
#endif
