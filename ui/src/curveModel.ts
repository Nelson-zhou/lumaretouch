import type {CurveSpec} from './native';
export const curveSignature=(s:CurveSpec)=>JSON.stringify([s.version,s.space,s.interpolation,s.boundary,s.enabled,
  s.master,s.red,s.green,s.blue]);
export function movedCurvePoint(points:[number,number][],i:number,x:number,y:number):[number,number]{
  const clamp=(v:number,lo:number,hi:number)=>Math.max(lo,Math.min(hi,v));
  const lo=i>0?points[i-1][0]+1e-5:0,hi=i<points.length-1?points[i+1][0]-1e-5:1;
  let nx=i===0?0:i===points.length-1?1:x===points[i][0]?x:lo<=hi?clamp(x,lo,hi):points[i][0];
  if(i>0&&i<points.length-1&&(nx-points[i-1][0]<1e-5||points[i+1][0]-nx<1e-5))nx=points[i][0];
  return [nx,clamp(y,0,1)];
}
export function matchesCurveResult(pendingId:string|undefined,resultId:string|undefined){
  return !!pendingId && pendingId===resultId;
}
