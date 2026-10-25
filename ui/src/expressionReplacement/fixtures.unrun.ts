// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED UNRUN. Metadata-only placeholders, never display or image acceptance evidence.
import {CONFIRMATION_KEYS,OPERATION_ID,emptyFusion,packet,previewCommand,type Confirmations,type Current,type Face,type Photograph,type PreviewCommand,type Source} from './model.ts';
export const H=(character:string)=>character.repeat(64);
export const source=(character='a'):Source=>({asset_sha256:H(character),original_sha256:H(character),source_kind:'original',width:640,height:480,orientation:'exif_normalized_once',retained_asset_id:`retained-${character}`});
export const face=(s:Source):Face=>({face_ref:{asset_sha256:s.asset_sha256,face_instance_id:'face-1',analysis_revision:2},enabled:true,analysis_status:'verified',manual:false,landmarks_count:478,landmarks_sha256:H('b'),crop:{left:100,top:80,width:200,height:200},eligibility_sha256:H('c'),protection_sha256:H('d')});
export function photograph(character='a'):Photograph{
  const s=source(character);
  return {source:s,label:`fixture-${character}`,faces:[face(s)],image:{mime:'image/png',width:640,height:480,sha256:H('e'),base64:'iVBOR'+'A'.repeat(35),source_sha256:s.asset_sha256,source_width:640,source_height:480,mapping:'normalized_full_frame',orientation:'exif_normalized_once'}};
}
export function current():Current{
  const photo=photograph();return {binding:{document_id:'photo-1',document_epoch:'epoch-1',load_id:'load-1',document_revision:3,state_revision:4,association_revision:5,people_graph_sha256:H('f'),source:photo.source},photo,available:true,unavailable_reason:null};
}
export function command():PreviewCommand{
  const c=current(),d=photograph('b');return previewCommand({version:1,operation_id:OPERATION_ID,action:'preview',request_id:'preview-1',binding:c.binding,
    target:{source:c.photo.source,face:c.photo.faces[0]},donor:{source:d.source,face:d.faces[0]},settings:{density:1,pyramid_levels:3,colour_match_strength:0},
    fusion:{...emptyFusion(),strokes:[{mode:'add',radius_px:12,points:[[150/639,130/479]]}]},confirmations:Object.fromEntries(CONFIRMATION_KEYS.map(key=>[key,true])) as Confirmations});
}
export function ready(sent:Awaited<ReturnType<typeof packet<PreviewCommand>>>){
  const image=photograph().image;return {version:1,operation_id:OPERATION_ID,request_id:sent.command.request_id,command_sha256:sent.command_sha256,action:'preview',binding:sent.command.binding,phase:'ready',
    preview:{preview_token:'token-1',candidate_sha256:H('1'),fusion_mask_sha256:H('2'),output_width:640,output_height:480,before:image,after:{...image,sha256:H('3')},fusion_image:{...image,sha256:H('4')}}};
}
