// SPDX-License-Identifier: GPL-3.0-or-later
import type {Source} from '../legShape/model';
export type SourcePreview={mime:'image/png';base64:string;source:{sha256:string;width:number;height:number};width:number;height:number;view_box:[number,number,number,number];mapping:'source_pixel_centre_eye_crop';minimum_iris_radius:number};
export type SourceImage={url:string;source:Source;displayWidth:number;displayHeight:number;viewBox:string};
export function previewImage(v:SourcePreview|null):SourceImage|null {
 if(!v||v.mapping!=='source_pixel_centre_eye_crop'||v.mime!=='image/png'||!v.base64||!/^[a-f0-9]{64}$/.test(v.source.sha256)||![v.width,v.height,v.source.width,v.source.height].every(n=>Number.isSafeInteger(n)&&n>=2)||v.width>1280||v.height>1280||!Number.isFinite(v.minimum_iris_radius)||v.minimum_iris_radius<8||v.view_box.length!==4||!v.view_box.every(Number.isFinite)||v.view_box[2]<=0||v.view_box[3]<=0)return null;
 return {url:`data:image/png;base64,${v.base64}`,source:{...v.source,orientation:'exif_normalized_once'},displayWidth:v.width,displayHeight:v.height,viewBox:v.view_box.join(' ')};
}
export function matchesSource(image:SourceImage|null,source:Source):image is SourceImage{return !!image&&image.source.sha256===source.sha256&&image.source.width===source.width&&image.source.height===source.height&&image.source.orientation===source.orientation;}
export function sourceViewport(image:SourceImage):string{return image.viewBox;}
