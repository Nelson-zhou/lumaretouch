// SPDX-License-Identifier: GPL-3.0-or-later
import {peopleContext, type FaceRef, type PeopleContext, type PeopleView} from '../people/model.ts';

export const OPERATION = 'lnx.hair_volume.v1' as const;
export const CONTROL_IDS = {crown: 'control:PC-32472:2', sides: 'control:PC-32472:3'} as const;
export const PROTECTION_LIMITS = {ears: 2, neck: 1, other_people: 64} as const;
export const REGION_KEYS = ['crown', 'left', 'right'] as const;
export type RegionKey = typeof REGION_KEYS[number];
export type Point = [number, number];
export type Box = [number, number, number, number];
export type Bounds = [number, number, number, number];
export type Recipe = {version: 1; crown: {version: 1; amount: number}; sides: {version: 1; linked: boolean; left: number; right: number}};
export type Patch = {x: Bounds; y: Bounds; contour: Point[]; hair_samples: Point[]; background_samples: Point[]};
/** Incomplete local measurements persist, but can never be submitted as support. */
export type PatchDraft = Omit<Patch, 'x' | 'y'> & {x: Bounds | null; y: Bounds | null};
export type Regions = Record<RegionKey, Patch | null>;
export type RegionDrafts = Record<RegionKey, PatchDraft | null>;
export type Protection = {ears: Box[]; neck: Box[]; other_people: Box[]; visible_anatomy_reviewed: boolean; whole_source_reviewed: boolean};
export type Source = {sha256: string; width: number; height: number};
export type Reference = {
  source: Source; face_ref: FaceRef; recipe: Recipe; source_kind: 'original' | 'derived';
  semantic_evidence_sha256: string | null; source_png: string; source_png_sha256: string;
  source_width: number; source_height: number; source_preview_width: number; source_preview_height: number;
  native_available: boolean; notice: string;
};
export type Draft = {recipe: Recipe; regions: RegionDrafts; protection: Protection;
  crown_confirmed: boolean; left_confirmed: boolean; right_confirmed: boolean};
export type PreviewPayload = {recipe: Recipe; regions: Regions; protection: Protection;
  confirmed: true; crown_confirmed: boolean; left_confirmed: boolean; right_confirmed: boolean};
export type Review = {
  preview_id: string; review_token: string; preview_sha256: string; support_asset_sha256: string;
  source: Source; face_ref: FaceRef; recipe: Recipe; regions: Regions; protection: Protection;
  semantic_evidence_sha256: string; before_png: string; after_png: string; support_png: string;
  before_sha256: string; after_sha256: string; support_sha256: string;
  source_width: number; source_height: number; before_width: number; before_height: number;
  after_width: number; after_height: number; support_width: number; support_height: number;
};
export type Action = 'context' | 'preview' | 'presented' | 'commit' | 'clear';
export type Request = {cmd: 'hair_volume'; protocol: 1; operation_id: typeof OPERATION; request_id: string;
  action: Action; people_context: PeopleContext; payload: Record<string, unknown>};
export type Result = {event: 'hair_volume_result'; protocol: 1; operation_id: typeof OPERATION; request_id: string;
  action: Action; document_id: string; people_context: PeopleContext; request_payload: Record<string, unknown>;
  success: boolean; outcome_unknown: boolean; error?: string; payload: unknown; doc_state?: unknown; workspace_reopened?: true};
export type Mailbox = {request_id: string; phase: 'pending' | 'done' | 'unavailable'; result?: Result; error?: string};
export type Binding = {key: string; context: PeopleContext | null; targetReady: boolean; measured: boolean; reason: string};
export const neutral = (): Recipe => ({version: 1, crown: {version: 1, amount: 0}, sides: {version: 1, linked: true, left: 0, right: 0}});
export const emptyPatch = (): PatchDraft => ({x: null, y: null, contour: [], hair_samples: [], background_samples: []});
export const emptyRegions = (): RegionDrafts => ({crown: null, left: null, right: null});
export const emptyProtection = (): Protection => ({ears: [], neck: [], other_people: [], visible_anatomy_reviewed: false, whole_source_reviewed: false});
export const emptyDraft = (recipe = neutral()): Draft => ({recipe, regions: emptyRegions(), protection: emptyProtection(),
  crown_confirmed: false, left_confirmed: false, right_confirmed: false});
export const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const fields = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const unit = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
const signed = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= -1 && value <= 1;
const revision = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
const extent = (value: unknown): value is number => revision(value) && value > 1 && value <= 1000000;
const token = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 160;
export const digest = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
export const png = (value: unknown): value is string => typeof value === 'string' && value.length <= 8 * 1024 * 1024
  && /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value);
export const point = (value: unknown): value is Point => Array.isArray(value) && value.length === 2 && value.every(unit);
export const sameFace = (a: FaceRef | null | undefined, b: FaceRef | null | undefined) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export const sameSource = (a: Source, b: Source) => a.sha256 === b.sha256 && a.width === b.width && a.height === b.height;
/** Equality only, never a replacement for native evidence hashes. */
export function key(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(key).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(field => `${JSON.stringify(field)}:${key(value[field])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}
export function checkRecipe(value: unknown): Recipe {
  if (!object(value) || !fields(value, ['version', 'crown', 'sides']) || value.version !== 1
    || !object(value.crown) || !fields(value.crown, ['version', 'amount']) || value.crown.version !== 1 || !signed(value.crown.amount)
    || !object(value.sides) || !fields(value.sides, ['version', 'linked', 'left', 'right']) || value.sides.version !== 1
    || typeof value.sides.linked !== 'boolean' || !signed(value.sides.left) || !signed(value.sides.right)
    || value.sides.linked && value.sides.left !== value.sides.right) throw Error('颅顶与两侧发量必须独立版本化，强度为 −1 到 +1；链接两侧必须明确使用相同值。');
  return structuredClone(value) as Recipe;
}
export function isNeutral(recipe: Recipe): boolean {return recipe.crown.amount === 0 && recipe.sides.left === 0 && recipe.sides.right === 0;}
export function activeRegions(recipe: Recipe): RegionKey[] {return REGION_KEYS.filter(region => (region === 'crown' ? recipe.crown.amount : recipe.sides[region]) !== 0);}
export function checkBounds(value: unknown): Bounds {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(unit) || value[0] <= 0 || value[3] >= 1
    || !(value[0] < value[1] && value[1] < value[2] && value[2] < value[3])) throw Error('过渡外界和内部平台必须在源图内部，严格依次为 a < b < c < d。');
  return [...value] as Bounds;
}
export function checkBox(value: unknown): Box {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(unit) || value[0] >= value[2] || value[1] >= value[3])
    throw Error('保护框必须是当前源图内非退化的左上角和右下角。');
  return [...value] as Box;
}
export function checkPatchDraft(value: unknown): PatchDraft {
  if (!object(value) || !fields(value, ['x', 'y', 'contour', 'hair_samples', 'background_samples'])) throw Error('本项轮廓只能包含源图边界和手工配对采样点。');
  for (const field of ['contour', 'hair_samples', 'background_samples']) {
    const points = value[field];
    if (!Array.isArray(points) || points.length > 33 || !points.every(point)) throw Error('每组轮廓与采样最多 33 个源图归一化点。');
  }
  return {x: value.x === null ? null : checkBounds(value.x), y: value.y === null ? null : checkBounds(value.y),
    contour: structuredClone(value.contour) as Point[], hair_samples: structuredClone(value.hair_samples) as Point[],
    background_samples: structuredClone(value.background_samples) as Point[]};
}
export function checkPatch(value: unknown, region: RegionKey): Patch {
  const patch = checkPatchDraft(value), {x, y, contour, hair_samples: hair, background_samples: background} = patch;
  if (!x || !y || contour.length < 3 || hair.length !== contour.length || background.length !== contour.length)
    throw Error('每项需完整过渡边界和平台，以及 3–33 组一一对应的轮廓、头发内和清晰背景点。');
  const axis = region === 'crown' ? 0 : 1;
  const inPlateau = ([px, py]: Point) => px >= x[1] && px <= x[2] && py >= y[1] && py <= y[2];
  for (let i = 0; i < contour.length; i++) {
    const p = contour[i], h = hair[i], b = background[i];
    if (!inPlateau(p) || !inPlateau(h) || b[0] < x[0] || b[0] > x[3] || b[1] < y[0] || b[1] > y[3]
      || h[axis] !== p[axis] || b[axis] !== p[axis]
      || i > 0 && p[axis] <= contour[i - 1][axis]
      || region === 'crown' && !(h[1] > p[1] && b[1] < p[1])
      || region === 'left' && !(h[0] > p[0] && b[0] < p[0])
      || region === 'right' && !(h[0] < p[0] && b[0] > p[0]))
      throw Error('轮廓必须沿正确方向递增，轮廓和头发点位于平台，配对头发/背景点在轮廓正确两侧且背景位于过渡外界内。');
  }
  return {...patch, x, y};
}
export function checkProtection(value: unknown): Protection {
  if (!object(value) || !fields(value, ['ears', 'neck', 'other_people', 'visible_anatomy_reviewed', 'whole_source_reviewed'])
    || typeof value.visible_anatomy_reviewed !== 'boolean' || typeof value.whole_source_reviewed !== 'boolean') throw Error('保护范围和整张源图复核缺失。');
  const result = {...value} as Protection;
  for (const field of ['ears', 'neck', 'other_people'] as const) {
    const boxes = value[field];
    if (!Array.isArray(boxes) || boxes.length > PROTECTION_LIMITS[field]) throw Error(`本类保护范围最多 ${PROTECTION_LIMITS[field]} 个源图保护框。`);
    result[field] = boxes.map(checkBox);
  }
  return result;
}
export function checkDraft(value: Draft): Draft {
  if (!object(value) || !fields(value, ['recipe', 'regions', 'protection', 'crown_confirmed', 'left_confirmed', 'right_confirmed'])
    || !object(value.regions) || !fields(value.regions, [...REGION_KEYS])
    || ![value.crown_confirmed, value.left_confirmed, value.right_confirmed].every(flag => typeof flag === 'boolean')) throw Error('本地发量草稿字段不完整。');
  return {recipe: checkRecipe(value.recipe), regions: Object.fromEntries(REGION_KEYS.map(region =>
    [region, value.regions[region] === null ? null : checkPatchDraft(value.regions[region])])) as RegionDrafts,
    protection: checkProtection(value.protection), crown_confirmed: value.crown_confirmed,
    left_confirmed: value.left_confirmed, right_confirmed: value.right_confirmed};
}
export function previewPayload(value: Draft): PreviewPayload {
  const draft = checkDraft(value), active = activeRegions(draft.recipe);
  if (!active.length || !draft.protection.visible_anatomy_reviewed || !draft.protection.whole_source_reviewed)
    throw Error('请选择非零调整，并独立复核整张源图和可见耳部、颈部及其他人物的保护范围。');
  const regions = Object.fromEntries(REGION_KEYS.map(region => [region, !active.includes(region) || draft.regions[region] === null ? null
    : checkPatch(draft.regions[region], region)])) as Regions;
  for (const region of active) if (!regions[region] || !draft[`${region}_confirmed`])
    throw Error('每项非零颅顶或单侧发量都需要本项轮廓、本人头发归属及清晰背景的独立确认。');
  return {...draft, regions, confirmed: true};
}

/** Source-pixel minima are local conservative policies, not published reference-product values. */
export function checkSourceGeometry(regions: Regions, source: Source): void {
  for (const region of REGION_KEYS) {
    const patch = regions[region]; if (!patch) continue;
    const extents = [source.width - 1, source.height - 1];
    for (const [index, bounds] of [patch.x, patch.y].entries()) {
      const extent = extents[index], [a, b, c, d] = bounds;
      if (a * extent < 1 - 1e-8 || (1 - d) * extent < 1 - 1e-8 || (b - a) * extent < 4 - 1e-8
        || (d - c) * extent < 4 - 1e-8 || (c - b) * extent < 2 - 1e-8)
        throw Error('边界需离源图边缘至少 1 像素，两个淡出边距各至少 4 像素，平台至少 2 像素。');
    }
    const tangent = region === 'crown' ? 0 : 1, normal = tangent === 0 ? 1 : 0, bounds = tangent === 0 ? patch.x : patch.y;
    if (patch.contour[patch.contour.length - 1][tangent] - patch.contour[0][tangent] < (bounds[2] - bounds[1]) / 2 - 1e-12)
      throw Error('实测轮廓端点必须覆盖至少一半的切向平台，不能用过短局部点列代表整项轮廓。');
    for (let i = 0; i < patch.contour.length; i++) if (
      Math.abs(patch.hair_samples[i][normal] - patch.contour[i][normal]) * extents[normal] < 1 - 1e-8
      || Math.abs(patch.background_samples[i][normal] - patch.contour[i][normal]) * extents[normal] < 1 - 1e-8)
      throw Error('每个头发/背景探针到对应轮廓的法向距离至少为 1 个规范源图像素。');
  }
}

/** Exact selected FaceRef only; no all-people, group, linked-person or synthetic face admission. */
export function binding(view: PeopleView | null | undefined): Binding {
  const context = peopleContext(view) ?? null, target = context?.target;
  const face = view?.faces.find(item => item.face_ref.face_instance_id === view.selected_face_id);
  const ready = !!view && !!context && token(context.document_id) && token(context.document_epoch)
    && [context.document_revision, context.state_revision, context.association_revision].every(revision)
    && digest(view.binding.asset_sha256) && target?.scope === 'face' && target.target_id === view.selected_face_id
    && !!face && face.face_ref.asset_sha256 === view.binding.asset_sha256 && revision(face.face_ref.analysis_revision)
    && token(face.face_ref.face_instance_id) && sameFace(face.face_ref, target.face_ref);
  const measured = ready && face?.enabled === true && face.analysis_status === 'verified';
  return {key: key([context, view?.binding.asset_sha256, view?.selected_face_id, face?.enabled, face?.analysis_status]), context,
    targetReady: ready, measured, reason: !ready ? '请在当前照片选择所需人物的独立覆盖；本项不支持分组、关联人物或批量迁移。'
      : !measured ? '所选人物未启用或缺少真实人脸分析；本项不根据人脸框猜测颅顶、耳部或头发归属。' : ''};
}
function readSource(value: unknown): Source {
  if (!object(value) || !fields(value, ['sha256', 'width', 'height']) || !digest(value.sha256) || !extent(value.width) || !extent(value.height))
    throw Error('当前不可变源图的哈希或规范尺寸无效。');
  return value as Source;
}
export function readReference(value: unknown, context: PeopleContext): Reference {
  if (!object(value) || !object(value.face_ref) || !sameFace(value.face_ref as FaceRef, context.target.face_ref)
    || typeof value.native_available !== 'boolean' || typeof value.notice !== 'string' || value.notice.length > 4096
    || !['original', 'derived'].includes(String(value.source_kind)) || !digest(value.source_png_sha256)
    || !(value.semantic_evidence_sha256 === null || digest(value.semantic_evidence_sha256))) throw Error('发量来源回执与当前人物或真实头发证据不一致。');
  const source = readSource(value.source);
  if (value.source_width !== source.width || value.source_height !== source.height || !png(value.source_png)
    || ![value.source_preview_width, value.source_preview_height].every(n => extent(n) && n <= 1024)
    || source.sha256 !== context.target.face_ref?.asset_sha256)
    throw Error('源图展示尺寸或原片/实际修复源绑定不符，不能手工标记。');
  return {...value, source, recipe: checkRecipe(value.recipe)} as Reference;
}
function boundedImage(raw: Record<string, unknown>, prefix: string): void {
  if (!png(raw[`${prefix}_png`]) || !digest(raw[`${prefix}_sha256`])
    || ![raw[`${prefix}_width`], raw[`${prefix}_height`]].every(n => extent(n) && n <= 1024)) throw Error('完整审核图片、尺寸或字节摘要无效。');
}
export function readReview(value: unknown, reference: Reference, draft: Draft): Review {
  const expected = previewPayload(draft);
  if (!object(value) || typeof value.preview_id !== 'string' || !/^[0-9a-f]{32}$/.test(value.preview_id)
    || !digest(value.review_token) || value.preview_sha256 !== value.review_token || !digest(value.support_asset_sha256)
    || !object(value.source) || !sameSource(readSource(value.source), reference.source)
    || !object(value.face_ref) || !sameFace(value.face_ref as FaceRef, reference.face_ref)
    || value.source_width !== reference.source.width || value.source_height !== reference.source.height
    || value.semantic_evidence_sha256 !== reference.semantic_evidence_sha256 || !digest(value.semantic_evidence_sha256)
    || key(checkRecipe(value.recipe)) !== key(expected.recipe) || key(value.regions) !== key(expected.regions)
    || key(checkProtection(value.protection)) !== key(expected.protection)) throw Error('候选与当前源图、人物、真实头发证据或本次独立轮廓不一致。');
  for (const side of ['before', 'after', 'support']) boundedImage(value, side);
  if (value.before_width !== value.after_width || value.before_height !== value.after_height
    || value.support_width !== value.before_width || value.support_height !== value.before_height)
    throw Error('完整混合前后图与诊断图必须保持同一幅照片的完整尺寸。');
  return value as unknown as Review;
}
function correlatedResult(raw: unknown, request: Request): Result {
  if (!object(raw) || raw.event !== 'hair_volume_result' || raw.protocol !== 1 || raw.operation_id !== OPERATION
    || raw.request_id !== request.request_id || raw.action !== request.action || raw.document_id !== request.people_context.document_id
    || key(raw.people_context) !== key(request.people_context) || key(raw.request_payload) !== key(request.payload)
    || typeof raw.success !== 'boolean' || typeof raw.outcome_unknown !== 'boolean') throw Error('原发量请求的身份、状态或内容不匹配，只能查询原请求。');
  return raw as unknown as Result;
}
export function readResult(raw: unknown, request: Request): Result {
  const result = correlatedResult(raw, request);
  if (result.outcome_unknown || result.workspace_reopened !== undefined) throw Error('原发量请求结果仍未知；保留原请求和草稿，不能重发。');
  return result;
}
export function readWorkspaceReopened(raw: unknown, request: Request): Result | null {
  if (!object(raw) || raw.workspace_reopened === undefined) return null;
  const result = correlatedResult(raw, request);
  if (result.workspace_reopened !== true || result.success !== false || result.outcome_unknown !== true)
    throw Error('原生工程重开回执不符合原未知请求，继续保留原操作保护。');
  return result;
}
export function reviewAck(review: Review): Record<string, unknown> {
  return {preview_id: review.preview_id, review_token: review.review_token,
    before_sha256: review.before_sha256, after_sha256: review.after_sha256, support_sha256: review.support_sha256};
}
export function readPresented(raw: unknown, review: Review): void {
  const expected = reviewAck(review);
  if (!object(raw) || raw.kind !== 'presented' || raw.presented !== true || Object.keys(expected).some(field => raw[field] !== expected[field]))
    throw Error('当前完整前后图片的精确显示确认不匹配，不能应用。');
}
export async function imageDigest(url: string): Promise<string> {
  if (!png(url)) throw Error('待核验图片不是有界 PNG。');
  const binary = atob(url.slice(url.indexOf(',') + 1)), bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, '0')).join('');
}
