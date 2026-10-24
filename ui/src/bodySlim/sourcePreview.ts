// SPDX-License-Identifier: GPL-3.0-or-later
import type {Source} from './model';
/** Backend proves a whole, EXIF-normalized source -> ALIGN8 decode -> PNG view.
 * The preview is not full-size source pixels and must never be labeled as such. */
export type SourcePreview={mime:'image/png';base64:string;source_sha256:string;source_width:number;source_height:number;decoded_width:number;decoded_height:number;width:number;height:number;mapping:'normalized_full_frame';orientation:'exif_normalized_once'};
export type SourceImage={url:string;source:Source;decodedWidth:number;decodedHeight:number;displayWidth:number;displayHeight:number;mapping:'normalized_full_frame'};
function extent(n:number):boolean{return Number.isSafeInteger(n)&&n>=2&&n<=1_000_000;}
export function previewImage(preview:SourcePreview|null):SourceImage|null{
 if(!preview||preview.mime!=='image/png'||preview.mapping!=='normalized_full_frame'||preview.orientation!=='exif_normalized_once'||!preview.base64||!/^[a-f0-9]{64}$/.test(preview.source_sha256))return null;
 const {source_width:w,source_height:h,decoded_width:dw,decoded_height:dh,width:pw,height:ph}=preview;
 if(![w,h,dw,dh,pw,ph].every(extent)||dw>w||dh>h||pw>dw||ph>dh||pw>1280||ph>1280)return null;
 if((dw!==w||dh!==h)&&(dw%8!==0||dh%8!==0||dw*h>=(dh+8)*w||dh*w>=(dw+8)*h))return null;
 // PIL thumbnail retains the whole canvas; one-pixel integer aspect rounding is allowed.
 if(Math.max(dw,dh)<=1280?(pw!==dw||ph!==dh):(Math.max(pw,ph)!==1280||Math.abs(pw*dh-ph*dw)>Math.max(dw,dh)))return null;
 return {url:`data:${preview.mime};base64,${preview.base64}`,source:{sha256:preview.source_sha256,width:w,height:h,orientation:preview.orientation},decodedWidth:dw,decodedHeight:dh,displayWidth:pw,displayHeight:ph,mapping:preview.mapping};
}
export function matchesSource(image:SourceImage|null,source:Source):image is SourceImage{
 return !!image&&image.mapping==='normalized_full_frame'&&image.source.sha256===source.sha256&&image.source.width===source.width&&image.source.height===source.height&&image.source.orientation===source.orientation;
}

/** Landmarks use source-normalized pixel centres. The PNG covers complete decoded
 * pixel edges, not the source's nominal raster size. No cropped/edited proxy fits. */
export function sourceViewport(image:SourceImage):string{
 const sx=(image.source.width-1)/(image.decodedWidth-1),sy=(image.source.height-1)/(image.decodedHeight-1);
 return `${-.5*sx} ${-.5*sy} ${image.decodedWidth*sx} ${image.decodedHeight*sy}`;
}
