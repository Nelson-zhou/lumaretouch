// SPDX-License-Identifier: GPL-3.0-or-later
/** Shared authored fixtures only, UNRUN. No product import or image processing was executed. */
import {createHash} from 'node:crypto';
import type {ReviewImageInput, WorkflowPresetHandoff, WorkflowPresetReview} from './presetReview.ts';
export const png = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAADklEQVR4nGMIAAMGCAUAGk4DwSPol3sAAAAASUVORK5CYII=';
const raw = Buffer.from(png, 'base64'), sha = createHash('sha256').update(raw).digest('hex');
const image = () => ({mime: 'image/png' as const, width: 2, height: 2, sha256: sha, byte_length: raw.length, page_count: 1});
export function reviewFixture(): WorkflowPresetReview {
  return {schema: 'lrt.workflow-preset-review.v1', review_id: 'review-a', review_sha256: 'a'.repeat(64),
    target: {document_id: 'document-a', load_id: 'load-a', revision: '1'}, preset_id: 'warm', preset_sha256: 'b'.repeat(64),
    module_ids: ['lnx.exposure.v1'], before: image(), after: image(), source_proof: {fixture: true}, source_size: [2, 2], output_size: [2, 2],
    before_state_sha256: 'c'.repeat(64), candidate_state_sha256: 'd'.repeat(64), people_sha256: 'e'.repeat(64), repair_sha256: 'f'.repeat(64),
    before_render_sha256: '1'.repeat(64), candidate_render_sha256: '2'.repeat(64), page_bytes: 65536, ttl_seconds: 900, approval_only: true, runtime_verified: false};
}
export function handoffFixture(): WorkflowPresetHandoff {
  return {version: 1, operation_id: '3'.repeat(64), document_id: 'document-a', preset_id: 'warm', preset_sha256: 'b'.repeat(64),
    phase: 'reviewing', review: reviewFixture(), message: 'Fixture only, never displayed as production evidence'};
}
export function pageFixture(input: ReviewImageInput) {
  return {review_id: input.review_id, review_sha256: input.review_sha256, target: reviewFixture().target, side: input.side,
    ...image(), page: input.page, page_bytes: 65536 as const, offset: 0, page_byte_length: raw.length, page_sha256: sha, base64: png};
}
