// AUTHORED / UNRUN. Source contract fixtures, not model or photo acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {upscaleDefaultRecipe,validUpscaleRecipe,validUpscaleCapability,unavailableUpscaleCapability,
  validUpscaleWriteCommand,validUpscaleSource} from './model';
test('first profile cannot select sharpening, identity or another model',()=>{
  assert.ok(validUpscaleRecipe(upscaleDefaultRecipe()));
  for(const model_id of ['lanczos3','identity','RealESRGAN_x4plus']) assert.equal(validUpscaleRecipe({version:1,model_id}),false);
  assert.equal(validUpscaleRecipe({...upscaleDefaultRecipe(),sharpen:1}),false);
});
test('capability distinguishes installation eligibility from unrun acceptance',()=>{
  const unavailable=unavailableUpscaleCapability('Official weight evidence missing');
  assert.ok(validUpscaleCapability(unavailable));
  assert.equal(validUpscaleCapability({...unavailable,acceptance:'passed'}),false);
  assert.equal(validUpscaleCapability({...unavailable,model_id:'other'}),false);
});
test('source limit and exact reviewed copy contract cannot be bypassed',()=>{
  const source={sha256:'a'.repeat(64),width:1024,height:1024,orientation:'exif_normalized_once'};
  assert.ok(validUpscaleSource(source)); assert.equal(validUpscaleSource({...source,height:1025}),false);
  assert.equal(validUpscaleSource({...source,width:1025,height:16}),false);
  assert.equal(validUpscaleSource({...source,width:15,height:16}),false);
  assert.equal(validUpscaleWriteCommand({action:'apply',reviewed:true,return_mode:'update_source'}),false);
});

// Presentation/transport wiring remains an authored acceptance case, not executed UI evidence.
