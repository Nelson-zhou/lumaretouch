// Synthetic ownership DTO only, not photographic evidence.
import {presetFixture as baseFixture} from '../collarbone/presetFixture';
import type {EyeBagPresetReview} from './presetModel';
export function eyeBagFixture():EyeBagPresetReview{
 const v=baseFixture();return {...v,replace_legacy:false,coverage:{version:1,support_transfer:'none',targets:[{face_ref:v.face_ref,scope:'target-reviewed-ridge',ridge_sha256:'c'.repeat(64),sides:['left']}]}};
}
