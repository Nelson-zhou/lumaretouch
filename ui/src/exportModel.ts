/**
 * P2-2（F11）：主导出页勾了「16-bit TIFF」，却仍按面板上的 format=jpg、且把默认的
 * tiffCompression=deflate 一起递上去——后端对 16-bit 只认「无压缩 TIFF」，于是这个
 * 可见选项一勾就必被拒，承诺的事反而做不成（"后台协议可用不代表主界面可达"）。
 *
 * 纯函数抽出来方便 node:test 钉住：切 16-bit 时同时把 format 收到 tif、压缩收到 none。
 */

export interface ExportCombo {
  format: string;
  tiffCompression: string;
}

/** 16-bit 母档直通只写无压缩 TIFF；非 16-bit 原样返回用户选的组合作用于其它字段。 */
export function reconcileExportCombo(bitDepth16: boolean, format: string,
                                     tiffCompression: string): ExportCombo {
  if (bitDepth16) {
    return { format: "tif", tiffCompression: "none" };
  }
  return { format, tiffCompression };
}
