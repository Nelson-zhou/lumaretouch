// SPDX-License-Identifier: GPL-3.0-or-later
export type HairFamilyMember = 'colour' | 'unification' | 'volume';
export type HairFamilyLocks = Record<HairFamilyMember, boolean>;
/** A reserved request must not reject itself after the common curve-edit barrier. */
export function hairFamilyAdmission(member: HairFamilyMember, baseReady: boolean, locks: HairFamilyLocks): boolean {
  return baseReady && (Object.keys(locks) as HairFamilyMember[]).every(other => other === member || !locks[other]);
}
export type HairReviewActivity = {open: boolean; pending: boolean; checking: boolean; preparing: boolean; refreshing: boolean; uncertain: boolean};
export function hairReviewBusy(state: HairReviewActivity): boolean {
  return state.open || state.pending || state.checking || state.preparing || state.refreshing || state.uncertain;
}
/** Capability identity is separate from numeric-core availability: neutral recovery may still be supported. */
export function hairVolumeProtocol(protocol: unknown, capability: unknown): boolean {
  if (!capability || typeof capability !== 'object' || Array.isArray(capability)) return false;
  const value = capability as Record<string, unknown>;
  return protocol === 1 && value.protocol === 1 && value.operation_id === 'lnx.hair_volume.v1'
    && typeof value.available === 'boolean' && (value.reason === null || typeof value.reason === 'string');
}
