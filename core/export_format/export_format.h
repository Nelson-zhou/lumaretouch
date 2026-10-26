/* SPDX-License-Identifier: GPL-3.0-or-later
 * Original-format policy ABI 1. Source-only; authored fixtures are UNRUN.
 */
#ifndef LRT_EXPORT_FORMAT_H
#define LRT_EXPORT_FORMAT_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Containers: 0 unknown, 1 JPEG, 2 PNG, 3 TIFF, 4 WebP.
 * Source kind: 0 unknown, 1 bitmap, 2 RAW.
 * Variant: 0 unknown, 1 encoded, 2 creative bound to encoded ancestor.
 * single_frame: 0 not proven single, 1 authenticated single frame.
 * Capabilities bits 0..5: jpg8, png8, png16, tif8, tif16, webp8.
 * Other capability bits are forbidden.
 *
 * Return uint64 numerical bit fields (independent of machine byte order):
 *   0..7   status (0 success; 1..8 refusal, documented in README.md)
 *   8..15  codec ID (same IDs as container)
 *   16..23 precision (8 or 16)
 *   24..31 canonical extension ID (1 jpg, 2 png, 3 tif, 4 webp)
 *   32..35 option bits: quality, tiff_compression, GPS, target_size
 *   36..63 reserved zero
 * A refusal returns only status: there is no partial/fallback decision.
 */
uint32_t lrt_export_format_abi(void);
uint64_t lrt_export_format_resolve(uint32_t container, uint32_t source_kind,
    uint32_t precision, uint32_t single_frame, uint32_t variant,
    uint32_t capabilities);

#ifdef __cplusplus
}
#endif
#endif
