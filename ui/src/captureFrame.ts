import type {CaptureDescriptor} from './captureModel';
export const CAPTURE_HEADER_BYTES=128;
export const CAPTURE_MAX_BYTES=128*1024*1024;
export interface VerifiedCapture {readonly descriptor:Readonly<CaptureDescriptor>;readonly rgba:Uint8ClampedArray<ArrayBuffer>}
const hex=(view:DataView,offset:number)=>Array.from({length:16},(_,i)=>view.getUint8(offset+i).toString(16).padStart(2,'0')).join('');
export function parseCaptureFrame(buffer:ArrayBuffer,expected:CaptureDescriptor,expectedDomain:CaptureDescriptor['domain']='proxy-output'):VerifiedCapture {
  if(buffer.byteLength<CAPTURE_HEADER_BYTES||buffer.byteLength>CAPTURE_MAX_BYTES+CAPTURE_HEADER_BYTES)
    throw new Error('采样画面长度越界');
  const v=new DataView(buffer);
  if(v.getUint32(0,false)!==0x4c524350||v.getUint16(4,true)!==1||v.getUint16(6,true)!==128)
    throw new Error('采样画面协议不匹配');
  for(let i=112;i<128;i++)if(v.getUint8(i)!==0)throw new Error('采样画面保留字段不为零');
  const quality=expectedDomain==='wb-input'?'proxy-linear-input':(expectedDomain==='repair-input'||expectedDomain==='source-input')?'proxy-float-input':'proxy-float-output';
  if(!['proxy-output','repair-input','source-input','wb-input'].includes(expectedDomain)||expected.version!==1||expected.domain!==expectedDomain||expected.profile!=='working-srgb'||expected.quality!==quality)
    throw new Error('不支持的采样画面来源');
  for(const [field,offset] of [['epoch',8],['shm_instance',24],['capture_id',40]] as const){
    const value=hex(v,offset);
    if(value==='0'.repeat(32)||value!==expected[field])throw new Error('采样画面身份已失效');
  }
  for(const [field,offset] of [['seq',56],['generation',64],['document_id',72],['ticket',80]] as const){
    const value=v.getBigUint64(offset,true);
    if(value===0n||value.toString()!==expected[field])throw new Error('采样画面版本已失效');
  }
  const w=v.getUint32(88,true),h=v.getUint32(92,true);
  if(w===0||h===0||w>Math.floor(CAPTURE_MAX_BYTES/(h*4)))throw new Error('采样画面尺寸越界');
  for(const [field,offset] of [['width',88],['height',92],['presentation_width',96],['presentation_height',100]] as const){
    if(v.getUint32(offset,true)===0||v.getUint32(offset,true)!==expected[field])throw new Error('采样画面几何已失效');
  }
  const length=w*h*4;
  if(v.getBigUint64(104,true)!==BigInt(length)||buffer.byteLength!==128+length)
    throw new Error('采样画面像素不完整');
  return {descriptor:Object.freeze({...expected}),rgba:new Uint8ClampedArray(buffer,128,length)};
}
