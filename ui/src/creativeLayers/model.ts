// SPDX-License-Identifier: GPL-3.0-or-later
/** UI transport types only. The host owns validated documents/history; Rust owns pixel rendering. */
export const CREATIVE_BLEND_MODES = ['normal', 'multiply', 'screen', 'lighten', 'darken'] as const;
export type CreativeBlend = typeof CREATIVE_BLEND_MODES[number];
export type CreativeAlignment = 'left' | 'hcenter' | 'right' | 'top' | 'vcenter' | 'bottom';
export interface CreativeTransform {
  x: number; y: number; scale_x: number; scale_y: number; rotation: number;
  flip_x: boolean; flip_y: boolean;
}
export interface CreativeLayer {
  id: string; kind: 'image' | 'group'; name: string; parent_id: string | null;
  asset_id: string | null; visible: boolean; locked: boolean; opacity: number;
  blend: CreativeBlend; mask_id: string | null; transform: CreativeTransform;
}
export interface CreativeDocument {
  schema: 1; document_id: string; source_uid: string; source_asset: string; revision: number;
  canvas: {width: number; height: number; dpi: number}; selected_id: string | null;
  /** Bottom-to-top sibling order, obtained by filtering on parent_id. */
  layers: CreativeLayer[];
}
export type CreativeCommand =
  | {action: 'select'; layer_id: string | null}
  | {action: 'rename'; layer_id: string; name: string}
  | {action: 'duplicate' | 'delete' | 'ungroup' | 'remove_mask'; layer_id: string}
  | {action: 'lock'; layer_id: string; locked: boolean}
  | {action: 'visibility'; layer_id: string; visible: boolean}
  | {action: 'group'; name: string; layer_ids: string[]}
  | {action: 'move'; layer_id: string; parent_id: string | null; index: number}
  | {action: 'opacity'; layer_id: string; opacity: number}
  | {action: 'blend'; layer_id: string; blend: CreativeBlend}
  | {action: 'transform'; layer_id: string; transform: Partial<CreativeTransform>}
  | {action: 'align'; layer_id: string; alignment: CreativeAlignment}
  | {action: 'canvas'; width: number; height: number; dpi: number}
  | {action: 'add_image'; asset_id: string; name: string}
  | {action: 'add_mask'; layer_id: string; mask_id: string};

export interface CreativeBinding {
  document_id: string; source_uid: string; ownership_token: string; expected_revision: number;
}
export interface CreativeRequest extends CreativeBinding {request_id: string}
export interface CreativePreview {
  document_id: string; source_uid: string; ownership_token: string; revision: number;
  render_id: string; url: string;
}
export interface CreativeAuthority {
  document: CreativeDocument; ownership_token: string; busy: boolean;
}
export type CreativeReceipt = CreativeRequest & (
  | {status: 'applied' | 'no_change'; revision: number; next_ownership_token?: string}
  | {status: 'rejected' | 'unknown'; message: string}
);
export interface CreativeHistory {
  can_undo: boolean; can_redo: boolean;
  /** True only when the host retains deleted layers AND referenced assets for undo. */
  recoverable_delete: boolean;
}
export interface CreativePorts {
  command?: (request: CreativeRequest & {command: CreativeCommand}) => Promise<CreativeReceipt>;
  /** Decode/intern real file bytes and commit add_image as one host-owned operation. */
  importImage?: (request: CreativeRequest & {file: File}) => Promise<CreativeReceipt>;
  /** Must decode an actual raster mask; no generated placeholder or opaque ID fabrication. */
  attachMask?: (request: CreativeRequest & {file: File; layer_id: string}) => Promise<CreativeReceipt>;
  removeMask?: (request: CreativeRequest & {layer_id: string}) => Promise<CreativeReceipt>;
  undo?: (request: CreativeRequest) => Promise<CreativeReceipt>;
  redo?: (request: CreativeRequest) => Promise<CreativeReceipt>;
  returnNew?: (request: CreativeRequest & {render_id: string}) => Promise<CreativeReceipt>;
  updateOriginal?: (request: CreativeRequest & {render_id: string}) => Promise<CreativeReceipt>;
  /** Query the ORIGINAL request. Never resend it or infer success from a changed revision. */
  reconcile?: (request: CreativeRequest) => Promise<CreativeReceipt>;
}

const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const positive = (v: unknown): v is number => finite(v) && v > 0;
const positiveInt = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) > 0;
export const validRevision = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;

/** Reject malformed snapshots instead of manufacturing a usable-looking document. */
export function checkedCreativeDocument(value: unknown): CreativeDocument {
  if (!record(value) || value.schema !== 1 || !text(value.document_id) || !text(value.source_uid) ||
      !text(value.source_asset) || !validRevision(value.revision) || !record(value.canvas) ||
      !positiveInt(value.canvas.width) || !positiveInt(value.canvas.height) || !positive(value.canvas.dpi) ||
      value.canvas.width * value.canvas.height > 100_000_000 || value.canvas.dpi < 1e-6 || value.canvas.dpi > 1_000_000 ||
      !(value.selected_id === null || text(value.selected_id)) || !Array.isArray(value.layers))
    throw Error('图层文档快照不完整，已暂停编辑。');
  if (value.layers.length > 1024) throw Error('图层数量超过安全上限，已暂停编辑。');
  const layers: CreativeLayer[] = value.layers.map((item: unknown) => {
    if (!record(item) || !text(item.id) || !text(item.name) || !['image', 'group'].includes(String(item.kind)) ||
        !(item.parent_id === null || text(item.parent_id)) || typeof item.visible !== 'boolean' ||
        typeof item.locked !== 'boolean' || !finite(item.opacity) || item.opacity < 0 || item.opacity > 1 ||
        !CREATIVE_BLEND_MODES.includes(item.blend as CreativeBlend) ||
        !(item.mask_id === null || text(item.mask_id)) || !record(item.transform))
      throw Error('图层字段无效，已暂停编辑。');
    if ((item.kind === 'image' && !text(item.asset_id)) || (item.kind === 'group' && item.asset_id !== null))
      throw Error('图层资源引用无效，已暂停编辑。');
    const t = item.transform;
    if (!finite(t.x) || !finite(t.y) || !positive(t.scale_x) || !positive(t.scale_y) ||
        Math.abs(t.x) > 1e9 || Math.abs(t.y) > 1e9 || t.scale_x < 1e-6 || t.scale_x > 1e4 || t.scale_y < 1e-6 || t.scale_y > 1e4 ||
        !finite(t.rotation) || Math.abs(t.rotation) > 360000 || typeof t.flip_x !== 'boolean' || typeof t.flip_y !== 'boolean')
      throw Error('图层变换无效，已暂停编辑。');
    if (item.kind === 'group' && (t.x !== 0 || t.y !== 0 || t.scale_x !== 1 || t.scale_y !== 1 || t.rotation !== 0 || t.flip_x || t.flip_y))
      throw Error('宿主提供了未支持的图层组变换，已暂停编辑。');
    return {
      id: item.id, kind: item.kind as CreativeLayer['kind'], name: item.name,
      parent_id: item.parent_id as string | null, asset_id: item.asset_id as string | null,
      visible: item.visible, locked: item.locked, opacity: item.opacity, blend: item.blend as CreativeBlend,
      mask_id: item.mask_id as string | null,
      transform: {x: t.x, y: t.y, scale_x: t.scale_x, scale_y: t.scale_y, rotation: t.rotation, flip_x: t.flip_x, flip_y: t.flip_y},
    };
  });
  const byId = new Map(layers.map(layer => [layer.id, layer]));
  if (byId.size !== layers.length || (value.selected_id !== null && !byId.has(value.selected_id)))
    throw Error('图层标识重复或选择已失效，已暂停编辑。');
  for (const layer of layers) {
    const seen = new Set([layer.id]);
    let parent = layer.parent_id;
    while (parent !== null) {
      const group = byId.get(parent);
      if (!group || group.kind !== 'group' || seen.has(parent)) throw Error('图层组关系无效，已暂停编辑。');
      seen.add(parent); if (seen.size > 32) throw Error('图层组深度超过安全上限，已暂停编辑。');
      parent = group.parent_id;
    }
  }
  return {
    schema: 1, document_id: value.document_id, source_uid: value.source_uid, source_asset: value.source_asset,
    revision: value.revision, canvas: {width: value.canvas.width, height: value.canvas.height, dpi: value.canvas.dpi},
    selected_id: value.selected_id, layers,
  };
}

export function bindingFor(authority: CreativeAuthority): CreativeBinding {
  return {document_id: authority.document.document_id, source_uid: authority.document.source_uid,
    ownership_token: authority.ownership_token, expected_revision: authority.document.revision};
}
export function sameOwner(a: CreativeBinding, b: CreativeBinding): boolean {
  return a.document_id === b.document_id && a.source_uid === b.source_uid && a.ownership_token === b.ownership_token;
}
export function previewMatches(preview: CreativePreview | null | undefined, authority: CreativeAuthority): preview is CreativePreview {
  return !!preview && preview.document_id === authority.document.document_id && preview.source_uid === authority.document.source_uid &&
    preview.ownership_token === authority.ownership_token && preview.revision === authority.document.revision &&
    text(preview.render_id) && text(preview.url);
}
export function layerAncestors(document: CreativeDocument, layer: CreativeLayer): CreativeLayer[] {
  const ancestors: CreativeLayer[] = [], seen = new Set([layer.id]);
  let parent = layer.parent_id;
  while (parent !== null && !seen.has(parent)) {
    const group = document.layers.find(item => item.id === parent);
    if (!group) break;
    ancestors.push(group); seen.add(group.id); parent = group.parent_id;
  }
  return ancestors;
}
export const layerLocked = (document: CreativeDocument, layer: CreativeLayer): boolean =>
  layer.locked || layerAncestors(document, layer).some(parent => parent.locked);
export const layerHidden = (document: CreativeDocument, layer: CreativeLayer): boolean =>
  !layer.visible || layerAncestors(document, layer).some(parent => !parent.visible);
export function layerRows(document: CreativeDocument): {layer: CreativeLayer; depth: number}[] {
  const rows: {layer: CreativeLayer; depth: number}[] = [];
  const children = new Map<string | null, CreativeLayer[]>();
  document.layers.forEach(layer => {
    const siblings = children.get(layer.parent_id) ?? []; siblings.push(layer); children.set(layer.parent_id, siblings);
  });
  const stack = (children.get(null) ?? []).map(layer => ({layer, depth: 0}));
  while (stack.length) {
    const row = stack.pop()!; rows.push(row);
    (children.get(row.layer.id) ?? []).forEach(layer => stack.push({layer, depth: row.depth + 1}));
  }
  return rows;
}
export function eligibleParents(document: CreativeDocument, layer: CreativeLayer): CreativeLayer[] {
  return document.layers.filter(group => group.kind === 'group' && group.id !== layer.id &&
    !layerLocked(document, group) && !layerAncestors(document, group).some(ancestor => ancestor.id === layer.id));
}
