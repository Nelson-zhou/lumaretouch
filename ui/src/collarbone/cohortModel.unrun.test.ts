// AUTHORED / UNRUN. No imports/tests/typecheck executed during authoring.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validAssociationReview} from '../people/associationProof';
import {collarboneAck,validCollarboneAck} from './transferModel';
import {validCollarboneCohort,collarboneCohortTargets} from './cohortModel';
import {cohortFixture} from './cohortFixture';
test('source and all members require ordered exact image acknowledgments',()=>{
 const {people,plan,sourceId,targetId}=cohortFixture();
 assert.ok(validAssociationReview(plan.persistent_association,people,plan.association_source,plan.targets));assert.ok(validCollarboneCohort(plan,people));
 const rows=collarboneCohortTargets(plan);assert.deepEqual(rows.map(v=>v.document_id),[sourceId,targetId]);assert.equal(rows[0].source,true);
 const visuals=rows.map(v=>v.visual),ack=collarboneAck(visuals);assert.ok(validCollarboneAck(ack,visuals));
 assert.equal(validCollarboneAck(ack.slice(1),visuals),false);assert.equal(validCollarboneAck([...ack].reverse(),visuals),false);
});
test('unlink empty selection retains prior-intent visual requirement',()=>{
 const {people,plan}=cohortFixture('unlink');assert.deepEqual(plan.module_scope,[]);assert.ok(validCollarboneCohort(plan,people));
 const bad={...plan,collarbone_cohort:undefined};assert.equal(validCollarboneCohort(bad,people),false);
});
test('active explicit override may require images without selected or inherited collarbone',()=>{
 const {people,plan}=cohortFixture('patch',true);assert.equal(Object.hasOwn(people.selection,'lnx.collarbone.v1'),false);
 assert.ok(validCollarboneCohort(plan,people));assert.equal(collarboneCohortTargets(plan).length,2);
});
test('missing either member image or coverage never becomes partial cohort consent',()=>{
 for(const mutate of [(p:any)=>{delete p.association_source.association.collarbone_visual;},(p:any)=>{delete p.targets[0].association.collarbone_coverage;},
  (p:any)=>{delete p.association_source;},(p:any)=>{p.targets[0].association.collarbone_visual.document_id=p.association_source.document_id;},
  (p:any)=>{p.targets[0].association.collarbone_coverage.targets[0].face_ref={...p.targets[0].association.ref,analysis_revision:99};},(p:any)=>{p.collarbone_cohort=false;}]){
  const {people,plan}=cohortFixture();const copy=structuredClone(plan);mutate(copy);assert.equal(validCollarboneCohort(copy,people),false);
 }
});
test('cohort payload cannot carry unrelated transfer image schema',()=>{
 const {people,plan}=cohortFixture();(plan.association_source.association as any).source_mask='not transferable';
 assert.equal(validAssociationReview(plan.persistent_association,people,plan.association_source,plan.targets),false);
});
test('visible UI includes source, no persistent guard bypass or omitted approval',()=>{
 const ui=readFileSync(new URL('../batch/BatchReview.tsx',import.meta.url),'utf8'),control=readFileSync(new URL('../people/ConfirmedPeopleTransfer.tsx',import.meta.url),'utf8');
 assert.ok(ui.includes('collarbonePlanTargets(plan)'));assert.ok(ui.includes("target.source?'源成员':'目标成员'"));
 assert.ok(ui.includes('collarboneAck(collarboneTargets.map(t=>t.visual))'));assert.ok(!control.includes('collarbonePersistentBlocked'));
 assert.ok(control.includes('确认源成员与所有目标的真实前后图像'));
});
