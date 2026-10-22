import {describe,it,expect} from 'vitest';
import {KEYS,IDS,neutral,adjust,link,check,active} from './model';
describe('mouth intent, source-written contracts',()=>{
  it('has nine independent controls and exact family',()=>{
    expect(KEYS).toHaveLength(9);expect(IDS.family).toBe('PC-32466-C-cbb4c198e8');
    expect(new Set(Object.values(IDS)).size).toBe(10);
  });
  it('only gummy splits and relink preserves unequal values',()=>{
    let r=link(neutral(),false);r=adjust(r,'gummy',.4,'left');r=adjust(r,'gummy',.2,'right');
    const joined=link(r,true);expect(joined.gummy).toEqual({linked:true,left:.4,right:.2});
    expect(adjust(joined,'gummy',.3,'right').gummy).toEqual({linked:true,left:.3,right:.3});
    expect(()=>adjust(r,'gummy',-.1,'left')).toThrow();
  });
  it('keeps independent scalars and rejects hidden source data',()=>{
    const r=adjust(neutral(),'m_lip',-.5);expect(active(r)).toBe(true);expect(r.width).toBe(0);
    expect(()=>check({...r,landmarks:[]})).toThrow();expect(()=>adjust(r,'tilt',NaN)).toThrow();
    expect(neutral().m_lip).toBe(0);
  });
});
