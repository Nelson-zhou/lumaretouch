// Synthetic source-contract DTO only, not photograph quality evidence.
import {cohortFixture} from './cohortFixture';
import type {CollarbonePresetReview} from './presetModel';
export function presetFixture():CollarbonePresetReview{
 const row=cohortFixture().plan.association_source.association!;
 return {version:1,preset_sha256:'a'.repeat(64),applies_sha256:'b'.repeat(64),load_id:'current-load-session',
  owner:row.owner,face_ref:row.ref,coverage:row.collarbone_coverage!,visual:row.collarbone_visual!};
}
