/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original source contract, AUTHORED / UNRUN. Native float32, element lengths.
 * Not a hardware ABI validation report. Read ABI.md before calling. */
#ifndef LRT_LIGHT_GLOW_H
#define LRT_LIGHT_GLOW_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
  uint32_t struct_bytes, abi_version, math_identity, mode, radius_px, reserved;
  float strength, threshold, exposure_ev, scattering, hue_deg, saturation,
        lightness, reserved_f32;
} LrtLightGlowSettings;
typedef struct {
  uint32_t struct_bytes, full_width, full_height, tile_x, tile_y,
           tile_width, tile_height, reserved;
} LrtLightGlowGeometry;
typedef struct {
  uint32_t struct_bytes, region_x, region_y, region_width, region_height,
           halo_px, channels, reserved;
  uint64_t input_floats, output_floats, coverage_floats, scratch_bytes, required_bytes;
} LrtLightGlowPlan;
typedef int32_t (*LrtLightGlowCancel)(void *user);
uint32_t lrt_light_glow_abi(void);
uint32_t lrt_light_glow_math(void);
uint32_t lrt_light_glow_settings_size(void);
uint32_t lrt_light_glow_geometry_size(void);
uint32_t lrt_light_glow_plan_size(void);
int32_t lrt_light_glow_plan(const LrtLightGlowSettings *, const LrtLightGlowGeometry *,
                          uint64_t max_work_bytes, LrtLightGlowPlan *);
int32_t lrt_light_glow_render(const LrtLightGlowSettings *, const LrtLightGlowGeometry *,
                            const float *input, uint64_t input_floats,
                            float *output, uint64_t output_floats,
                            float *coverage, uint64_t coverage_floats,
                            uint64_t max_work_bytes, LrtLightGlowCancel, void *user);
#ifdef __cplusplus
}
#endif
#endif
