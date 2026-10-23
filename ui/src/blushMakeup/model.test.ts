// SPDX-License-Identifier: GPL-3.0-or-later
// Authored UNRUN. No vitest/typecheck was run during source implementation.
import {describe,it,expect} from 'vitest';
import {PATTERNS,check,neutral,colour,rgb,palette,patches,OP} from './model';
describe('original blush material intent',()=>{
  it('has twelve different analytic shapes with fixed colour',()=>{
    expect(PATTERNS).toHaveLength(12);expect(new Set(PATTERNS.map(p=>JSON.stringify(p.lobes))).size).toBe(12);
  });
  it('makes strict RGB/HEX consistent and caps six unique saved colours',()=>{
    expect(colour('#aabbcc')).toBe('#AABBCC');expect(rgb([170,187,204])).toBe('#AABBCC');
    expect(()=>rgb([256,0,0])).toThrow();expect(()=>rgb([1.2,2,3])).toThrow();expect(()=>colour('#FFF')).toThrow();
    expect(()=>palette(['#ffffff','#FFFFFF'])).toThrow();expect(()=>palette(Array(7).fill('#000000'))).toThrow();
  });
  it('rejects cached anatomy and writes only chosen scalar leaves',()=>{
    expect(()=>check({...neutral(),source:'foreign'})).toThrow();expect(()=>check({...neutral(),strength:NaN})).toThrow();
    expect(patches({...neutral(),colour:'#123456'},['colour'])).toEqual([{operation_id:OP,parameter_path:'/colour',unset:false,value:'#123456'}]);
  });
});
