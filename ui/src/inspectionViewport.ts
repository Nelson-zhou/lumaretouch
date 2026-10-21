import {imageDisplayRect,fitScaleOf} from './view.ts';

export type InspectionBox={left:number;top:number;width:number;height:number};
export function inspectionLayout(box:InspectionBox,canvasWidth:number,canvasHeight:number,
  view:{zoom:number;x:number;y:number},dpr:number,oneToOne:boolean){
  if(![box.left,box.top,box.width,box.height,canvasWidth,canvasHeight,view.zoom,view.x,view.y,dpr].every(Number.isFinite)
     || Math.min(box.width,box.height,canvasWidth,canvasHeight,view.zoom,dpr)<=0
     || ![canvasWidth,canvasHeight].every(n=>Number.isInteger(n)&&n<=0xffffffff))return null;
  const fit=fitScaleOf(box.width,box.height,canvasWidth,canvasHeight);
  const zoom=oneToOne?1/(dpr*fit):view.zoom;
  const rect=imageDisplayRect({boxW:box.width,boxH:box.height,frameW:canvasWidth,frameH:canvasHeight,
    zoom,panX:view.x,panY:view.y});
  // Align the absolute origin, not merely the offset inside a fractional CSS box.
  rect.left=Math.round((box.left+rect.left)*dpr)/dpr-box.left;
  rect.top=Math.round((box.top+rect.top)*dpr)/dpr-box.top;
  const sx=rect.width/canvasWidth,sy=rect.height/canvasHeight;
  const x=Math.max(0,Math.min(canvasWidth,Math.floor(-rect.left/sx)));
  const y=Math.max(0,Math.min(canvasHeight,Math.floor(-rect.top/sy)));
  const right=Math.max(0,Math.min(canvasWidth,Math.ceil((box.width-rect.left)/sx)));
  const bottom=Math.max(0,Math.min(canvasHeight,Math.ceil((box.height-rect.top)/sy)));
  const roi=right>x&&bottom>y?{x,y,width:right-x,height:bottom-y}:null;
  return {fit,zoom,rect,roi,patch:roi?{left:rect.left+x*sx,top:rect.top+y*sy,width:roi.width*sx,height:roi.height*sy}:null};
}
