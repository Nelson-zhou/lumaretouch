// SPDX-License-Identifier: GPL-3.0-or-later
// Native spatial sampling, display-only RGB8. AUTHORED / UNRUN.
import {sourcePoint, type EyeSide, type Point, type RidgeSource} from './support';
export type SourceCrop = {rect: [number, number, number, number]; image: {mime: 'image/png'; width: number; height: number; sha256: string; base64?: string}};
export type SourceCrops = {version: 1; token: string; mapping: 'source_pixel_edges'; orientation: 'exif_normalized_once'; source_sha256: string;
  source_width: number; source_height: number; input_stage: 'source' | 'committed_repair'; snapshot_sha256: string;
  display_encoding: 'srgb_rgb8'; sampling: 'one_source_pixel_per_image_pixel'; eyes: Record<EyeSide, SourceCrop>};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, k: string[]) => Object.keys(v).sort().join('|') === [...k].sort().join('|');
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export const MAX_CROP_PNG_BYTES = 4 * 1024 * 1024;
export function validSourceCrops(v: unknown, source: RidgeSource): v is SourceCrops {
  if (!object(v) || !keys(v, ['version', 'token', 'mapping', 'orientation', 'source_sha256', 'source_width', 'source_height', 'input_stage', 'snapshot_sha256', 'display_encoding', 'sampling', 'eyes'])
    || v.version !== 1 || typeof v.token !== 'string' || !/^[a-f0-9]{32}$/.test(v.token) || v.mapping !== 'source_pixel_edges' || v.orientation !== 'exif_normalized_once'
    || v.display_encoding !== 'srgb_rgb8' || v.sampling !== 'one_source_pixel_per_image_pixel'
    || !['source', 'committed_repair'].includes(String(v.input_stage)) || !hash(v.snapshot_sha256)
    || !hash(v.source_sha256) || v.source_sha256 !== source.sha256 || v.source_width !== source.width || v.source_height !== source.height
    || ![source.width, source.height].every(n => Number.isSafeInteger(n) && n >= 2 && n <= 1_000_000)
    || !object(v.eyes) || !keys(v.eyes, ['left', 'right'])) return false;
  let pixels = 0;
  return Object.values(v.eyes).every(crop => {
    if (!object(crop) || !keys(crop, ['rect', 'image']) || !Array.isArray(crop.rect) || crop.rect.length !== 4
      || !crop.rect.every(n => Number.isSafeInteger(n)) || !object(crop.image)) return false;
    const [x, y, w, h] = crop.rect as number[], image = crop.image;
    pixels += w * h;
    return x >= 0 && y >= 0 && w >= 1 && h >= 1 && w <= 2048 && h <= 2048 && x + w <= source.width && y + h <= source.height
      && pixels <= 4_000_000 && keys(image, ['mime', 'width', 'height', 'sha256']) && image.mime === 'image/png'
      && image.width === w && image.height === h && hash(image.sha256);
  });
}
export async function sourceCropImage(value: unknown, crops: SourceCrops, side: EyeSide): Promise<SourceCrop | null> {
  try {
    if (!object(value) || !keys(value, ['kind', 'token', 'side', 'snapshot_sha256', 'image']) || value.kind !== 'eye_bag_source_image'
      || value.token !== crops.token || value.side !== side || value.snapshot_sha256 !== crops.snapshot_sha256 || !object(value.image)) return null;
    const image = value.image, expected = crops.eyes[side];
    if (!keys(image, ['mime', 'width', 'height', 'sha256', 'base64']) || image.mime !== 'image/png'
      || image.width !== expected.image.width || image.height !== expected.image.height || image.sha256 !== expected.image.sha256
      || typeof image.base64 !== 'string' || !image.base64.length || image.base64.length > Math.ceil(MAX_CROP_PNG_BYTES / 3) * 4) return null;
    const raw = atob(image.base64);
    if (raw.length < 33 || raw.length > MAX_CROP_PNG_BYTES || btoa(raw) !== image.base64) return null;
    const bytes = Uint8Array.from(raw, c => c.charCodeAt(0)), data = new DataView(bytes.buffer);
    if (![137,80,78,71,13,10,26,10].every((n, i) => bytes[i] === n) || data.getUint32(8) !== 13 || data.getUint32(12) !== 0x49484452
      || data.getUint32(16) !== image.width || data.getUint32(20) !== image.height || bytes[24] !== 8 || bytes[25] !== 2) return null;
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    if (Array.from(digest, n => n.toString(16).padStart(2, '0')).join('') !== image.sha256) return null;
    return {...expected, image: image as SourceCrop['image']};
  } catch {return null;}
}
/** Crop screen edges -> whole-source normalized edges. No pixel-center/w-1 ambiguity. */
export function cropSourcePoint(x: number, y: number, screen: {left: number; top: number; width: number; height: number}, crop: SourceCrop, source: RidgeSource): Point | null {
  const p = sourcePoint(x, y, screen); if (!p) return null;
  const [cx, cy, cw, ch] = crop.rect;
  return [(cx + p[0] * cw) / source.width, (cy + p[1] * ch) / source.height];
}
