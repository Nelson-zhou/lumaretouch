import type {CurveSpec,ParametricSpec} from './native';
export const curveSignature=(s:CurveSpec)=>JSON.stringify([s.version,s.space,s.interpolation,s.boundary,s.enabled,
  s.master,s.red,s.green,s.blue,s.luminance_space,s.luminance,
  s.parametric&&[s.parametric.version,s.parametric.algorithm,s.parametric.space,s.parametric.grid,s.parametric.boundary,s.parametric.enabled,
  s.parametric.shadows,s.parametric.darks,s.parametric.lights,s.parametric.highlights,s.parametric.splits]]);
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

export type EditableCurveSpec=CurveSpec & {luminance:[number,number][]};
export function editableCurveSpec(s:CurveSpec):EditableCurveSpec {
  const luminance:[number,number][]=s.luminance??[[0,0],[1,1]];
  return {...structuredClone(s),version:s.version===3?3:2,luminance_space:'linear-srgb-y-ratio',
    luminance:structuredClone(luminance)};
}

export const neutralParametric=():ParametricSpec=>({version:1,algorithm:'lrt-rt512-parametric-splitgrid-lut-v1',space:'srgb-display',
  grid:'split-aligned-4x16384',boundary:'identity-outside-unit',enabled:true,shadows:0,darks:0,lights:0,highlights:0,splits:[.25,.5,.75]});
export function parametricCurveSpec(s:CurveSpec):EditableCurveSpec&{parametric:ParametricSpec}{
  return {...editableCurveSpec(s),version:3,parametric:structuredClone(s.parametric??neutralParametric())};
}

export function curveEditSnapshot(s:CurveSpec){
  return {raw:structuredClone(s),editable:editableCurveSpec(s)};
}
