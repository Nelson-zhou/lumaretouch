import type {ParsedFrame} from './previewFrame';
export interface DisplayGeometry {rasterW:number;rasterH:number;width:number;height:number;documentId:string|null;geometry:string|null;kind:number;instance:string|null}
export function displayGeometry(frame:ParsedFrame):DisplayGeometry {
  const p=frame.presentation;
  return {rasterW:frame.w,rasterH:frame.h,width:p?.width??frame.w,height:p?.height??frame.h,
    documentId:p?.documentId??null,geometry:p?.geometry??null,kind:p?.kind??0,instance:frame.instance};
}
export interface Rect {left:number;top:number;width:number;height:number}
function contain(width:number,height:number,left:number,top:number,boxW:number,boxH:number):Rect{
  const scale=Math.min(boxW/width,boxH/height);
  return {left:left+(boxW-width*scale)/2,top:top+(boxH-height*scale)/2,width:width*scale,height:height*scale};
}
/** Bounded composition raster; each whole photograph preserves its own aspect. */
export function composition(edited:DisplayGeometry,original:DisplayGeometry|null,mode:'single'|'split'|'swipe'){
  const sameDocument=!!original&&!!edited.documentId&&original.documentId===edited.documentId;
  const before=sameDocument?original:null;
  if(mode==='single')return {width:edited.rasterW,height:edited.rasterH,displayWidth:edited.width,displayHeight:edited.height,
    edited:{left:0,top:0,width:edited.rasterW,height:edited.rasterH},original:null,compositionOnly:false};
  const aspect=Math.max(edited.width/edited.height,before?before.width/before.height:0);
  const columns=mode==='split'?2:1;
  const height=Math.max(1,Math.min(edited.rasterH,Math.floor(4096/(aspect*columns)),4096));
  const paneW=Math.max(1,Math.min(Math.floor(4096/columns),Math.round(height*aspect)));
  const width=paneW*columns;
  return {width,height,displayWidth:width,displayHeight:height,
    edited:contain(edited.width,edited.height,mode==='split'?paneW:0,0,paneW,height),
    original:before?contain(before.width,before.height,0,0,paneW,height):null,
    compositionOnly:!!before&&edited.geometry!==before.geometry};
}
export function sameDisplay(a:DisplayGeometry|null,b:DisplayGeometry):boolean {
  return !!a&&a.rasterW===b.rasterW&&a.rasterH===b.rasterH&&a.width===b.width&&a.height===b.height&&
    a.documentId===b.documentId&&a.geometry===b.geometry&&a.kind===b.kind&&a.instance===b.instance;
}

/** Admission is independent of arrival timing and current UI document status. */
export function frameAdmission(current:DisplayGeometry|null,frame:ParsedFrame,mode:'single'|'split'|'swipe',holdOriginal:boolean,skipDraw:boolean){
  const geometry=displayGeometry(frame),complete=frame.y0===0&&frame.rows===frame.h;
  const changed=!sameDisplay(current,geometry);
  const originalCapture=geometry.kind===2&&(mode!=='single'||!holdOriginal);
  const wantsDraw=!skipDraw&&frame.pixelLen>0&&!originalCapture;
  return {geometry,complete,usable:wantsDraw&&(!changed||complete),recoverFull:wantsDraw&&changed&&!complete};
}
