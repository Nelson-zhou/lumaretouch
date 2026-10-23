import type {FaceRef, ParameterPatch, PeopleContext, PeopleView} from '../people/model';
import type {MaskObject} from '../localMasks/model';
export const OPERATION = 'lnx.hair_colour.v1';
export const IDS = {colour: 'LNX-REF-PC-32472-C-281e093d26', gloss: 'LNX-REF-PC-32472-C-29852ec2fd'};
export const STYLES = [
  ['honey_tea_brown','蜜茶棕'],['chestnut_brown','栗棕'],['sunset_orange','落日橘'],
  ['cool_tea_brown','冷茶棕'],['bitter_flax','苦亚麻'],['natural_black','自然黑'],
  ['rose_purple','玫瑰紫'],['blue_black','蓝黑'],['iris_blue_purple','鸢尾蓝紫'],
  ['raspberry_pink_brown','树莓粉棕'],['maple_red','枫叶红'],['moss_green','苔绿'],
  ['pale_wisteria_pink','薄藤粉'],
] as const;
export type HairStyle = typeof STYLES[number][0];
export type HairRecipe = {version:1;style:HairStyle;strength:number;gloss:number};
export type HairMask = {version:1;domain:'source-normalized';objects:MaskObject[]};
export type HairFact = {requested:boolean;applied:boolean;reason:string|null;changed_pixels:number;support_pixels:number;highlight_pixels:number;recovered_pixels:number;limitation:string;recipe:HairRecipe};
export type HairContext = {face_ref:FaceRef;source:{sha256:string;width:number;height:number};recipe:HairRecipe;support:HairMask;recovery:HairMask;support_reviewed:boolean;facts:HairFact|null;source_png:string;domain:'source-normalized';notice:string};
export type HairPreview = {preview_id:string;kind:'support'|'recovery';face_ref:FaceRef;source:HairContext['source'];overlay_png:string;support_pixels:number;selected_pixels:number;notice:string};
export const neutral = ():HairRecipe => ({version:1,style:'honey_tea_brown',strength:0,gloss:0});
export const emptyMask = ():HairMask => ({version:1,domain:'source-normalized',objects:[]});
export function check(value:unknown):HairRecipe {
  if(value == null) return neutral();
  if(typeof value !== 'object'||Array.isArray(value)) throw Error('头发配方无效');
  const v=value as Record<string,unknown>;
  if(v.version!==1||Object.keys(v).sort().join(',')!=='gloss,strength,style,version'||!STYLES.some(s=>s[0]===v.style)) throw Error('头发配方字段或版本无效');
  for(const key of ['strength','gloss']) if(typeof v[key]!=='number'||!Number.isFinite(v[key])||Number(v[key])<0||Number(v[key])>1) throw Error('头发强度必须在本产品的 0–1 量程内');
  return {version:1,style:v.style as HairStyle,strength:Number(v.strength),gloss:Number(v.gloss)};
}
export function resolvedRecipe(view:PeopleView|null):HairRecipe {
  const values=view?.resolved?.operations[OPERATION];
  if(!values)return neutral();
  return check({version:1,style:values['/style']?.value??neutral().style,strength:values['/strength']?.value??0,gloss:values['/gloss']?.value??0});
}
export function patches(recipe:HairRecipe):ParameterPatch[] {
  const checked=check(recipe);
  return (['style','strength','gloss'] as const).map(key=>({operation_id:OPERATION,parameter_path:`/${key}`,unset:false,value:checked[key]}));
}
export function contextKey(context:PeopleContext):string {return JSON.stringify(context);}
export type HairAction='context'|'preview_support'|'preview_recovery'|'commit_support'|'commit_recovery'|'clear_recovery'|'clear_support';
export type HairRequest={request_id:string;action:HairAction;people_context:PeopleContext;payload:Record<string,unknown>};
export type HairResult={protocol:1;request_id:string;action:HairAction;document_id:string;success:boolean;outcome_unknown:boolean;error?:string;payload:unknown;doc_state?:unknown};
export type HairMailbox={request_id:string;phase:'pending'|'done'|'unavailable';result?:HairResult;error?:string};
export type HairPortState={pending:boolean;uncertain:boolean;checking:boolean;message:string};
export type HairPort={call:<T>(action:HairAction,context:PeopleContext,payload:Record<string,unknown>)=>Promise<T>;recover:()=>Promise<unknown>;pending:()=>boolean;uncertain:()=>boolean;subscribe:(listener:()=>void)=>()=>void;snapshot:()=>HairPortState};
