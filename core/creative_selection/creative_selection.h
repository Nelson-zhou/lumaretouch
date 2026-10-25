/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original creative-selection coverage ABI. AUTHORED / UNRUN.
 * All pointer spans must remain live, aligned and non-overlapping for the call.
 * No output or stats writes occur on errors. See docs/creative-selection/ABI.md.
 */
#ifndef LUMARETOUCH_CREATIVE_SELECTION_H
#define LUMARETOUCH_CREATIVE_SELECTION_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { LR_SELECTION_ABI_V1 = 1 };
enum { LR_SELECTION_RECTANGLE = 1, LR_SELECTION_ELLIPSE = 2,
       LR_SELECTION_LASSO = 3, LR_SELECTION_BRUSH = 4,
       LR_SELECTION_INVERT = 5 };
enum { LR_SELECTION_NEW = 0, LR_SELECTION_ADD = 1,
       LR_SELECTION_SUBTRACT = 2, LR_SELECTION_INTERSECT = 3 };
enum { LR_SELECTION_OK = 0, LR_SELECTION_ABI_ERROR = 1,
       LR_SELECTION_VALUE_ERROR = 2, LR_SELECTION_LIMIT_ERROR = 3,
       LR_SELECTION_CANCELLED = 4, LR_SELECTION_ALLOCATION_ERROR = 5,
       LR_SELECTION_PANIC_ERROR = 6 };

typedef struct { double x, y; } LrSelectionPointV1;
typedef struct {
    uint32_t kind, combine, point_offset, point_count;
    double x0, y0, x1, y1;
    double diameter, hardness, opacity;
} LrSelectionOperationV1;
typedef struct {
    uint32_t abi_version, struct_size, source_width, source_height;
    uint32_t operation_count, point_count, feather_radius, reserved;
    const LrSelectionOperationV1 *operations;
    const LrSelectionPointV1 *points;
} LrSelectionRecipeV1;
typedef struct { uint32_t x, y, width, height; } LrSelectionTileV1;
typedef struct {
    uint64_t max_working_bytes, max_output_pixels, max_work_units;
} LrSelectionLimitsV1;
typedef struct {
    uint64_t working_bytes, work_units, output_pixels;
} LrSelectionStatsV1;
typedef uint32_t (*LrSelectionCancelV1)(void *context);

uint32_t lr_selection_abi_version(void);
int32_t lr_selection_evaluate_v1(
    const LrSelectionRecipeV1 *recipe,
    const LrSelectionTileV1 *tile,
    const LrSelectionLimitsV1 *limits,
    LrSelectionCancelV1 cancel,
    void *cancel_context,
    float *output,
    uint64_t output_len,
    LrSelectionStatsV1 *stats);

/* A NULL limits pointer uses {67108864, 1048576, 100000000}.
 * NULL cancel disables cancellation; NULL stats omits stats.
 * output_len must equal width*height, without a stride or row padding.
 * Recipe v1 requires struct_size == sizeof(LrSelectionRecipeV1), reserved == 0.
 * This ABI returns authoritative source-grid samples, not display proxy data.
 */
#ifdef __cplusplus
}
#endif
#endif
