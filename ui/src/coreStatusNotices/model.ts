/** Read-only projection of an accepted engine_status snapshot. No log scraping,
 * commands, inferred CPU, inferred ICC absence, or independent polling owner. */
type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
const projectIdentity = (value: unknown): string | null => {
  const project = record(value);
  if (project.open === false && project.project_id === null && project.path === null) return 'unmanaged';
  if (project.open !== true || !nonempty(project.project_id) || !nonempty(project.path)) return null;
  return JSON.stringify([project.project_id, project.path]);
};
export const boundedText = (value: string, max = 240): string => {
  const clean = value.replace(/[\u0000-\u001f\u007f]/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
};

export interface CoreStatusView {
  loadId: string;
  device: string | null;
  fallback: string | null;
  fallbackReported: boolean;
  notes: string[];
  resources: {label: string; bytes: number}[];
}

const RESOURCE_FIELDS = [
  ['bytes_filter', '滤波缓存'], ['bytes_bands', '分带缓存'],
  ['bytes_light', '光影图层'], ['bytes_effect_recovery', '效果恢复'],
  ['bytes_manual_liquify', '手动液化'], ['bytes_deform', '形变图层'],
  ['bytes_lut', '色彩查找表'],
] as const;

/** Fail closed on torn image/session/report snapshots and missing identity. */
export function currentImageFacts(value: unknown): CoreStatusView | null {
  const status = record(value), image = record(status.image);
  const loadId = image.load_id, doc = record(record(status.doc_report).doc_state);
  if (status.engine_alive !== true || !nonempty(loadId) ||
      record(image.doc_state).document_id !== loadId || doc.document_id !== loadId) return null;
  const session = record(status.session);
  // session_state is the existing atomic bridge between a load and a project:
  // its doc_state and project are emitted together. Successful project creation
  // can retain this same load; no fresh image_ready is required or fabricated.
  const sessionProject = projectIdentity(session.project);
  // Before any project_* event, native's separate project slot is explicitly
  // null. Only the session's explicit unmanaged receipt can bridge that case.
  const project = status.project === null && sessionProject === 'unmanaged'
    ? sessionProject : projectIdentity(status.project);
  if (project === null || project !== sessionProject ||
      session.current !== image.doc || session.index !== image.session_index ||
      record(session.doc_state).document_id !== loadId) return null;
  const notes = Array.isArray(image.notes) ? image.notes.filter(nonempty) : [];
  // The decoder's explicit statements are the evidence, not missing fields.
  // Put assumptions first so a long decode report cannot hide COLOR-002.
  const uniqueNotes = [...new Set(notes)];
  uniqueNotes.sort((a, b) => Number(b.includes('输入假设')) - Number(a.includes('输入假设')));
  return {
    loadId,
    device: nonempty(image.device) ? boundedText(image.device, 64) : null,
    fallback: nonempty(image.device_fallback) ? boundedText(image.device_fallback) : null,
    fallbackReported: image.device_fallback === null || nonempty(image.device_fallback),
    notes: uniqueNotes.slice(0, 8).map(note => boundedText(note)),
    resources: RESOURCE_FIELDS.flatMap(([key, label]) => {
      const bytes = image[key];
      return typeof bytes === 'number' && Number.isSafeInteger(bytes) && bytes >= 0 ? [{label, bytes}] : [];
    }),
  };
}
