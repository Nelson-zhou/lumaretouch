/** Export intent only: Original is resolved by the authenticated engine per document. */
export interface ExportCombo {
  format: string;
  tiffCompression?: string;
}

export function isOriginalExportFormat(format: string): boolean {
  return format === "original";
}

export function is16BitExportFormat(format: string): boolean {
  return ["png", "tif", "tiff"].includes(format);
}

/** Original never inherits the remembered explicit-format precision preference. */
export function exportBitDepthForIntent(bitDepth16: boolean, format: string): 8 | 16 | undefined {
  return isOriginalExportFormat(format) ? undefined : bitDepth16 ? 16 : 8;
}

/** Enabling explicit 16-bit preserves PNG/TIFF; Original remains a policy intent. */
export function reconcileExportFormat(bitDepth16: boolean, format: string): string {
  return bitDepth16 && !isOriginalExportFormat(format) && !is16BitExportFormat(format) ? "tif" : format;
}

/** The explicit 16-bit writers cannot carry GPS; keep the remembered preference. */
export function exportGpsForDepth(bitDepth16: boolean, rememberedGps: boolean): boolean {
  return !bitDepth16 && rememberedGps;
}

/** Do not hide GPS conflicts for Original: any resolved RGB16 entry rejects the batch. */
export function exportGpsForIntent(bitDepth16: boolean, format: string, rememberedGps: boolean): boolean {
  return isOriginalExportFormat(format) ? rememberedGps : exportGpsForDepth(bitDepth16, rememberedGps);
}

/** Original sends a TIFF preference, applicable only to engine-resolved TIFF entries. */
export function reconcileExportCombo(bitDepth16: boolean, format: string,
                                     tiffCompression: string, compressionChosen = true): ExportCombo {
  const selected = reconcileExportFormat(bitDepth16, format);
  return { format: selected, tiffCompression: ["tif", "tiff"].includes(selected)
    || (isOriginalExportFormat(selected) && compressionChosen) ? tiffCompression : undefined };
}
