/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_CREATIVE_LAYERS_H
#define LRT_CREATIVE_LAYERS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_creative_layers_abi(void);
int32_t lrt_creative_validate_rgba(const float *input, size_t length,
                                 size_t width, size_t height);
int32_t lrt_creative_validate_mask(const float *input, size_t length,
                                 size_t width, size_t height);
int32_t lrt_creative_linearize_rgba(const float *input, float *output, size_t length);
int32_t lrt_creative_linearize_extended_rgba(const float *input, float *output, size_t length);
int32_t lrt_creative_encode_opaque_sdr_rgb(const float *input, float *output, size_t length);
int32_t lrt_creative_display_rgb8(const float *input, uint8_t *output,
                                size_t length, const float *matte);
int32_t lrt_creative_composite_tile(
    const float *source, size_t source_length, size_t source_width, size_t source_height,
    const float *backdrop, float *output, size_t tile_length, size_t tile_width, size_t tile_height,
    const double *inverse, double canvas_x, double canvas_y, float opacity, uint32_t mode,
    const float *mask, size_t mask_length);
#ifdef __cplusplus
}
#endif
#endif
