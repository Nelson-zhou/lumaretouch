/** Display-only geometry. Match engine/ops/geometry.py: integer crop, then clockwise rotation. */
export type GuideAxis = 'horizontal' | 'vertical';
export interface GuidePoint { x:number; y:number }
export interface GuideRect { left:number; top:number; width:number; height:number }
export interface GuideCrop { rect?:number[]; rotation_degrees?:number; neutral?:boolean; out_full?:number[]|null }
export interface GuideTransform {
  sourceWidth:number; sourceHeight:number;
  cropLeft:number; cropTop:number; cropWidth:number; cropHeight:number;
  outputWidth:number; outputHeight:number; cos:number; sin:number;
  rect:GuideRect;
}
export interface GuideSegment { start:GuidePoint; end:GuidePoint }

/** Python round() uses ties-to-even, unlike Math.round(). Crop boundaries must agree. */
export function roundEven(value:number):number {
  const lower=Math.floor(value),fraction=value-lower;
  return fraction<.5?lower:fraction>.5?lower+1:lower%2===0?lower:lower+1;
}

export function guideTransform(sourceSize:readonly [number,number],crop:GuideCrop|undefined,rect:GuideRect):GuideTransform|null {
  const [sourceWidth,sourceHeight]=sourceSize;
  if(!Number.isSafeInteger(sourceWidth)||!Number.isSafeInteger(sourceHeight)||sourceWidth<1||sourceHeight<1
    ||![rect.left,rect.top,rect.width,rect.height].every(Number.isFinite)||rect.width<=0||rect.height<=0)return null;
  const bounds=crop?.rect??[0,0,1,1],rotation=crop?.rotation_degrees??0;
  if(bounds.length!==4||!bounds.every(value=>Number.isFinite(value)&&value>=0&&value<=1)
    ||bounds[0]>=bounds[2]||bounds[1]>=bounds[3]||!Number.isFinite(rotation)||Math.abs(rotation)>180+1e-12)return null;
  const cut=(size:number,low:number,high:number):[number,number]=>{
    const first=Math.min(Math.max(roundEven(size*low),0),size-1);
    return [first,Math.min(Math.max(roundEven(size*high),first+1),size)];
  };
  const [cropLeft,right]=cut(sourceWidth,bounds[0],bounds[2]);
  const [cropTop,bottom]=cut(sourceHeight,bounds[1],bounds[3]);
  const cropWidth=right-cropLeft,cropHeight=bottom-cropTop;
  const remainder=Math.abs(rotation)%90;
  // The renderer's compatibility snap is STRICT: exactly ±0.5° is not snapped.
  const quarter=remainder<.5||Math.abs(remainder-90)<.5?((roundEven(rotation/90)%4)+4)%4:null;
  const radians=rotation*Math.PI/180;
  const cos=quarter===null?Math.cos(radians):[1,0,-1,0][quarter];
  const sin=quarter===null?Math.sin(radians):[0,1,0,-1][quarter];
  const outputWidth=Math.max(1,roundEven(cropWidth*Math.abs(cos)+cropHeight*Math.abs(sin)));
  const outputHeight=Math.max(1,roundEven(cropWidth*Math.abs(sin)+cropHeight*Math.abs(cos)));
  return {sourceWidth,sourceHeight,cropLeft,cropTop,cropWidth,cropHeight,outputWidth,outputHeight,cos,sin,rect};
}

/** Source-normalized pixel-edge coordinates. Pixel centers are (index + .5) / size. */
export function sourceToDisplay(point:GuidePoint,transform:GuideTransform):GuidePoint {
  const t=transform;
  const x=point.x*t.sourceWidth-t.cropLeft-t.cropWidth/2;
  const y=point.y*t.sourceHeight-t.cropTop-t.cropHeight/2;
  return {x:t.rect.left+(t.cos*x-t.sin*y+t.outputWidth/2)/t.outputWidth*t.rect.width,
    y:t.rect.top+(t.sin*x+t.cos*y+t.outputHeight/2)/t.outputHeight*t.rect.height};
}

/** Inverse is deliberately unclamped so captured drags keep their original grab offset. */
export function displayToSource(point:GuidePoint,transform:GuideTransform):GuidePoint {
  const t=transform;
  const x=(point.x-t.rect.left)/t.rect.width*t.outputWidth-t.outputWidth/2;
  const y=(point.y-t.rect.top)/t.rect.height*t.outputHeight-t.outputHeight/2;
  return {x:(t.cos*x+t.sin*y+t.cropWidth/2+t.cropLeft)/t.sourceWidth,
    y:(-t.sin*x+t.cos*y+t.cropHeight/2+t.cropTop)/t.sourceHeight};
}

/** Liang–Barsky clipping also keeps hit targets out of letterboxes and toolbar regions. */
export function clipGuideSegment(segment:GuideSegment,rect:GuideRect):GuideSegment|null {
  if(rect.width<=0||rect.height<=0)return null;
  const {start,end}=segment,dx=end.x-start.x,dy=end.y-start.y;
  let low=0,high=1;
  const p=[-dx,dx,-dy,dy],q=[start.x-rect.left,rect.left+rect.width-start.x,start.y-rect.top,rect.top+rect.height-start.y];
  for(let index=0;index<4;index++){
    if(Math.abs(p[index])<1e-12){if(q[index]<0)return null;continue;}
    const fraction=q[index]/p[index];
    if(p[index]<0)low=Math.max(low,fraction);else high=Math.min(high,fraction);
    if(low>high)return null;
  }
  return {start:{x:start.x+low*dx,y:start.y+low*dy},end:{x:start.x+high*dx,y:start.y+high*dy}};
}

export function guideSegment(transform:GuideTransform,axis:GuideAxis,position:number):GuideSegment|null {
  if(!Number.isFinite(position)||position<0||position>1)return null;
  const t=transform,left=t.cropLeft/t.sourceWidth,right=(t.cropLeft+t.cropWidth)/t.sourceWidth;
  const top=t.cropTop/t.sourceHeight,bottom=(t.cropTop+t.cropHeight)/t.sourceHeight;
  if(axis==='vertical'?(position<left||position>right):(position<top||position>bottom))return null;
  const start=axis==='vertical'?{x:position,y:top}:{x:left,y:position};
  const end=axis==='vertical'?{x:position,y:bottom}:{x:right,y:position};
  return clipGuideSegment({start:sourceToDisplay(start,t),end:sourceToDisplay(end,t)},t.rect);
}

/** Project a screen-space arrow onto this guide's source-coordinate movement axis. */
export function guideKeyboardDelta(transform:GuideTransform,axis:GuideAxis,key:string,step=1):number {
  const t=transform;
  const dx=axis==='vertical'?t.cos*t.sourceWidth*t.rect.width/t.outputWidth:-t.sin*t.sourceHeight*t.rect.width/t.outputWidth;
  const dy=axis==='vertical'?t.sin*t.sourceWidth*t.rect.height/t.outputHeight:t.cos*t.sourceHeight*t.rect.height/t.outputHeight;
  const x=key==='ArrowRight'?step:key==='ArrowLeft'?-step:0;
  const y=key==='ArrowDown'?step:key==='ArrowUp'?-step:0;
  return (x*dx+y*dy)/(dx*dx+dy*dy);
}
