export const LEVEL_CHANNELS=['master','red','green','blue'] as const;
export type LevelsChannel=typeof LEVEL_CHANNELS[number];
export const LEVEL_KEYS=['input_black','input_white','gamma','output_black','output_white'] as const;
export type LevelKey=typeof LEVEL_KEYS[number];
export type LevelsBand=Record<LevelKey,number>;
export type LevelsSpec={version:1;space:'srgb-display';enabled:boolean}&Record<LevelsChannel,LevelsBand>;
export const neutralBand=():LevelsBand=>({input_black:0,input_white:1,gamma:1,output_black:0,output_white:1});
export const neutralLevels=():LevelsSpec=>({version:1,space:'srgb-display',enabled:true,
  master:neutralBand(),red:neutralBand(),green:neutralBand(),blue:neutralBand()});
export const levelsSignature=(s:LevelsSpec)=>JSON.stringify([s.version,s.space,s.enabled,...LEVEL_CHANNELS.map(c=>LEVEL_KEYS.map(k=>s[c][k]))]);
export function changedLevel(s:LevelsSpec,channel:LevelsChannel,key:LevelKey,value:number):LevelsSpec {
  if(!Number.isFinite(value))throw new Error('色阶需要有限数值');
  const next=structuredClone(s),band=next[channel];
  const low=key==='gamma'?.1:key==='input_white'?band.input_black+1e-5:0;
  const high=key==='gamma'?10:key==='input_black'?band.input_white-1e-5:1;
  band[key]=Math.max(low,Math.min(high,value));
  // Floating endpoint rounding must not manufacture a forbidden gap.
  if(band.input_white-band.input_black<1e-5){
    if(key==='input_black')band.input_black=Math.max(0,band.input_white-1e-5-Number.EPSILON);
    else if(key==='input_white')band.input_white=Math.min(1,band.input_black+1e-5+Number.EPSILON);
    else throw new Error('输入白点与黑点距离过近');
  }
  return next;
}
export const levelsMidpoint=(band:LevelsBand)=>band.input_black+(band.input_white-band.input_black)*Math.pow(.5,band.gamma);
export function gammaFromMidpoint(band:LevelsBand,value:number){
  if(!Number.isFinite(value))throw new Error('灰点需要有限数值');
  const normalized=(value-band.input_black)/(band.input_white-band.input_black);
  const clamped=Math.max(Math.pow(.5,10),Math.min(Math.pow(.5,.1),normalized));
  return Math.log(clamped)/Math.log(.5);
}
