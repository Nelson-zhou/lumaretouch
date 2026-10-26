// SPDX-License-Identifier: GPL-3.0-or-later
import {UPSCALE_LIMITS, validUpscalePng, type UpscalePng} from './model';

const decode = (base64: string): Uint8Array => {
  const raw = atob(base64);
  if (btoa(raw) !== base64) throw Error('图像不是规范 Base64 编码。');
  return Uint8Array.from(raw, character => character.charCodeAt(0));
};
function crc(bytes: Uint8Array, start: number, end: number): number {
  let value = 0xffffffff;
  for (let i = start; i < end; i++) {
    value ^= bytes[i];
    for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);
  }
  return (value ^ 0xffffffff) >>> 0;
}

/** Display evidence only. PNG bytes are never used as the HDR document source. */
export async function verifyUpscalePng(image: UpscalePng): Promise<boolean> {
  try {
    if (!validUpscalePng(image)) return false;
    const bytes = decode(image.base64), view = new DataView(bytes.buffer);
    if (bytes.length < 57 || bytes.length > UPSCALE_LIMITS.imageBytes
      || ![137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => bytes[i] === byte)) return false;
    let offset = 8, header = false, data = false, seenData = false, dataEnded = false, ended = false;
    while (offset + 12 <= bytes.length) {
      const length = view.getUint32(offset), end = offset + length + 12;
      if (end > bytes.length || crc(bytes, offset + 4, end - 4) !== view.getUint32(end - 4)) return false;
      const kind = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8));
      if (!/^[A-Za-z]{2}[A-Z][A-Za-z]$/.test(kind)) return false;
      if (!header) {
        if (kind !== 'IHDR' || length !== 13 || view.getUint32(offset + 8) !== image.width
          || view.getUint32(offset + 12) !== image.height || bytes[offset + 16] !== 8
          || ![2, 6].includes(bytes[offset + 17]) || bytes[offset + 18] || bytes[offset + 19] || bytes[offset + 20]) return false;
        header = true;
      } else if (kind === 'IDAT') {
        if (dataEnded) return false;
        seenData = true; data = data || length > 0;
      } else if (kind === 'IEND') {
        if (length || !data || end !== bytes.length) return false;
        ended = true; break;
      } else {
        if (!/^[a-z]/.test(kind) || ['acTL', 'fcTL', 'fdAT'].includes(kind)) return false;
        if (seenData) dataEnded = true;
      }
      offset = end;
    }
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return ended && Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') === image.sha256;
  } catch { return false; }
}

export const upscaleImageUrl = (image: UpscalePng): string => `data:image/png;base64,${image.base64}`;

