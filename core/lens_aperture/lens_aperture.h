/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_LENS_APERTURE_H
#define LRT_LENS_APERTURE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* AUTHORED / UNRUN. Native float32 linear-sRGB D65 premultiplied RGBA.
 * Depth HW [0,1]: zero near, one far. Optional refinement HW [-1,1].
 * All arrays immutable, same complete source grid/revision. Lengths count floats.
 * Alpha [0,1]; finite signed RGB bounded by abs(RGB) <= 65504 * alpha.
 * Null refinement requires refinement_len=0. No other input may be null.
 * Every nonzero return leaves output unchanged; output overlaps no input.
 * Callback/context must stay live and cannot unwind or mutate/reenter buffers.
 * Host authenticates source/depth identities, performs full validation once and
 * retains immutable snapshots. Tile render also checks its entire source halo.
 * Status: 0 success, 1 ABI, 2 settings, 3 pixels, 4 cancelled, 5 resource,
 * 6 panic contained, 7 unrepresentable result. No feature-acceptance claim. */
typedef struct {
    /* 0 disk; 1 rim-weighted disk; 2 regular pentagon; 3 regular octagon;
     * 4 intersection of two disks. These are ORIGINAL kernels, not parity. */
    uint32_t aperture;
    float max_radius_px;         /* [0,128], radius in source-grid pixels */
    float focus_near;            /* [0,1], <= focus_far */
    float focus_far;             /* [0,1] */
    float depth_falloff;         /* [0.000001,1] */
    float occlusion_tolerance;   /* [0,1], farther tap visibility threshold */
    float rotation_radians;      /* [-pi,pi] */
} lrt_lens_aperture_settings_v1;

uint32_t lrt_lens_aperture_abi(void);
/* Bit k denotes implemented original kernel k, not tested product acceptance. */
uint32_t lrt_lens_aperture_kernel_mask_v1(void);
int32_t lrt_lens_aperture_validate_v1(
    const float *source, size_t source_len,
    const float *depth, size_t depth_len,
    const float *refinement, size_t refinement_len,
    size_t width, size_t height,
    int32_t (*cancel)(void *), void *context);
int32_t lrt_lens_aperture_render_tile_v1(
    const float *source, size_t source_len,
    const float *depth, size_t depth_len,
    const float *refinement, size_t refinement_len,
    size_t width, size_t height, size_t x, size_t y,
    size_t tile_width, size_t tile_height, lrt_lens_aperture_settings_v1 settings,
    float *output, size_t output_len, int32_t (*cancel)(void *), void *context);
#ifdef __cplusplus
}
#endif
#endif
