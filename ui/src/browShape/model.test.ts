import {describe,it,expect} from 'vitest';
import {neutral,adjust,link,check} from './model';
describe('eyebrow bilateral recipe',()=>{
  it('relinks without overwriting asymmetry; explicit linked adjustment synchronizes',()=>{
    let r=link(neutral(),'arch',false);r=adjust(r,'arch','left',.4);r=adjust(r,'arch','right',-.2);
    r=link(r,'arch',true);expect(r.arch).toEqual({linked:true,left:.4,right:-.2});
    r=adjust(r,'arch','right',.1);expect(r.arch).toEqual({linked:true,left:.1,right:.1});
    expect(r.position).toEqual(neutral().position);
  });
  it('rejects corrupt and nonparameter data',()=>{
    expect(()=>check({...neutral(),source:'other-person.jpg'})).toThrow();
    expect(()=>check({...neutral(),position:{linked:true,left:NaN,right:0}})).toThrow();
  });
});
