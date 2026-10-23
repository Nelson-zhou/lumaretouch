// UNRUN source integration fixtures, not typecheck evidence.
import {describe,it,expect} from 'vitest';
import {createPeopleWorkflow} from '../people/workflow';
import {REQUIREMENTS,neutral,check} from './model';
describe('eye-light ownership contract',()=>{
 it('retains all six exact requirement identities',()=>expect(Object.values(REQUIREMENTS)).toHaveLength(6));
 it('does not put support into a creative recipe',()=>expect(()=>check({...neutral(),local_assets:{}})).toThrow());
 it('uses existing people receipt owner',()=>{const w=createPeopleWorkflow({send:async()=>{},read:async request_id=>({phase:'unavailable',request_id}),refresh:async()=>{}});expect(w.snapshot().pending).toBe(false);});
});
