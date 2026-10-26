// SPDX-License-Identifier: GPL-3.0-or-later
import type {ModelStatus} from '../promptedMasks/curatedExtension';
const EXTENSION='hand-landmarker-v1';
export function handModelReady(value:ModelStatus|null):boolean{
 return value?.extension_id===EXTENSION&&!value.running&&!value.error&&value.result?.state==='installed'
  &&value.result.installed===true&&value.result.ready===true&&value.result.checkpoint_verified===true
  &&value.result.readiness==='cpu-probe-passed'&&!value.result.error;
}
