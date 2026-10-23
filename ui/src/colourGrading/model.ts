export type Range = 'shadows'|'midtones'|'highlights'|'global';
export type Wheel = {hue:number;saturation:number;luminance:number};
export type Recipe = {version:1;algorithm:'lrt-tonal-opponent-v1';working_space:'linear-srgb-d65';shadows:Wheel;midtones:Wheel;highlights:Wheel;global:Wheel;blending:number;balance:number};
export const ranges:Range[]=['shadows','midtones','highlights','global'];
export function neutral():Recipe {return {version:1,algorithm:'lrt-tonal-opponent-v1',working_space:'linear-srgb-d65',shadows:{hue:0,saturation:0,luminance:0},midtones:{hue:0,saturation:0,luminance:0},highlights:{hue:0,saturation:0,luminance:0},global:{hue:0,saturation:0,luminance:0},blending:50,balance:0};}
export function checked(r:Recipe):Recipe {
  if(!r||Object.keys(r).sort().join()!==Object.keys(neutral()).sort().join()||r.version!==1||r.algorithm!=='lrt-tonal-opponent-v1'||r.working_space!=='linear-srgb-d65')throw Error('颜色分级版本或字段无效');
  const n=(v:number,min:number,max:number)=>{if(typeof v!=='number'||!Number.isFinite(v)||v<min||v>max)throw Error('颜色分级数值超出范围');return v;};
  const out=neutral();for(const k of ranges){const w=r[k];if(!w||Object.keys(w).sort().join()!=='hue,luminance,saturation')throw Error('颜色分级色轮字段无效');out[k]={hue:n(w.hue,0,360)%360,saturation:n(w.saturation,0,100),luminance:n(w.luminance,-100,100)};}
  out.blending=n(r.blending,0,100);out.balance=n(r.balance,-100,100);return out;
}
export function wheelAt(x:number,y:number,w:Wheel):Wheel {const radius=Math.hypot(x,y);return {...w,hue:radius<0.00001?w.hue:(Math.atan2(y,x)*180/Math.PI+360)%360,saturation:Math.min(100,radius*100)};}
export const requirements={parent:'PC-32455-C-f13fcb2a36',highlights:'PC-32455-C-70e9de0dd5',shadows:'PC-32455-C-e9dd04bf09',midtones:'PC-32455-C-af57303f9a',global:'PC-32455-C-9dbe7ace64',blending:'PC-32455-C-a068ef2242',balance:'PC-32455-C-f4147a1001',luminance:'PC-32455-C-a25ffd787b'} as const;
