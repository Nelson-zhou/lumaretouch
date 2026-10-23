// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState,EngineStatus} from '../native';
import type {Binding} from './model';
/** Loaded-frame identity and persistent document identity are different namespaces.
 * doc.document_id is _load_id; people/body binding.document_id is DocumentVersions.
 * Verify the active load using the former, then retain the latter unchanged. */
export function shoulderBinding(status:EngineStatus|null,doc:DocState|null):Binding|null{
 if(!doc?.document_id||!status?.image?.load_id||status.image.load_id!==doc.document_id)return null;
 const body=doc.shoulder_shape?.binding,people=doc.people?.binding;
 if(body&&people&&(body.document_id!==people.document_id||body.document_epoch!==people.document_epoch||body.asset_sha256!==people.asset_sha256))return null;
 return body??people??null;
}
