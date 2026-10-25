// SPDX-License-Identifier: GPL-3.0-or-later
import {SELECTION_LIMITS, validSelectionPng, type SelectionPng} from './model.ts';
function checksum(bytes: Uint8Array, start: number, end: number): number {
  let crc = 0xffffffff;
  for (let i = start; i < end; i++) {
    crc ^= bytes[i]; for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
/** Verify the actual encoded PNG, not a URL, filename, canvas illustration or claimed digest. */
export async function verifySelectionImage(image: SelectionPng): Promise<boolean> {
  try {
    if (!validSelectionPng(image)) return false;
    const raw = atob(image.base64); if (btoa(raw) !== image.base64 || raw.length > SELECTION_LIMITS.imageBytes) return false;
    const bytes = Uint8Array.from(raw, char => char.charCodeAt(0)), view = new DataView(bytes.buffer);
    if (bytes.length < 57 || ![137, 80, 78, 71, 13, 10, 26, 10].every((v, i) => bytes[i] === v)) return false;
    let position = 8, header = false, data = false, dataEnded = false, ended = false;
    while (position + 12 <= bytes.length) {
      const size = view.getUint32(position), end = position + size + 12;
      if (end > bytes.length || checksum(bytes, position + 4, end - 4) !== view.getUint32(end - 4)) return false;
      const kind = String.fromCharCode(...bytes.subarray(position + 4, position + 8));
      if (!/^[A-Za-z]{2}[A-Z][A-Za-z]$/.test(kind)) return false;
      if (!header) {
        if (kind !== 'IHDR' || size !== 13 || view.getUint32(position + 8) !== image.width || view.getUint32(position + 12) !== image.height
          || bytes[position + 16] !== 8 || ![0, 2, 4, 6].includes(bytes[position + 17])
          || bytes[position + 18] || bytes[position + 19] || bytes[position + 20]) return false;
        header = true;
      } else if (kind === 'IDAT') {if (dataEnded) return false; data = data || size > 0;}
      else if (kind === 'IEND') {if (size || !data || end !== bytes.length) return false; ended = true; break;}
      else {
        if (!/^[a-z]/.test(kind) || ['acTL', 'fcTL', 'fdAT'].includes(kind)) return false;
        if (data) dataEnded = true;
      }
      position = end;
    }
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return ended && Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') === image.sha256;
  } catch {return false;}
}
export const selectionImageUrl = (image: SelectionPng): string => `data:image/png;base64,${image.base64}`;
