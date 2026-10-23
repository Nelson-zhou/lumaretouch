/** View metadata only. Source-normalized lines never enter the pixel recipe. */
export type Axis='horizontal'|'vertical';
export interface Guide {id:string;axis:Axis;position:number}
export interface GuideState {visible:boolean;lines:Guide[]}
export interface GuideReport extends GuideState {
  protocol:1;document_id:string;load_id:string;workspace:string;revision:number;geometry:string;
  undo_steps:number;redo_steps:number;view_only:true;
}
export const emptyGuides:GuideState={visible:true,lines:[]};
export function isReport(value:unknown):value is GuideReport {
  const p=value as GuideReport|undefined;
  return !!p&&p.protocol===1&&p.view_only===true&&typeof p.visible==='boolean'
    &&typeof p.document_id==='string'&&!!p.document_id&&typeof p.load_id==='string'&&!!p.load_id
    &&typeof p.geometry==='string'&&/^[1-9][0-9]*$/.test(p.geometry)
    &&typeof p.workspace==='string'&&!!p.workspace&&Number.isSafeInteger(p.revision)&&p.revision>=0
    &&Number.isSafeInteger(p.undo_steps)&&p.undo_steps>=0&&Number.isSafeInteger(p.redo_steps)&&p.redo_steps>=0
    &&Array.isArray(p.lines)&&p.lines.length<=128&&new Set(p.lines.map(x=>x?.id)).size===p.lines.length
    &&p.lines.every(x=>x&&typeof x.id==='string'&&x.id.length>0&&x.id.length<=128
      &&(x.axis==='horizontal'||x.axis==='vertical')&&Number.isFinite(x.position)&&x.position>=0&&x.position<=1);
}
export interface GuideModes {
  available:boolean;compare:boolean;reference:boolean;brush:boolean;mask:boolean;category:boolean;crop:boolean;
  inspection:boolean;picker:boolean;manual:boolean;repair:boolean;busy:boolean;
}
export function guidePolicy(m:GuideModes){
  const hidden=!m.available||m.compare||m.reference||m.brush||m.mask||m.category||m.crop||m.inspection||m.picker;
  return {hidden,locked:hidden||m.manual||m.repair||m.busy,
    reason:hidden?'当前视图暂时隐藏参考线，退出后恢复手动显隐设置':m.manual||m.repair?'手动液化 / 修复中参考线仅供查看，不能移动':m.busy?'等待当前操作完成':'参考线仅辅助查看，不写入照片或导出'};
}
