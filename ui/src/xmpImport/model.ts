import type {EffectiveSourceProof} from '../people/transferProof';

/** XMP is an input format, not an Adobe rendering engine or executable recipe. */
export const XMP_MODE = 'native-parameter-adaptation-v1' as const;
export const XMP_LIMITS = {sourceBytes: 1024 * 1024, properties: 512, edge: 640, pngBytes: 1024 * 1024, base64: 1398104} as const;
export type XmpAdaptationId = 'exposure' | 'point_curves';
export type XmpReport = {
  version: 1; source_sha256: string; report_sha256: string; filename: string; byte_length: number;
  process_version: string | null; camera_raw_version: string | null;
  properties: {name: string; status: 'adaptable' | 'unsupported' | 'metadata' | 'invalid'; value: unknown; reason: string}[];
  adaptations: {id: XmpAdaptationId; title: string; module: string; reason: string}[];
  warnings: string[]; can_import: boolean;
};
export type XmpAck = {source_sha256: string; report_sha256: string; mode: typeof XMP_MODE; selected: XmpAdaptationId[]};
export type XmpSummary = {version: 1; source_sha256: string; filename: string; selected: XmpAdaptationId[]; report: XmpReport; read_only_summary: true};
export type XmpPreview = {mime: 'image/png'; width: number; height: number; sha256: string; base64: string};
export type XmpTransfer = {
  version: 1; document_id: string; revision: string; xmp_sha256: string; source_proof: EffectiveSourceProof;
  before_sha256: string; candidate_sha256: string; before_people_sha256: string; candidate_people_sha256: string;
  source_size: [number, number]; before_output_size: [number, number]; after_output_size: [number, number];
  before: XmpPreview; after: XmpPreview;
};
/** These are the PNG hashes, not the similarly named recipe/graph hashes above. */
export type XmpReviewAck = {source_sha256: string; report_sha256: string; before_sha256: string; after_sha256: string};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const text = (v: unknown, max = 131072): v is string => typeof v === 'string' && Array.from(v).length <= max;
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const size = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2 && v.every(integer);
const moduleFor: Record<XmpAdaptationId, string> = {exposure: 'lnx.exposure.v1', point_curves: 'lnx.curves.v1'};
const adaptationId = (v: unknown): v is XmpAdaptationId => v === 'exposure' || v === 'point_curves';
function boundedValue(v: unknown, depth = 0): boolean {
  if (depth > 32) return false;
  if (v === null || typeof v === 'boolean') return true;
  if (typeof v === 'string') return text(v, 65536);
  if (typeof v === 'number') return Number.isFinite(v);
  if (Array.isArray(v)) return v.length <= 4096 && v.every(item => boundedValue(item, depth + 1));
  return object(v) && Object.keys(v).length <= 4096 && Object.entries(v).every(([key, item]) => text(key, 1026) && boundedValue(item, depth + 1));
}
export function validXmpReport(v: unknown): v is XmpReport {
  if (!object(v) || !keys(v, ['version', 'source_sha256', 'report_sha256', 'filename', 'byte_length', 'process_version', 'camera_raw_version', 'properties', 'adaptations', 'warnings', 'can_import'])
    || v.version !== 1 || !hash(v.source_sha256) || !hash(v.report_sha256) || !text(v.filename, 255) || !v.filename || /[\\/\0]/.test(v.filename)
    || !integer(v.byte_length) || v.byte_length > XMP_LIMITS.sourceBytes || typeof v.can_import !== 'boolean'
    || !(v.process_version === null || text(v.process_version, 65536)) || !(v.camera_raw_version === null || text(v.camera_raw_version, 65536))
    || !Array.isArray(v.properties) || v.properties.length > XMP_LIMITS.properties
    || !Array.isArray(v.adaptations) || v.adaptations.length > 2
    || !Array.isArray(v.warnings) || v.warnings.length > 256 || !v.warnings.every(w => text(w, 1048576))) return false;
  if (!v.properties.every(p => object(p) && keys(p, ['name', 'status', 'value', 'reason']) && text(p.name, 1026) && !!p.name
    && ['adaptable', 'unsupported', 'metadata', 'invalid'].includes(String(p.status)) && boundedValue(p.value) && text(p.reason))) return false;
  const seen = new Set<string>();
  for (const a of v.adaptations) {
    if (!object(a) || !keys(a, ['id', 'title', 'module', 'reason']) || !adaptationId(a.id) || seen.has(a.id)
      || a.module !== moduleFor[a.id] || !text(a.title, 512) || !a.title || !text(a.reason)) return false;
    seen.add(a.id);
  }
  return (!v.can_import || (v.process_version === '11.0' && seen.size > 0)) && JSON.stringify(v).length <= 4 * 1024 * 1024;
}
export function validXmpAck(v: unknown, report?: XmpReport): v is XmpAck {
  return object(v) && keys(v, ['source_sha256', 'report_sha256', 'mode', 'selected']) && hash(v.source_sha256) && hash(v.report_sha256)
    && v.mode === XMP_MODE && Array.isArray(v.selected) && v.selected.length > 0 && v.selected.length <= 2
    && v.selected.every(adaptationId) && new Set(v.selected).size === v.selected.length
    && (!report || (validXmpReport(report) && report.can_import && v.source_sha256 === report.source_sha256
      && v.report_sha256 === report.report_sha256 && v.selected.every(id => report.adaptations.some(a => a.id === id))));
}
export function validXmpSummary(v: unknown, scope?: string[]): v is XmpSummary {
  if (!object(v) || !keys(v, ['version', 'source_sha256', 'filename', 'selected', 'report', 'read_only_summary'])
    || v.version !== 1 || v.read_only_summary !== true || !validXmpReport(v.report)
    || v.source_sha256 !== v.report.source_sha256 || v.filename !== v.report.filename
    || !validXmpAck({source_sha256: v.source_sha256, report_sha256: v.report.report_sha256, mode: XMP_MODE, selected: v.selected}, v.report)) return false;
  const selected = v.selected as XmpAdaptationId[];
  return !scope || (scope.length === selected.length && selected.every(id => scope.includes(moduleFor[id])));
}
function sourceProof(v: unknown, dimensions: [number, number]): v is EffectiveSourceProof {
  if (!object(v) || !keys(v, ['asset_sha256', 'original_sha256', 'creative_source']) || !hash(v.asset_sha256) || !hash(v.original_sha256)) return false;
  const c = v.creative_source;
  return c === null ? v.asset_sha256 === v.original_sha256 : object(c) && keys(c, ['sha256', 'width', 'height'])
    && c.sha256 === v.asset_sha256 && c.width === dimensions[0] && c.height === dimensions[1];
}
function preview(v: unknown, output: [number, number]): v is XmpPreview {
  return object(v) && keys(v, ['mime', 'width', 'height', 'sha256', 'base64']) && v.mime === 'image/png' && hash(v.sha256)
    && integer(v.width) && integer(v.height) && v.width <= XMP_LIMITS.edge && v.height <= XMP_LIMITS.edge
    && v.width <= output[0] && v.height <= output[1] && Math.abs(v.width * output[1] - v.height * output[0]) <= Math.max(...output)
    && typeof v.base64 === 'string' && v.base64.length <= XMP_LIMITS.base64 && v.base64.startsWith('iVBOR')
    && v.base64.length % 4 === 0 && /^[A-Za-z0-9+/]+={0,2}$/.test(v.base64);
}
export function validXmpTransfer(v: unknown, documentId: string, revision: string | undefined, sourceSha: string): v is XmpTransfer {
  return object(v) && keys(v, ['version', 'document_id', 'revision', 'xmp_sha256', 'source_proof', 'before_sha256', 'candidate_sha256',
    'before_people_sha256', 'candidate_people_sha256', 'source_size', 'before_output_size', 'after_output_size', 'before', 'after'])
    && v.version === 1 && v.document_id === documentId && !!documentId && typeof v.revision === 'string'
    && /^\d{1,20}$/.test(v.revision) && BigInt(v.revision) <= 18446744073709551615n && v.revision === revision
    && hash(v.xmp_sha256) && v.xmp_sha256 === sourceSha && hash(v.before_sha256) && hash(v.candidate_sha256)
    && hash(v.before_people_sha256) && hash(v.candidate_people_sha256) && size(v.source_size)
    && sourceProof(v.source_proof, v.source_size) && size(v.before_output_size) && size(v.after_output_size)
    && preview(v.before, v.before_output_size) && preview(v.after, v.after_output_size);
}
export function xmpReviewKey(token: string, value: XmpTransfer, report: XmpReport): string {
  return JSON.stringify([token, value.document_id, value.revision, value.xmp_sha256, report.report_sha256, value.source_proof,
    value.before_sha256, value.candidate_sha256, value.before_people_sha256, value.candidate_people_sha256,
    value.source_size, value.before_output_size, value.after_output_size, value.before.sha256, value.after.sha256]);
}
export function xmpReviewAck(value: XmpTransfer, report: XmpReport): XmpReviewAck {
  return {source_sha256: value.xmp_sha256, report_sha256: report.report_sha256, before_sha256: value.before.sha256, after_sha256: value.after.sha256};
}
export function validXmpReviewAck(v: unknown): v is XmpReviewAck {
  return object(v) && keys(v, ['source_sha256', 'report_sha256', 'before_sha256', 'after_sha256']) && Object.values(v).every(hash);
}
/** Hash the decoded PNG bytes; a URL, load event, or shape check alone is not proof. */
export async function verifyXmpPreview(value: XmpPreview): Promise<boolean> {
  try {
    if (!preview(value, [value.width, value.height])) return false;
    const bytes = Uint8Array.from(atob(value.base64), char => char.charCodeAt(0));
    if (bytes.length > XMP_LIMITS.pngBytes || bytes.length < 33 || ![137, 80, 78, 71, 13, 10, 26, 10].every((n, i) => bytes[i] === n)) return false;
    const view = new DataView(bytes.buffer);
    if (view.getUint32(8) !== 13 || view.getUint32(12) !== 0x49484452 || view.getUint32(16) !== value.width || view.getUint32(20) !== value.height) return false;
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('') === value.sha256;
  } catch {return false;}
}
