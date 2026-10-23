import {useEffect, useRef, useState} from 'react';
import type {CropReview} from './model';

/** The engine supplied this real canonical final crop; CSS does not simulate geometry. */
export function CropTransferReview({value, reviewKey, onReady}: {
  value: CropReview; reviewKey: string; onReady: (key: string, ready: boolean) => void;
}) {
  const notify = useRef(onReady); notify.current = onReady;
  const [image, setImage] = useState<'loading' | 'ready' | 'error'>('loading');
  const [verified, setVerified] = useState<'loading' | 'ready' | 'error'>('loading');
  useEffect(() => {
    let live = true;
    setVerified('loading');
    void (async () => {
      try {
        const bytes = Uint8Array.from(atob(value.preview.base64), char => char.charCodeAt(0));
        const digest = await crypto.subtle.digest('SHA-256', bytes);
        const actual = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('');
        if (live) setVerified(actual === value.preview.sha256 ? 'ready' : 'error');
      } catch {if (live) setVerified('error');}
    })();
    return () => {live = false;};
  }, [reviewKey, value.preview.base64, value.preview.sha256]);
  useEffect(() => {notify.current(reviewKey, image === 'ready' && verified === 'ready');}, [reviewKey, image, verified]);
  const failed = image === 'error' || verified === 'error';
  return <section aria-label="本目标完整编辑后的裁剪预检" style={{flexBasis: '100%'}}>
    <strong>本目标最终裁剪预览，尚未应用</strong>
    <p>源图 {value.source_size.join(' × ')} 像素 → 输出 {value.output_size.join(' × ')} 像素。旋转 {value.crop.rotation_degrees}°。</p>
    <p>归一化裁剪框：{value.crop.rect_normalized.map(n => n.toFixed(5)).join('，')}。</p>
    <img src={`data:image/png;base64,${value.preview.base64}`} width={value.preview.width} height={value.preview.height}
      style={{maxWidth: '100%', height: 'auto'}} alt="该目标完整编辑链经实际裁剪及旋转后的显示缩略图，不是源照片或 CSS 模拟"
      onLoad={event => setImage(event.currentTarget.naturalWidth === value.preview.width && event.currentTarget.naturalHeight === value.preview.height ? 'ready' : 'error')}
      onError={() => setImage('error')}/>
    {(image !== 'ready' || verified !== 'ready') && <p role="status">{failed ? '预览未通过像素尺寸或内容校验，不能提交；请重新预检。' : '正在验证本目标的实际裁剪预览…'}</p>}
    <small>仅用于审核构图，不参与最终出片，也不代替全分辨率质量验收。目标源图或配方改变后须重新预检。</small>
  </section>;
}
