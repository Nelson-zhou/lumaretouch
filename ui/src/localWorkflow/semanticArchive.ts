// SPDX-License-Identifier: GPL-3.0-or-later
/** Authenticated by the engine, then rechecked at preflight. No UI value is authority. */
export interface SemanticArchive {
  path: string; file_bytes: number; file_sha256: string; intent_sha256: string;
  /** Exact canonical text, not a Number-round-tripped object. */
  portable_intent_json: string;
}
export interface SemanticIntent {
  version: 1; algorithm: string; enabled: boolean; mode: 'extreme' | 'harmonious'; strengths: number[];
  offset_policy: 'recompute-then-user-offset-v1'; class_policy: 'require-requested-support-v1';
  reference: {asset_id: string; render_sha256: string; source: {sha256: string; width: number; height: number}; [key: string]: unknown};
  groups: {id: string; enabled: boolean; offsets: number[]}[];
}
const HASH = /^[a-f0-9]{64}$/;
const CLASSES = ['global', 'background', 'hair', 'body_skin', 'face_skin', 'clothes', 'others'];
export function semanticIntent(archive: SemanticArchive): SemanticIntent | null {
  try {
    const value = JSON.parse(archive.portable_intent_json) as SemanticIntent;
    if (!value || value.version !== 1 || value.algorithm !== 'semantic-oklab-log-ot-pchip-hsv8-v1' || typeof value.enabled !== 'boolean'
        || !['extreme', 'harmonious'].includes(value.mode) || value.offset_policy !== 'recompute-then-user-offset-v1'
        || value.class_policy !== 'require-requested-support-v1' || !Array.isArray(value.strengths) || value.strengths.length !== 3
        || value.strengths.some(n => typeof n !== 'number' || !Number.isFinite(n) || n < 0 || n > 200)
        || !value.reference || !HASH.test(value.reference.asset_id) || !HASH.test(value.reference.render_sha256)
        || !value.reference.source || !HASH.test(value.reference.source.sha256)
        || !Array.isArray(value.groups) || !value.groups.length || value.groups.length > 7
        || new Set(value.groups.map(g => g.id)).size !== value.groups.length || !value.groups.some(g => g.id === 'global')
        || value.groups.some(g => !CLASSES.includes(g.id) || typeof g.enabled !== 'boolean' || !Array.isArray(g.offsets)
          || g.offsets.length !== 50 || g.offsets.some(n => typeof n !== 'number' || !Number.isFinite(n)))) return null;
    return value;
  } catch {return null;}
}
export function checkedSemanticArchive(value: unknown): SemanticArchive | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const row = value as SemanticArchive;
  if (Object.keys(row).sort().join(',') !== 'file_bytes,file_sha256,intent_sha256,path,portable_intent_json'
      || typeof row.path !== 'string' || !row.path.startsWith('/') || !/\.lrtcolour$/i.test(row.path)
      || row.path.length > 4096 || /[\u0000-\u001f\u007f]/.test(row.path)
      || !Number.isSafeInteger(row.file_bytes) || row.file_bytes < 1 || row.file_bytes > 256*1024*1024 + 128*1024
      || typeof row.file_sha256 !== 'string' || !HASH.test(row.file_sha256)
      || typeof row.intent_sha256 !== 'string' || !HASH.test(row.intent_sha256)
      || typeof row.portable_intent_json !== 'string' || new TextEncoder().encode(row.portable_intent_json).length > 64*1024
      || !semanticIntent(row)) return null;
  return structuredClone(row);
}
export function sameSemanticArchive(a: unknown, b: unknown): boolean {
  const left = checkedSemanticArchive(a), right = checkedSemanticArchive(b);
  return !!left && !!right && (Object.keys(left) as (keyof SemanticArchive)[]).every(key => left[key] === right[key]);
}
