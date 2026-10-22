import {capturePoint} from '../colorSampleGeometry.ts';
import type {DisplayRect} from '../view';

/** All persisted gesture coordinates are display-normalized, never screen pixels. */
export type Point = [number, number];
export const MAX_POLYGON_POINTS = 256;

export function normalizedPoint(x:number,y:number,rect:DisplayRect,width:number,height:number):Point|null {
  if(!capturePoint(x,y,rect,width,height))return null;
  return [(x-rect.left)/rect.width,(y-rect.top)/rect.height];
}

export function appendLasso(points:Point[],point:Point):Point[] {
  const last=points.at(-1);
  if(last&&Math.hypot(last[0]-point[0],last[1]-point[1])<0.0005)return points;
  const next=[...points,point];
  if(next.length<=MAX_POLYGON_POINTS)return next;
  // Keep the beginning and latest point instead of silently truncating the gesture.
  return next.filter((_,index)=>index%2===0||index===next.length-1);
}

const cross=(a:Point,b:Point,c:Point)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
const between=(a:Point,b:Point,p:Point)=>Math.abs(cross(a,b,p))<1e-10&&
  p[0]>=Math.min(a[0],b[0])-1e-10&&p[0]<=Math.max(a[0],b[0])+1e-10&&
  p[1]>=Math.min(a[1],b[1])-1e-10&&p[1]<=Math.max(a[1],b[1])+1e-10;
function intersects(a:Point,b:Point,c:Point,d:Point){
  const ab1=cross(a,b,c),ab2=cross(a,b,d),cd1=cross(c,d,a),cd2=cross(c,d,b);
  return (ab1*ab2<0&&cd1*cd2<0)||between(a,b,c)||between(a,b,d)||between(c,d,a)||between(c,d,b);
}

export function polygonError(polygon:Point[]):string|null {
  if(polygon.length<3||polygon.length>MAX_POLYGON_POINTS)return '请圈出至少三个点的目标区域';
  if(polygon.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v)||v<0||v>1)))return '目标区域超出取样画面';
  let area=0;
  for(let i=0;i<polygon.length;i++){
    const a=polygon[i],b=polygon[(i+1)%polygon.length];
    if(Math.hypot(a[0]-b[0],a[1]-b[1])<1e-8)return '目标边界包含重复点，请重新圈选';
    area+=a[0]*b[1]-b[0]*a[1];
    for(let j=i+2;j<polygon.length;j++){
      if(i===0&&j===polygon.length-1)continue;
      if(intersects(a,b,polygon[j],polygon[(j+1)%polygon.length]))return '目标边界不能交叉，请重新圈选';
    }
  }
  return Math.abs(area)<0.000002?'目标区域太小，请重新圈选':null;
}

export function clampOffset(polygon:Point[],offset:Point):Point {
  if(!polygon.length||!offset.every(Number.isFinite))return [0,0];
  const xs=polygon.map(p=>p[0]),ys=polygon.map(p=>p[1]);
  return [Math.max(-Math.min(...xs),Math.min(1-Math.max(...xs),offset[0])),
    Math.max(-Math.min(...ys),Math.min(1-Math.max(...ys),offset[1]))];
}

export function sourceError(polygon:Point[],offset:Point):string|null {
  const invalid=polygonError(polygon);if(invalid)return invalid;
  if(!offset.every(Number.isFinite)||Math.hypot(...offset)<1e-8)return '请拖动同形轮廓，选择与目标不同的来源';
  if(polygon.some(([x,y])=>x+offset[0]<0||x+offset[0]>1||y+offset[1]<0||y+offset[1]>1))return '来源区域必须完整位于取样画面内';
  return null;
}

export function insidePolygon(point:Point,polygon:Point[],offset:Point=[0,0]):boolean {
  const p:Point=[point[0]-offset[0],point[1]-offset[1]];let inside=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
    const a=polygon[i],b=polygon[j];
    if(between(a,b,p))return true;
    if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
  }
  return inside;
}

export function center(polygon:Point[]):Point {
  return polygon.length?[polygon.reduce((n,p)=>n+p[0],0)/polygon.length,polygon.reduce((n,p)=>n+p[1],0)/polygon.length]:[0,0];
}
