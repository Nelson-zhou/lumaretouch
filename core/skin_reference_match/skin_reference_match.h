/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_SKIN_REFERENCE_MATCH_H
#define LRT_SKIN_REFERENCE_MATCH_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN, ABI1. Input/output RGB is contiguous float32 HWC3,
 * encoded working-sRGB-D65 SDR [0,1]; numerical work uses linear RGB.
 * Coverage is contiguous float32 HW [0,1]. All lengths count elements.
 * Reference and target are INDEPENDENT actual immutable same-photo source ROIs.
 * They have independent dimensions; there are no correspondences/resizing.
 * Host must authenticate source, selected reference face, reviewed target face
 * OR body support, ownership, exclusion of reference face, and stable cache keys.
 * This core does NOT select brightest faces or segment people/body skin.
 *
 * limits[2]: maximum abs ln(Y) shift [0,ln(2)], maximum Euclidean norm
 * of [ln(R/G),ln(B/G)] shift [0,.35]. Fit ALWAYS requires reliable evidence.
 * transform[4]: [1, dLogY, dLogRG, dLogBG], immutable after successful fit.
 * diagnostics[24]: [1, ref_count, target_count, ref_robust_weight,
 * target_robust_weight, ref_effective_n, target_effective_n,
 * ref_centre[3], target_centre[3], ref_initial_MAD[3], target_initial_MAD[3],
 * raw_shift[3], bound_flags, min_retained_weight_fraction]. Axes are logY,RG,BG.
 * bound_flags: bit0 brightness bounded, bit1 chroma bounded, bit2 tiny shift zeroed.
 * Fits use full source support and fixed streaming histograms, not ROI downsampling.
 * Ref+target <=32M pixels; dimensions 1..65536; accounted bytes
 * 16*(refN+targetN)+262144 <=2GiB; native histogram allocation 147456 bytes.
 *
 * apply takes CURRENT pixels, not source pixels; no halo/resizing/smoothing.
 * One fit can be applied to arbitrary native-resolution tiles, each <=1048576
 * pixels; 40*tileN+4096 <=64MiB. Supplied coverage is the reviewed effective
 * permission for this target tile. No inferred ownership or pixel replacement.
 * amount=0: missing coverage and transform may each use (NULL,0). Supplied
 * inputs still validate; valid current output is a bit-exact copy, including -0.
 * amount>0 requires both. All-zero valid shifts and zero support are also exact.
 * All application uses a common gamut-feasible linear RGB interpolation, never
 * independent channel clipping; unreliable current black/white is unchanged.
 *
 * Status: 0 success; 1 ABI/length/dimensions/overlap; 2 settings; 3 invalid
 * pixels/numerical refusal; 4 cancellation; 5 resource admission/allocation;
 * 6 caught panic; 7 insufficient reference; 8 insufficient target;
 * 9 excessive dispersion/low retained evidence; 10 invalid transform.
 * All nonzero returns leave caller outputs untouched. Two fit arrays are
 * published at success with no fallible operation between copies, NOT atomic
 * synchronization for concurrent readers or protection against process failure.
 * Output ranges must overlap no supplied input or each other. Read-only inputs
 * may overlap. Caller owns live valid allocations, immutable inputs, exclusive
 * outputs and callback lifetime. Callback must not unwind, reenter, or mutate
 * buffers. The final publication copy cannot be canceled. */
uint32_t lrt_skin_reference_match_abi(void);
int32_t lrt_skin_reference_match_fit_v1(
    const float *reference, size_t reference_len,
    const float *reference_coverage, size_t reference_coverage_len, size_t reference_width, size_t reference_height,
    const float *target, size_t target_len,
    const float *target_coverage, size_t target_coverage_len, size_t target_width, size_t target_height,
    const double *limits, size_t limits_len,
    double *transform_out, size_t transform_len,
    double *diagnostics_out, size_t diagnostics_len,
    int32_t (*cancel)(void *), void *context);
int32_t lrt_skin_reference_match_apply_v1(
    const float *current, size_t current_len, const float *coverage, size_t coverage_len,
    size_t width, size_t height, const double *transform, size_t transform_len, float amount,
    float *output, size_t output_len, int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
