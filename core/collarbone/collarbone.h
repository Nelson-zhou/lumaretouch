/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_COLLARBONE_H
#define LRT_COLLARBONE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Encoded working-sRGB-D65 SDR float32 HWC/HW coverage.
 * Points/width fractions are double; counts uint32; statistics uint64.
 * Normalized points map x*source_width-.5, y*source_height-.5 (pixel-edge domain).
 * Width is HALF-WIDTH / min(source_width,source_height), 4..256 source pixels.
 * 1..2 curves, each 3..8 points; widths_len==counts_len. No absent-side synthesis.
 * The real source window contains output ROI plus actual near/far sample/filter
 * halo. No fake padding. Rectangles use integer full-source x,y and dimensions.
 * The signed field is amount-independent, natural-log gain, abs<=0.12+1e-8.
 * Every observed neighborhood and output pixel requires supplied owned coverage.
 * Stats[8]: reviewed band, covered band, source-border refusal, unsupported sample,
 * unreliable source, insufficient/ambiguous signal, admitted pixels, overlap ties.
 * Status: 0 success; 1 ABI; 2 settings/geometry; 3 pixels/numerics; 4 cancelled;
 * 5 resource; 6 contained panic. Empty evidence is reported in stats, not invented.
 * Discard ALL output after nonzero status; caller publishes only after success.
 * Live aligned allocations, immutable inputs, exclusive nonoverlapping outputs.
 * Callback must not unwind, reenter or mutate buffers; foreign faults not caught.
 * No authentication of semantic ownership or review is possible from raw arrays. */
uint32_t lrt_collarbone_abi(void);
int32_t lrt_collarbone_prepare_v1(
    const float *reference, size_t reference_len, const float *coverage, size_t coverage_len,
    size_t source_width, size_t source_height,
    size_t window_x, size_t window_y, size_t window_width, size_t window_height,
    const double *points, size_t points_len, const uint32_t *counts, size_t counts_len,
    const double *widths, size_t widths_len,
    size_t output_x, size_t output_y, size_t output_width, size_t output_height,
    float *field, size_t field_len, uint64_t *stats, size_t stats_len,
    int32_t (*cancel)(void *), void *context);
int32_t lrt_collarbone_compose_v1(
    const float *current, size_t current_len,
    size_t tile_x, size_t tile_y, size_t tile_width, size_t tile_height,
    const float *field, size_t field_len,
    size_t field_x, size_t field_y, size_t field_width, size_t field_height,
    size_t source_width, size_t source_height, float amount,
    float *output, size_t output_len, int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
