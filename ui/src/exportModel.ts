/** Preserve the selected lossless compression; RGB16 only forces TIFF format. */
export interface ExportCombo {
  format: string;
  tiffCompression?: string;
}

/** 16-bit限定TIFF容器，压缩方案不偷偷覆盖用户选择。 */
export function reconcileExportCombo(bitDepth16: boolean, format: string,
                                     tiffCompression: string): ExportCombo {
  if (bitDepth16) {
    return { format: "tif", tiffCompression };
  }
  return { format, tiffCompression: ["tif", "tiff"].includes(format) ? tiffCompression : undefined };
}
