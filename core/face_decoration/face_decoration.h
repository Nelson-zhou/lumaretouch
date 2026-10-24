/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef LRT_FACE_DECORATION_H
#define LRT_FACE_DECORATION_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t lrt_face_decoration_abi(void);
/* Source/output RGB float32, frame[6], support[width*height], marks[count*7].
   Output must not overlap inputs. See lib.rs for dimensions, bounds and codes. */
int32_t lrt_face_decoration_delta(const float *source, const float *frame,
    const float *support, size_t width, size_t height, const float *marks,
    size_t mark_count, float strength, float *output);
#ifdef __cplusplus
}
#endif
#endif
