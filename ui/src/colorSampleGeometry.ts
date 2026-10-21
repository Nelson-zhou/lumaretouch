import {imageDisplayRect,type DisplayRect} from './view.ts';
import type {CaptureDescriptor,CapturePoint,CaptureRegion} from './captureModel';
export function captureRect(box:{width:number;height:number},view:{zoom:number;x:number;y:number},capture:CaptureDescriptor):DisplayRect {
  return imageDisplayRect({boxW:box.width,boxH:box.height,frameW:capture.presentation_width,
    frameH:capture.presentation_height,zoom:view.zoom,panX:view.x,panY:view.y});
}
export function capturePoint(x:number,y:number,rect:DisplayRect,width:number,height:number):{x:number;y:number}|null {
  if(![x,y,rect.left,rect.top,rect.width,rect.height,width,height].every(Number.isFinite)||
      rect.width<=0||rect.height<=0||!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0)return null;
  if(x<rect.left||y<rect.top||x>=rect.left+rect.width||y>=rect.top+rect.height)return null;
  return {x:Math.min(width-1,Math.floor((x-rect.left)*width/rect.width)),
    y:Math.min(height-1,Math.floor((y-rect.top)*height/rect.height))};
}
export function neighbourhood(point:CapturePoint,width:number,height:number):CaptureRegion|null {
  if(!Number.isInteger(point.x)||!Number.isInteger(point.y)||![1,3,5,11].includes(point.size)||
    point.x<0||point.y<0||point.x>=width||point.y>=height)return null;
  const radius=(point.size-1)/2,x=Math.max(0,point.x-radius),y=Math.max(0,point.y-radius);
  return {x,y,width:Math.min(width,point.x+radius+1)-x,height:Math.min(height,point.y+radius+1)-y};
}
