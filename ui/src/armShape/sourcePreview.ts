// SPDX-License-Identifier: GPL-3.0-or-later
import {previewImage,sourceViewport,type SourcePreview as Payload} from '../legShape/sourcePreview';
/** Whole canonical-source PNG, never the edited preview or a cropped proxy. */
export type SourcePreview={url:string;source_sha256:string;width:number;height:number;domain:'canonical-source';displayWidth:number;displayHeight:number;viewport:string};
export function armSourcePreview(payload:Payload|null):SourcePreview|null{
 const image=previewImage(payload);if(!image)return null;
 return {url:image.url,source_sha256:image.source.sha256,width:image.source.width,height:image.source.height,domain:'canonical-source',displayWidth:image.displayWidth,displayHeight:image.displayHeight,viewport:sourceViewport(image)};
}
