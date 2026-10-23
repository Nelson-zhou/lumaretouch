// Authored source regression cases only; not executed in this tranche.
import test from 'node:test';import assert from 'node:assert/strict';
import {shoulderBinding} from './context.ts';
import type {DocState,EngineStatus} from '../native.ts';
const binding={document_id:'document-uuid',document_epoch:'workspace-uuid',document_revision:7,asset_sha256:'a'.repeat(64)};
const doc={document_id:'load-clock-identity',people:{binding},shoulder_shape:{binding}} as DocState;
const status={image:{load_id:'load-clock-identity'}} as EngineStatus;
test('load and persistent document identities intentionally differ',()=>{assert.notEqual(doc.document_id,binding.document_id);assert.deepEqual(shoulderBinding(status,doc),binding);});
test('a stale document report does not expose old body binding on a new load',()=>{assert.equal(shoulderBinding({image:{load_id:'new-load'}} as EngineStatus,doc),null);});
test('disagreeing people and body bindings are not silently mixed',()=>{assert.equal(shoulderBinding(status,{...doc,shoulder_shape:{binding:{...binding,document_id:'different-document'}}} as DocState),null);});
