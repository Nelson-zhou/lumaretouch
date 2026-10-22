import {useEffect,useRef} from 'react';
/** Candidate PNG is opaque grayscale L, not an alpha PNG. Its intensity is coverage. */
export function CandidateMask({src,onPaint,onError}:{src:string;onPaint:()=>void;onError:(error:string)=>void}){
  const canvas=useRef<HTMLCanvasElement>(null),callbacks=useRef({onPaint,onError});callbacks.current={onPaint,onError};
  useEffect(()=>{
    let alive=true;const image=new Image();
    image.onload=()=>{if(!alive||!canvas.current)return;
      try{if(!image.naturalWidth||!image.naturalHeight||Math.max(image.naturalWidth,image.naturalHeight)>1024)throw Error('候选显示尺寸无效');
        const node=canvas.current;node.width=image.naturalWidth;node.height=image.naturalHeight;
        const ctx=node.getContext('2d');if(!ctx)throw Error('不能创建候选蒙版画布');
        ctx.drawImage(image,0,0);const pixels=ctx.getImageData(0,0,node.width,node.height);
        for(let i=0;i<pixels.data.length;i+=4){const coverage=pixels.data[i];pixels.data[i]=38;pixels.data[i+1]=230;pixels.data[i+2]=203;pixels.data[i+3]=Math.round(coverage*.55);}
        ctx.putImageData(pixels,0,0);callbacks.current.onPaint();
      }catch(error){callbacks.current.onError(String(error));}
    };
    image.onerror=()=>{if(alive)callbacks.current.onError('候选蒙版显示失败，不能应用。');};
    image.src=src;return()=>{alive=false;image.onload=null;image.onerror=null;};
  },[src]);
  return <canvas className="promptedCandidate" ref={canvas} role="img" aria-label="选中候选的真实蒙版覆盖（青色）"/>;
}
