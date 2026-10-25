// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {imageDigest, type Review} from './model';
import type {HairUnificationPort} from './nativePort';

type Side = 'before' | 'after' | 'support';
const SIDES: Side[] = ['before', 'after', 'support'];
/** Only decoded, hash-matched, fully visible clean photographs can authorize the exact ACK. */
export function ReviewImages({review, port}: {review: Review; port: HairUnificationPort}) {
  const nodes = useRef<Partial<Record<Side, HTMLImageElement>>>({}), live = useRef(review.preview_id);
  const mounted = useRef(false);
  live.current = review.preview_id;
  const [loaded, setLoaded] = useState<string[]>([]), [visible, setVisible] = useState(false);
  useLayoutEffect(() => {
    mounted.current = true;
    setLoaded([]); setVisible(false); port.imagesReady(review.preview_id, false);
    return () => {mounted.current = false; port.imagesReady(review.preview_id, false);};
  }, [port, review.preview_id]);
  useEffect(() => {
    const entries = new Map<Element, boolean>();
    const update = () => setVisible(!document.hidden && document.hasFocus()
      && SIDES.every(side => !!nodes.current[side] && entries.get(nodes.current[side]!) === true));
    const observer = new IntersectionObserver(changes => {
      changes.forEach(entry => entries.set(entry.target, entry.isIntersecting && entry.intersectionRatio >= .99)); update();
    }, {threshold: [0, .99, 1]});
    SIDES.forEach(side => {const node = nodes.current[side]; if (node) observer.observe(node);});
    window.addEventListener('focus', update); window.addEventListener('blur', update); document.addEventListener('visibilitychange', update);
    return () => {observer.disconnect(); window.removeEventListener('focus', update); window.removeEventListener('blur', update);
      document.removeEventListener('visibilitychange', update);};
  }, [review.preview_id]);
  useEffect(() => {
    const ready = visible && SIDES.every(side => loaded.includes(`${review.preview_id}:${side}`));
    if (!ready) {port.imagesReady(review.preview_id, false); return;}
    let active = true, second = 0;
    const first = requestAnimationFrame(() => {second = requestAnimationFrame(() => {
      if (active && !document.hidden && document.hasFocus()) port.imagesReady(review.preview_id, true);
    });});
    return () => {active = false; cancelAnimationFrame(first); cancelAnimationFrame(second);};
  }, [port, review.preview_id, loaded, visible]);
  function fail(message: string) {
    if (!mounted.current || live.current !== review.preview_id || port.snapshot().workspace?.review?.preview_id !== review.preview_id) return;
    port.imagesReady(review.preview_id, false); port.failed(message);
  }
  async function decoded(node: HTMLImageElement, side: Side) {
    const preview = review.preview_id, url = review[`${side}_png`];
    if (node.currentSrc !== url || node.naturalWidth !== review[`${side}_width`] || node.naturalHeight !== review[`${side}_height`]) {
      fail('审核图片解码尺寸不符，不能确认显示或应用。'); return;
    }
    try {
      const hash = await imageDigest(url);
      if (!mounted.current || live.current !== preview || port.snapshot().workspace?.review?.preview_id !== preview) return;
      if (hash !== review[`${side}_sha256`]) {fail('审核图片字节与原候选摘要不一致，不能应用。'); return;}
      setLoaded(values => values.includes(`${preview}:${side}`) ? values : [...values, `${preview}:${side}`]);
    } catch {fail('审核图片字节核验失败，不能应用；原样本草稿仍保留。');}
  }
  return <section aria-label="本次真实完整前后照片与样本范围审核" className="hair-unification-review-images">
    <div className="hair-unification-pictures">
      {SIDES.map(side => <figure key={`${review.preview_id}:${side}`}>
        <figcaption>{side === 'before' ? '本次调整前 · 完整成片' : side === 'after' ? '候选效果 · 尚未应用' : '本人头发与参考样本 · 非效果图'}</figcaption>
        <img ref={node => {if (node) nodes.current[side] = node; else delete nodes.current[side];}}
          src={review[`${side}_png`]} draggable={false}
          alt={side === 'before' ? '当前照片在本次发色统一前的干净完整画面' : side === 'after'
            ? '同一照片发色统一候选的干净完整画面' : '源图上真实已审核头发及手绘发根发尾参考样本的诊断范围'}
          onLoad={event => {void decoded(event.currentTarget, side);}} onError={() => fail('完整审核图片未加载成功，不能用占位图确认效果。')}/>
      </figure>)}
    </div>
    <p role="status">{visible ? '完整审核图已进入视图。确认还需三张图片解码和原始 PNG 字节摘要全部匹配。'
      : '请让以上三张完整图片同时进入视图；裁切、未加载或隐藏的图不能作为显示确认。'}</p>
    <p>图片来自当前照片实际渲染后缩小的审核结果，不是原尺寸画质验收。范围图只解释采样与作用范围，不能代替干净前后对照。</p>
  </section>;
}
