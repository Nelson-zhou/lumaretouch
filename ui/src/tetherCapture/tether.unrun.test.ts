// SPDX-License-Identifier: GPL-3.0-or-later
/** Authored UNRUN fixtures. No camera/native/runtime execution in this change. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {deviceStartBlocker} from './model.ts';
import type {TetherDevice} from './protocol.ts';

function device(): TetherDevice {
  return {device_id: 'actual-enumerated-id', label: 'fixture, not a real device', connected: true,
    detected_by_runtime: true, recording_format: 'unknown', recording_format_reason: 'unverified', settings: [],
    capabilities: {event_polling: {state: 'verified', reason: 'poll interface only'},
      original_download: {state: 'unknown', reason: 'first actual transfer not yet attempted'},
      remote_shutter: {state: 'unsupported', reason: 'no trigger support'},
      live_view: {state: 'unknown', reason: 'not attempted'}}};
}
test('first session admits unknown download without declaring it verified', () => {
  const value = device();
  assert.equal(deviceStartBlocker(value), null);
  assert.equal(value.capabilities.original_download.state, 'unknown');
});
test('explicit download refusal or unverified events remain blocked', () => {
  const value = device();
  value.capabilities.original_download = {state: 'unsupported', reason: 'driver refused'};
  assert.equal(deviceStartBlocker(value), 'driver refused');
  const other = device(); other.capabilities.event_polling.state = 'unknown';
  assert.notEqual(deviceStartBlocker(other), null);
});
