import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { TOOL_GROUPS, toolGroupOf } from './toolNavigation.ts';
test('each non-documentation feature has one accessible category',()=>{
  const spec=JSON.parse(readFileSync(new URL('./spec/refine.json',import.meta.url),'utf8'));
  const archive=new Set(['PC-47211','PC-47248','PC-47246','PC-230985','PC-32558','PC-64490','PC-149774','PC-32550','PC-121089','PC-124704','PC-32552']);
  const ids=TOOL_GROUPS.flatMap(g=>[...g.features]);
  assert.equal(new Set(ids).size,ids.length);
  for(const f of spec.features) if(!archive.has(f.id)) assert.ok(toolGroupOf(f.id),f.id);
});
test('basic color controls are not buried in portrait',()=>{
  assert.equal(toolGroupOf('PC-32455'),'color');
  assert.equal(toolGroupOf('PC-32465'),'portrait');
  assert.equal(toolGroupOf('PC-32478'),'crop');
});
