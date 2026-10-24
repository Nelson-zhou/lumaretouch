// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. No typecheck, test collection or UI execution performed.
import {describe,it,expect} from 'vitest';
import {OPERATION_ID,REQUIREMENT_ID,ANCHORS,FLAGS,neutral,check,checkReviewSupport,type ReviewSupport} from './model';
import {recoveryWithoutCore} from './availability';
const support=():ReviewSupport=>({version:1,method:'user-traced-complete-person-silhouette-v1',outline:[[.46,.24],[.54,.24],[.6,.3],[.6,.7],[.54,.76],[.46,.76],[.4,.7],[.4,.3]],collar_box:[.1,.05,.9,.95],confirmations:Object.fromEntries(FLAGS.map(k=>[k,true])) as ReviewSupport['confirmations']});
describe('whole-person width source contracts AUTHORED UNRUN',()=>{
 it('has independent exact requirement and all actual anchors',()=>{expect(OPERATION_ID).toBe('lnx.body_slim.v1');expect(REQUIREMENT_ID).toBe('LNX-REF-PC-32473-C-bc54b9eb3c');expect(ANCHORS).toHaveLength(33);});
 it('retains signed scalar only',()=>{for(const amount of [-1,0,1])expect(check({version:1,amount})).toEqual({version:1,amount});expect(()=>check({...neutral(),waist:1} as never)).toThrow();});
 it('requires explicit full silhouette not a rectangle',()=>{expect(checkReviewSupport(support())).toEqual(support());const value=support();value.outline=value.outline.slice(0,4);expect(()=>checkReviewSupport(value)).toThrow();});
 it('requires every affirmative source review',()=>{for(const flag of FLAGS){const value=support();value.confirmations[flag]=false as never;expect(()=>checkReviewSupport(value)).toThrow();}});
 it('allows recovery only without core',()=>{expect(recoveryWithoutCore('recipe',{recipe:neutral()})).toBe(true);expect(recoveryWithoutCore('recipe',{recipe:{version:1,amount:.1}})).toBe(false);expect(recoveryWithoutCore('operation_status',{enabled:false})).toBe(true);expect(recoveryWithoutCore('support_review',{})).toBe(false);});
});
