/** Producer-bound presentation; legacy frames have no document/geometry proof. */
export interface FramePresentation {documentId:string;width:number;height:number;geometry:string;kind:1|2|3|4}
export interface ParsedFrame {
  seq:number;seqId:string;tEmitNs:number;tPullNs:number;w:number;h:number;pixelLen:number;y0:number;rows:number;
  headerBytes:number;instance:string|null;presentation:FramePresentation|null;pixels:Uint8Array<ArrayBuffer>;bitmap?:ImageBitmap;
}
export function parseFrameHead(buf:ArrayBuffer):ParsedFrame {
  if(buf.byteLength<40)throw Error('预览帧头不完整');
  const v=new DataView(buf),modern=v.getUint32(0,false)===0x4c524631;
  const headerBytes=modern?128:40;
  if(buf.byteLength<headerBytes)throw Error('预览帧头不完整');
  if(modern&&(v.getUint16(4,true)!==1||v.getUint16(6,true)!==128))throw Error('不支持的预览帧协议');
  if(modern)for(let i=100;i<128;i++)if(v.getUint8(i)!==0)throw Error('未知预览帧扩展');
  const offset=modern?8:0,w=v.getUint32(modern?32:24,true),h=v.getUint32(modern?36:28,true);
  const pixelLen=v.getUint32(modern?40:32,true),y0=v.getUint32(modern?44:36,true),rows=pixelLen/(w*4);
  if(!w||!h||y0>=h||!Number.isInteger(rows)||rows>h-y0||buf.byteLength!==headerBytes+pixelLen)throw Error('预览帧像素长度/区域不一致');
  let presentation:FramePresentation|null=null,instance:string|null=null;
  if(modern){
    const hex=Array.from(new Uint8Array(buf,48,16),x=>x.toString(16).padStart(2,'0')).join('');
    instance=hex==='0'.repeat(32)?null:hex;
    const tag=v.getUint32(64,false);
    if(tag===0x4c505231){
      const doc=v.getBigUint64(68,true),width=v.getUint32(76,true),height=v.getUint32(80,true),geometry=v.getBigUint64(84,true),kind=v.getUint32(92,true);
      if(!width||!height||!geometry||kind<1||kind>4||(!doc&&kind!==4)||v.getUint32(96,true)!==0)throw Error('预览构图元数据无效');
      presentation={documentId:doc.toString(),width,height,geometry:geometry.toString(),kind:kind as 1|2|3|4};
    }else if(tag!==0||new Uint8Array(buf,64,36).some(x=>x!==0))throw Error('未知预览构图协议');
  }
  const seq=v.getBigUint64(offset,true);if(seq===0n)throw Error('未提交的预览帧');
  return {seq:Number(seq),seqId:seq.toString(),tEmitNs:Number(v.getBigUint64(offset+8,true)),tPullNs:Number(v.getBigUint64(offset+16,true)),
    w,h,pixelLen,y0,rows,headerBytes,instance,presentation,pixels:new Uint8Array(buf,headerBytes,pixelLen)};
}
