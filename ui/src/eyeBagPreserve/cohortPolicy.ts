// SPDX-License-Identifier: GPL-3.0-or-later
/** Explicit source-first policy only. No source masks, analysis or recovery data can travel. */
export type EyeBagCohortPolicy = {version: 1; members: {document_id: string; replace_legacy: boolean}[]};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
export function validEyeBagCohortPolicy(value: unknown, ids: string[]): value is EyeBagCohortPolicy {
  return object(value) && keys(value, ['version', 'members']) && value.version === 1 && Array.isArray(value.members)
    && ids.length >= 2 && ids.length <= 16 && new Set(ids).size === ids.length && ids.every(id => /^[a-f0-9]{32}$/.test(id))
    && value.members.length === ids.length && value.members.every((row, index) => object(row)
      && keys(row, ['document_id', 'replace_legacy']) && row.document_id === ids[index] && typeof row.replace_legacy === 'boolean');
}
export function eyeBagCohortPolicy(ids: string[], choices: Record<string, boolean | undefined>): EyeBagCohortPolicy | undefined {
  if (ids.some(id => typeof choices[id] !== 'boolean')) return undefined;
  const value: EyeBagCohortPolicy = {version: 1, members: ids.map(document_id => ({document_id, replace_legacy: choices[document_id]!}))};
  return validEyeBagCohortPolicy(value, ids) ? value : undefined;
}
export function sameEyeBagCohortPolicy(value: unknown, expected: EyeBagCohortPolicy, ids: string[]): boolean {
  return validEyeBagCohortPolicy(value, ids) && validEyeBagCohortPolicy(expected, ids)
    && value.members.every((row, index) => row.replace_legacy === expected.members[index].replace_legacy);
}
