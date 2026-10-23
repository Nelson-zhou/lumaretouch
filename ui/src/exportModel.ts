/** Preserve the selected lossless format and its applicable options. */
export interface ExportCombo {
  format: string;
  tiffCompression?: string;
}

export function is16BitExportFormat(format: string): boolean {
  return ["png", "tif", "tiff"].includes(format);
}

/** Enabling 16-bit preserves PNG/TIFF; JPEG/WebP explicitly fall back to TIFF. */
export function reconcileExportFormat(bitDepth16: boolean, format: string): string {
  return bitDepth16 && !is16BitExportFormat(format) ? "tif" : format;
}

/** The 16-bit writers cannot carry GPS; keep the stored 8-bit preference untouched. */
export function exportGpsForDepth(bitDepth16: boolean, rememberedGps: boolean): boolean {
  return !bitDepth16 && rememberedGps;
}

/** Never send TIFF-only compression to PNG, or silently reduce requested bit depth. */
export function reconcileExportCombo(bitDepth16: boolean, format: string,
                                     tiffCompression: string): ExportCombo {
  const selected = reconcileExportFormat(bitDepth16, format);
  return { format: selected, tiffCompression: ["tif", "tiff"].includes(selected) ? tiffCompression : undefined };
}
