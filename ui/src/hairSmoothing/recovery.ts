// SPDX-License-Identifier: GPL-3.0-or-later
/** Native replacement metadata, not a request/result/history ledger. */
export type HairSmoothingRecovery = {engine_epoch: string; replacement_serial: number};
export function validHairSmoothingRecovery(value: unknown): value is HairSmoothingRecovery {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  return Object.keys(row).sort().join('|') === 'engine_epoch|replacement_serial'
    && typeof row.engine_epoch === 'string' && /^[a-f0-9]{32}$/.test(row.engine_epoch)
    && typeof row.replacement_serial === 'number' && Number.isSafeInteger(row.replacement_serial) && row.replacement_serial > 0;
}

export function validHairSmoothingAbandonment(proof: unknown, request: {request_id:string}): boolean {
  if (!proof || typeof proof !== 'object' || Array.isArray(proof)) return false;
  const row = proof as Record<string, unknown>, {request_id, ...binding} = request;
  const canonical = (value: unknown): string => Array.isArray(value) ? '['+value.map(canonical).join(',')+']'
    : value && typeof value === 'object' ? '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical((value as Record<string,unknown>)[k])).join(',')+'}' : JSON.stringify(value) ?? 'undefined';
  return Object.keys(row).sort().join('|') === 'authority|hair_smoothing_request|owner_engine_epoch|previous_outcome|replacement_engine_epoch|replacement_serial|request_id'
    && row.authority === 'native-verified-replacement' && row.previous_outcome === 'unknown' && row.request_id === request_id
    && canonical(row.hair_smoothing_request) === canonical(binding)
    && [row.owner_engine_epoch,row.replacement_engine_epoch].every(v=>typeof v==='string' && /^[a-f0-9]{32}$/.test(v))
    && typeof row.replacement_serial === 'number' && Number.isSafeInteger(row.replacement_serial) && row.replacement_serial > 0;
}
