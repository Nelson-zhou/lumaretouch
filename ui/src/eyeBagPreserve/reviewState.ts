// SPDX-License-Identifier: GPL-3.0-or-later
import type {SpillImage} from '../spillRemoval/model';
import {imageKey, memberKey, members, type EyeBagReview, type EyeBagMember} from './model';
export type EyeBagImages = Record<string, SpillImage>;
export type EyeBagLoaded = Record<string, boolean>;
export type EyeBagAccepted = Record<string, boolean>;
export function pairReady(review: EyeBagReview, member: EyeBagMember, images: EyeBagImages, loaded: EyeBagLoaded): boolean {
  return (['before', 'after'] as const).every(side => {
    const key = imageKey(review, side, member.visual.document_id);
    return !!images[key] && loaded[key] === true;
  });
}
/** Every member is necessary, including nonvisible pages. One shared overlay is not a member preview. */
export function reviewReady(review: EyeBagReview, images: EyeBagImages, loaded: EyeBagLoaded,
  accepted: EyeBagAccepted, supportAccepted: boolean): boolean {
  const support = imageKey(review, 'support');
  return !!images[support] && loaded[support] === true && (review.version === 1 || supportAccepted)
    && members(review).every(member => pairReady(review, member, images, loaded) && accepted[memberKey(review, member.visual)] === true);
}
