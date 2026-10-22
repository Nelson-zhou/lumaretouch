import {CAPTURE_MAX_BYTES,type VerifiedCapture} from '../captureFrame.ts';
import type {CaptureDescriptor} from '../captureModel';

// Display diagnostics only. These arrays never become a sampled source, a
// retained mask, a request payload, or an export input.
const linearSrgb8=Float64Array.from({length:256},(_,i)=>{
  const value=i/255;
  return value<=.04045?value/12.92:Math.pow((value+.055)/1.055,2.4);
});

export function sourceLuminanceFromSrgb8(red:number,green:number,blue:number):number {
  return .2126*linearSrgb8[red]+.7152*linearSrgb8[green]+.0722*linearSrgb8[blue];
}

function validRows(descriptor:Readonly<CaptureDescriptor>):boolean {
  const rows=descriptor.sample_valid_rows;
  return Array.isArray(rows)&&rows.length===descriptor.height&&rows.length<=8192&&
    rows.every(row=>Array.isArray(row)&&row.length===2&&row.every(Number.isSafeInteger)&&
      row[0]>=0&&row[0]<=row[1]&&row[1]<=descriptor.width);
}

export function luminanceMapUnavailableReason(descriptor:Readonly<CaptureDescriptor>|null):string|null {
  if(!descriptor)return '请先打开原始源图范围查看或审核';
  if(descriptor.domain!=='source-input'||descriptor.profile!=='working-srgb'||descriptor.mask_overlay!==true)
    return '此画面没有原始源图与已保存覆盖数据';
  if(descriptor.mask_suspended)return `已保存蒙版暂停：${descriptor.mask_suspended}`;
  if(!validRows(descriptor))return '此画面未提供完整的采样有效域，无法区分源图与构图填充';
  if(!descriptor.sample_valid_rows!.some(([start,end])=>end>start))return '此画面没有可用的源图像素';
  return null;
}

/** Linear-light Y is encoded back to neutral sRGB for display. Unlike a CSS
 * grayscale filter, coverage stays colored and Y never includes coverage alpha.
 * RGB8/crop interpolation make this a proxy diagnostic, not full-source proof. */
export function savedMaskDisplay(frame:VerifiedCapture,luminanceMap:boolean) {
  const d=frame.descriptor,length=d.width*d.height*4;
  if(d.domain!=='source-input'||d.profile!=='working-srgb'||d.mask_overlay!==true||
    !Number.isSafeInteger(length)||length<=0||length>CAPTURE_MAX_BYTES||frame.rgba.length!==length)
    throw Error('原始源图蒙版显示数据无效');
  if(luminanceMap){
    const reason=luminanceMapUnavailableReason(d);
    if(reason)throw Error(reason);
  }
  const base=new Uint8ClampedArray(frame.rgba),coverage=new Uint8ClampedArray(length);
  // Exactly two bounded display buffers, as in the normal RGB overlay. The
  // original RGBA includes the saved-composition alpha and is never written.
  for(let y=0;y<d.height;y++){
    const row=luminanceMap?d.sample_valid_rows![y]:null;
    for(let x=0;x<d.width;x++){
      const i=(y*d.width+x)*4,valid=!row||(x>=row[0]&&x<row[1]);
      if(luminanceMap){
        let gray:number;
        if(valid){
          const value=sourceLuminanceFromSrgb8(frame.rgba[i],frame.rgba[i+1],frame.rgba[i+2]);
          const encoded=value<=.0031308?12.92*value:1.055*Math.pow(value,1/2.4)-.055;
          gray=Math.round(Math.max(0,Math.min(1,encoded))*255);
        }else{
          // Padding is not a black source pixel or an inverted selected pixel.
          gray=((Math.floor(x/8)+Math.floor(y/8))%2)?34:44;
        }
        base[i]=base[i+1]=base[i+2]=gray;
      }
      base[i+3]=255;
      coverage[i]=40;coverage[i+1]=220;coverage[i+2]=240;
      coverage[i+3]=valid&&!d.mask_suspended?Math.round(frame.rgba[i+3]*.55):0;
    }
  }
  return {base,coverage};
}
