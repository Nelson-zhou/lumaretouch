import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {verifyXmpPreview, type XmpTransfer} from './model';

/** Only verified engine-rendered before/after images can unlock this review. */
export function XmpPixelReview({value, reviewKey, onReady}: {
  value: XmpTransfer; reviewKey: string; onReady: (key: string, ready: boolean) => void;
}) {
  const notify = useRef(onReady); notify.current = onReady;
  const [loaded, setLoaded] = useState({before: false, after: false});
  const [verified, setVerified] = useState<'loading' | 'ready' | 'error'>('loading');
  const [failed, setFailed] = useState(false), [acknowledged, setAcknowledged] = useState(false);
  useLayoutEffect(() => {
    notify.current(reviewKey, false);
    return () => {notify.current(reviewKey, false);};
  }, [reviewKey]);
  useEffect(() => {
    let live = true;
    // Parent keys this component by the frozen review. Do not reset a cached
    // image load event from a passive effect after that image already loaded.
    setVerified('loading'); setAcknowledged(false);
    void Promise.all([verifyXmpPreview(value.before), verifyXmpPreview(value.after)]).then(results => {
      if (live) setVerified(results.every(Boolean) ? 'ready' : 'error');
    }, () => {if (live) setVerified('error');});
    return () => {live = false;};
  }, [reviewKey, value.before, value.after]);
  const ready = loaded.before && loaded.after && verified === 'ready' && !failed;
  useEffect(() => {notify.current(reviewKey, ready && acknowledged);}, [reviewKey, ready, acknowledged]);
  return <section className="xmpPixelReview" aria-label="当前照片 XMP 本机适配前后审核">
    <strong>真实前后像素审核，尚未应用</strong>
    <p>这些图像来自当前照片完整编辑链的冻结渲染，不是 Adobe 结果、源照片替代图或 CSS 模拟。请检查色彩、亮度和曲线变化。</p>
    <div className="xmpComparison">{(['before', 'after'] as const).map(side => {
      const image = value[side], dimensions = side === 'before' ? value.before_output_size : value.after_output_size;
      return <figure key={side}><figcaption>{side === 'before' ? '适配前' : '本机适配后'} · 输出 {dimensions.join(' × ')} 像素</figcaption>
        <img src={`data:image/png;base64,${image.base64}`} width={image.width} height={image.height}
          alt={side === 'before' ? '当前照片在应用所选 XMP 参数前的实际渲染' : '当前照片应用所选本机适配参数后的实际候选渲染'}
          onLoad={event => {
            const ok = event.currentTarget.naturalWidth === image.width && event.currentTarget.naturalHeight === image.height;
            setLoaded(previous => ({...previous, [side]: ok})); if (!ok) setFailed(true);
          }} onError={() => {setFailed(true); setLoaded(previous => ({...previous, [side]: false}));}}/>
      </figure>;
    })}</div>
    {!ready && <p role="status">{failed || verified === 'error' ? '预览未通过图像加载、尺寸或 SHA-256 校验，不能应用。请重新预检。' : '正在加载并核验前后两张实际预览…'}</p>}
    <label><input type="checkbox" checked={acknowledged} disabled={!ready} onChange={event => setAcknowledged(event.target.checked)}/>
      我已查看本次前后图像，接受这些本机适配效果并继续应用。</label>
    <small>审核缩略图最长边 640 像素，不代替全分辨率质量验收。换图、修改配方或人物状态后，旧确认立即失效。</small>
  </section>;
}
