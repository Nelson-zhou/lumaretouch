// SPDX-License-Identifier: GPL-3.0-or-later
import {checkedRules, record, type RuleDraft} from '../model.ts';
export const SCHEMA = 'lrt.portrait-crop-rule-catalogue.v1';
export const RULE_KEYS = ['aspect_ratio', 'headroom_fraction', 'head_fraction', 'horizontal_position'] as const;
export type PresetRules = Record<typeof RULE_KEYS[number], number>;
export type Entry = {id: string; name: string; rules: PresetRules};
export type Catalogue = {schema: typeof SCHEMA; catalogue_id: string; revision: number; entries: Entry[]};
type Expected = {catalogue_id: string; expected_revision: number};
export type Mutation = Expected & (
  {action: 'create'; name: string; rules: PresetRules} |
  {action: 'rename'; id: string; name: string} |
  {action: 'update'; id: string; rules: PresetRules} |
  {action: 'delete'; id: string}
);
export type Request = {action: 'list'} | Mutation;
export type Reply = {status: 'snapshot' | 'saved' | 'no_change'; catalogue: Catalogue} |
  {status: 'rejected'; no_change: true; message: string} | {status: 'uncertain'; message: string};
export type Transport = (request: Request) => Promise<unknown>;
const exact = (value: unknown, keys: readonly string[]): value is Record<string, unknown> => record(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const revision = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0;
export function checkedName(value: string): string {
  const chars = Array.from(value);
  // Names are case-sensitive; no implicit trimming, Unicode normalization or aliases.
  if (!chars.length || chars.length > 64 || new TextEncoder().encode(value).byteLength > 192 || value.trim() !== value ||
      chars.some(c => /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/u.test(c) || (c !== ' ' && /\s/u.test(c)) || (c.codePointAt(0)! >= 0xd800 && c.codePointAt(0)! <= 0xdfff))) {
    throw Error('名称须为 1–64 个可见字符、最多 192 UTF-8 字节，不含首尾空白或控制字符。');
  }
  return value;
}
export function draftFromRules(value: PresetRules): RuleDraft {
  return {aspect_ratio: String(value.aspect_ratio), headroom_fraction: String(value.headroom_fraction), head_fraction: String(value.head_fraction), horizontal_position: String(value.horizontal_position)};
}
export function rulesFromDraft(draft: RuleDraft): PresetRules {
  const value = checkedRules(draft);
  // Deliberate allowlist, not spreading photo/controller state or a plan.
  return {aspect_ratio: value.aspect_ratio, headroom_fraction: value.headroom_fraction, head_fraction: value.head_fraction, horizontal_position: value.horizontal_position};
}
function rules(value: unknown): PresetRules {
  if (!exact(value, RULE_KEYS) || RULE_KEYS.some(key => typeof value[key] !== 'number' || !Number.isFinite(value[key]))) throw Error('预设必须且只能包含四项有限构图比例。');
  return rulesFromDraft(draftFromRules(value as PresetRules));
}
export function checkedCatalogue(value: unknown): Catalogue {
  if (!exact(value, ['schema', 'catalogue_id', 'revision', 'entries']) || value.schema !== SCHEMA || typeof value.catalogue_id !== 'string' || !/^[a-f0-9]{32}$/.test(value.catalogue_id) || !revision(value.revision) || !Array.isArray(value.entries) || value.entries.length > 256) throw Error('预设目录版本、身份或容量无效；不会清空或迁移。');
  const ids = new Set<string>(), names = new Set<string>();
  const entries = value.entries.map(item => {
    if (!exact(item, ['id', 'name', 'rules']) || typeof item.id !== 'string' || !/^rule-[1-9]\d{0,15}$/.test(item.id) || !revision(Number(item.id.slice(5))) || Number(item.id.slice(5)) > Number(value.revision) || typeof item.name !== 'string' || ids.has(item.id) || names.has(item.name)) throw Error('目录中存在未知字段或重复/无效预设。');
    const name = checkedName(item.name); ids.add(item.id); names.add(name);
    return {id: item.id, name, rules: rules(item.rules)};
  });
  return {schema: SCHEMA, catalogue_id: value.catalogue_id, revision: value.revision, entries};
}
export function checkedReply(value: unknown): Reply {
  if (record(value) && ['snapshot', 'saved', 'no_change'].includes(String(value.status)) && exact(value, ['status', 'catalogue'])) return {status: value.status as 'snapshot' | 'saved' | 'no_change', catalogue: checkedCatalogue(value.catalogue)};
  if (exact(value, ['status', 'no_change', 'message']) && value.status === 'rejected' && value.no_change === true && typeof value.message === 'string' && value.message.length <= 4096) return {status: 'rejected', no_change: true, message: value.message};
  if (exact(value, ['status', 'message']) && value.status === 'uncertain' && typeof value.message === 'string' && value.message.length <= 4096) return {status: 'uncertain', message: value.message};
  throw Error('预设目录回执无法验证；不能声称保存或删除成功。');
}
