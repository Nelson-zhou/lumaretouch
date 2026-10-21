/** Identity-safe inspection envelope decoder. Not yet connected to Viewer.
 * Identities stay decimal strings at JSON/ack boundaries, never JS numbers.
 */
export type InspectionIdentity = {
  id:string; document:string; sourceGeneration:string; recipe:string; viewport:string;
};
export type InspectionExpectation = {
  epoch:string; ticket:InspectionIdentity;
  canvasWidth:number; canvasHeight:number;
  roi:{x:number;y:number;width:number;height:number};
  maxPayloadBytes:number;
};
const identityKeys = ['id','document','sourceGeneration','recipe','viewport'] as const;
const HEADER = 128;
const U64_MAX = (1n << 64n) - 1n;

function identity(value:string):bigint {
  if (typeof value !== 'string' || value.length>20 || !/^(0|[1-9][0-9]*)$/.test(value)) {
    throw new Error('Inspection identities require canonical decimal strings');
  }
  const n=BigInt(value);
  if(n>U64_MAX)throw new Error('Inspection identity exceeds u64');
  return n;
}
function u32(value:number):number {
  if(!Number.isInteger(value)||value<0||value>0xffffffff)throw new Error('Invalid inspection dimension');
  return value;
}

export function parseInspectionFrame(buffer:ArrayBuffer, expected:InspectionExpectation) {
  if(!(buffer instanceof ArrayBuffer))throw new Error('Inspection requires an non-shared ArrayBuffer');
  if((buffer as ArrayBuffer & {resizable?:boolean}).resizable===true)throw new Error('Inspection rejects resizable buffers');
  if(buffer.byteLength<HEADER)throw new Error('Truncated inspection header');
  if(!Number.isSafeInteger(expected.maxPayloadBytes)||expected.maxPayloadBytes<0)throw new Error('Invalid inspection budget');
  if(!/^[0-9a-f]{32}$/.test(expected.epoch)||/^0+$/.test(expected.epoch))throw new Error('Invalid engine epoch');
  const view=new DataView(buffer);
  if(view.getUint32(0,true)!==0x4649524c||view.getUint16(4,true)!==1||view.getUint16(6,true)!==HEADER) {
    throw new Error('Inspection protocol mismatch');
  }
  const epoch=Array.from(new Uint8Array(buffer,8,16),x=>x.toString(16).padStart(2,'0')).join('');
  if(epoch!==expected.epoch)throw new Error('Inspection engine epoch mismatch');
  const ticket={} as InspectionIdentity;
  identityKeys.forEach((key,i)=>{
    const n=view.getBigUint64(24+i*8,true);
    if(n!==identity(expected.ticket[key])||(key==='id'&&n===0n))throw new Error('Inspection ticket mismatch');
    ticket[key]=n.toString();
  });
  const dims=[expected.canvasWidth,expected.canvasHeight,expected.roi.x,expected.roi.y,
    expected.roi.width,expected.roi.height].map(u32);
  dims.forEach((n,i)=>{if(view.getUint32(64+i*4,true)!==n)throw new Error('Inspection canvas/ROI mismatch');});
  const [cw,ch,x,y,w,h]=dims;
  if(!cw||!ch||!w||!h||x+w>cw||y+h>ch)throw new Error('Inspection ROI outside canvas');
  const length=BigInt(w)*BigInt(h)*4n;
  if(length!==view.getBigUint64(88,true)||length>BigInt(expected.maxPayloadBytes)||length+128n!==BigInt(buffer.byteLength)) {
    throw new Error('Inspection payload length or budget mismatch');
  }
  if(view.getUint32(96,true)!==0x41424752||view.getUint16(100,true)!==1||view.getUint16(102,true)!==1) {
    throw new Error('Inspection pixel format/profile/quality mismatch');
  }
  const decodedBits=view.getUint16(104,true),sourceBits=view.getUint16(106,true);
  if(![8,16].includes(decodedBits)||sourceBits>32)throw new Error('Inspection precision metadata invalid');
  for(let i=108;i<128;i++)if(view.getUint8(i)!==0)throw new Error('Inspection reserved bytes must be zero');
  // Exact byteLength equality above proves this conversion is representable.
  const pixels=new Uint8ClampedArray(buffer,HEADER,Number(length));
  for(let i=3;i<pixels.length;i+=4)if(pixels[i]!==255)throw new Error('Inspection RGBA must be opaque');
  return {epoch,ticket,canvasWidth:cw,canvasHeight:ch,roi:{x,y,width:w,height:h},
    decodedBits,sourceBits:sourceBits===0?null:sourceBits,pixels};
}
