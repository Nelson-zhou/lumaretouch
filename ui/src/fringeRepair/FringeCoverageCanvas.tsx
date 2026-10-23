import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {MAX_POINTS, newStroke, reviewImageKey, type BrushSettings, type FringeStroke, type Point} from './model';
import type {FringeRepairOwner} from './useFringeRepairWorkflow';

interface Gesture {pointer: number; key: string; stroke: FringeStroke; rect: DOMRect; started: number}
export function FringeCoverageCanvas({owner, settings, zoom, showCoverage}: {
  owner: FringeRepairOwner; settings: BrushSettings; zoom: number; showCoverage: boolean;
}) {
  const {state, workflow} = owner, image = state.review?.image;
  const beforeViewport = useRef<HTMLDivElement>(null), afterViewport = useRef<HTMLDivElement>(null);
  const beforeImage = useRef<HTMLImageElement>(null), afterImage = useRef<HTMLImageElement>(null);
  const gesture = useRef<Gesture | null>(null), syncing = useRef(false);
  const [path, setPath] = useState<FringeStroke | null>(null), [cursor, setCursor] = useState<Point | null>(null);
  const [fitWidth, setFitWidth] = useState(1), [loaded, setLoaded] = useState<string[]>([]), [visible, setVisible] = useState(false);
  // A pending request never lends its identity to pixels from the last review.
  const key = state.reviewPreviewId ?? '';
  function cancel(message: string) {gesture.current = null; setPath(null); workflow.cancelStroke(message);}
  useLayoutEffect(() => {
    gesture.current = null; setPath(null); setCursor(null); setLoaded([]);
  }, [key]);
  useEffect(() => {
    const blur = () => {if (gesture.current) cancel('窗口失去焦点，本笔未写入范围草稿。');};
    const visibility = () => {if (document.hidden) blur();};
    window.addEventListener('blur', blur); document.addEventListener('visibilitychange', visibility);
    return () => {window.removeEventListener('blur', blur); document.removeEventListener('visibilitychange', visibility);};
  }, [workflow]);
  useLayoutEffect(() => {
    if (!state.strokeActive) {gesture.current = null; setPath(null);}
  }, [state.strokeActive]);
  useLayoutEffect(() => {
    const viewport = beforeViewport.current, peer = afterViewport.current;
    if (!viewport || !peer || !image) return;
    const measure = () => setFitWidth(Math.max(1, Math.min(viewport.clientWidth, peer.clientWidth,
      viewport.clientHeight * image.width / image.height, peer.clientHeight * image.width / image.height) - 2));
    const observer = new ResizeObserver(measure); observer.observe(viewport); observer.observe(peer); measure();
    return () => observer.disconnect();
  }, [image?.width, image?.height, key]);
  useLayoutEffect(() => {
    const before = beforeImage.current, after = afterImage.current;
    setVisible(false); if (!before || !after) return;
    const intersections = new Map<Element, boolean>();
    const update = () => setVisible(intersections.get(before) === true && intersections.get(after) === true &&
      !document.hidden && document.hasFocus());
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => intersections.set(entry.target, entry.isIntersecting && entry.intersectionRatio >= .99)); update();
    }, {threshold: [0, .99, 1]});
    observer.observe(before); observer.observe(after);
    window.addEventListener('focus', update); window.addEventListener('blur', update); document.addEventListener('visibilitychange', update);
    return () => {observer.disconnect(); window.removeEventListener('focus', update); window.removeEventListener('blur', update);
      document.removeEventListener('visibilitychange', update);};
  }, [key, image?.before, image?.after]);
  useLayoutEffect(() => {
    if (!image || !key || state.phase !== 'ready' || state.dirty || state.strokeActive || !visible || showCoverage ||
        !['before', 'after', 'coverage'].every(side => loaded.includes(`${key}:${side}`))) return;
    let active = true, second = 0;
    const first = requestAnimationFrame(() => {second = requestAnimationFrame(() => {
      if (active && !document.hidden && document.hasFocus() && beforeImage.current?.complete && afterImage.current?.complete)
        void workflow.presented(key);
    });});
    return () => {active = false; cancelAnimationFrame(first); cancelAnimationFrame(second);};
  }, [key, image, state.phase, state.dirty, state.strokeActive, visible, loaded, showCoverage, workflow]);
  if (!image) return <div className="fringeWaiting" role="status">正在准备真实照片前后对照与计算范围…</div>;
  const width = fitWidth * zoom / 100, height = width * image.height / image.width;
  const position = (event: ReactPointerEvent<HTMLDivElement>): Point | null => {
    const rect = event.currentTarget.getBoundingClientRect(), x = (event.clientX - rect.left) / rect.width, y = (event.clientY - rect.top) / rect.height;
    return rect.width > 0 && rect.height > 0 && x >= 0 && x <= 1 && y >= 0 && y <= 1 ? [x, y] : null;
  };
  const stop = (event: ReactPointerEvent<HTMLDivElement>) => {event.preventDefault(); event.stopPropagation();};
  function append(event: ReactPointerEvent<HTMLDivElement>): boolean {
    const down = gesture.current; if (!down || down.pointer !== event.pointerId || down.key !== key) return false;
    const point = position(event), rect = event.currentTarget.getBoundingClientRect();
    if (!point || (['left', 'top', 'width', 'height'] as const).some(field => Math.abs(rect[field] - down.rect[field]) > .5)) {
      cancel('画布位置、缩放或笔迹边界已变化，本笔已取消。'); return false;
    }
    if (Date.now() - down.started > 60000 || down.stroke.points.length >= MAX_POINTS) {
      cancel('本笔超过路径或时长预算，请分成更短笔划。'); return false;
    }
    const last = down.stroke.points.at(-1)!;
    if (Math.hypot((point[0] - last[0]) * rect.width, (point[1] - last[1]) * rect.height) >= 1) {
      down.stroke = {...down.stroke, points: [...down.stroke.points, point]}; setPath(down.stroke);
    }
    return true;
  }
  const imageLoaded = (element: HTMLImageElement, side: 'before' | 'after' | 'coverage') => {
    if (workflow.snapshot().reviewPreviewId !== key || element.currentSrc !== image[side]) return;
    if (element.naturalWidth !== image.width || element.naturalHeight !== image.height) {
      workflow.failed('祛边审核图片尺寸不符，不能应用。', key); return;
    }
    setLoaded(previous => previous.includes(`${key}:${side}`) ? previous : [...previous, `${key}:${side}`]);
  };
  const imageError = () => workflow.failed('祛边审核图片未完整显示，不能应用。', key);
  const vectors = state.dirty ? state.draft?.strokes ?? [] : [];
  const drawVector = (stroke: FringeStroke) => {
    const points = stroke.points.map(point => `${point[0] * image.width},${point[1] * image.height}`).join(' ');
    const color = stroke.mode === 'add' ? '#53d6b4' : '#fc79ac', radius = stroke.radius * Math.min(image.width, image.height);
    return stroke.points.length === 1
      ? <circle key={stroke.id} cx={stroke.points[0][0] * image.width} cy={stroke.points[0][1] * image.height}
        r={radius} fill={color} opacity={.18 + stroke.opacity * .35}/>
      : <polyline key={stroke.id} points={points} stroke={color} strokeWidth={radius * 2}
        strokeLinecap="round" strokeLinejoin="round" fill="none" opacity={.18 + stroke.opacity * .35}/>;
  };
  const scroll = (source: HTMLDivElement, target: HTMLDivElement | null) => {
    if (syncing.current || !target) return;
    syncing.current = true; target.scrollLeft = source.scrollLeft; target.scrollTop = source.scrollTop; syncing.current = false;
  };
  return <>
    <div className="fringePictures">
      <figure><figcaption>本次调整前 · 在这里添加 / 减去范围</figcaption>
        <div ref={beforeViewport} className="fringeViewport" onScroll={event => scroll(event.currentTarget, afterViewport.current)}>
          <div className="fringeDrawing" style={{width, height}} role="application" aria-label="祛边范围画布，照片最终构图坐标"
            onPointerDown={event => {
              stop(event); if (event.button !== 0 || gesture.current) return;
              const point = position(event); if (!point || !workflow.beginStroke()) return;
              const stroke = newStroke(point, settings);
              gesture.current = {pointer: event.pointerId, key, stroke, rect: event.currentTarget.getBoundingClientRect(), started: Date.now()};
              setPath(stroke); setCursor(point); event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={event => {stop(event); setCursor(position(event)); if (gesture.current) append(event);}}
            onPointerUp={event => {
              stop(event); if (gesture.current?.pointer !== event.pointerId) return;
              const valid = append(event), down = gesture.current; gesture.current = null; setPath(null);
              if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
              if (valid && down && down.key === key) workflow.endStroke(down.stroke);
            }}
            onPointerCancel={event => {stop(event); if (gesture.current?.pointer === event.pointerId) cancel('指针手势取消，本笔未保存。');}}
            onLostPointerCapture={event => {if (gesture.current?.pointer === event.pointerId) cancel('指针控制中断，本笔未保存。');}}
            onPointerLeave={() => {if (!gesture.current) setCursor(null);}}>
            <img key={reviewImageKey(key, 'before')} ref={beforeImage} src={image.before} alt="本次祛边调整前的真实照片" draggable={false}
              onLoad={event => imageLoaded(event.currentTarget, 'before')} onError={imageError}/>
            <img key={reviewImageKey(key, 'coverage')} src={image.coverage} alt="引擎计算的当前祛边范围" draggable={false}
              className={showCoverage && !state.dirty ? 'fringeComputedCoverage' : 'fringeConcealed'}
              onLoad={event => imageLoaded(event.currentTarget, 'coverage')} onError={imageError}/>
            <svg viewBox={`0 0 ${image.width} ${image.height}`} aria-hidden="true">
              {showCoverage && vectors.map(drawVector)}{path && drawVector(path)}
              {cursor && <circle cx={cursor[0] * image.width} cy={cursor[1] * image.height}
                r={settings.size / 200 * Math.min(image.width, image.height)} className="fringeCursor"/>}
            </svg>
          </div>
        </div>
      </figure>
      <figure><figcaption>{state.phase === 'loading' ? '上次计算结果 · 正在更新' : state.dirty ? '上次计算结果 · 草稿尚未更新' : '本次祛边后 · 尚未应用'}</figcaption>
        <div ref={afterViewport} className="fringeViewport" onScroll={event => scroll(event.currentTarget, beforeViewport.current)}>
          <div className="fringeDrawing fringeReadOnly" style={{width, height}}>
            <img key={reviewImageKey(key, 'after')} ref={afterImage} src={image.after} alt="真实祛边候选效果，只读" draggable={false}
              onLoad={event => imageLoaded(event.currentTarget, 'after')} onError={imageError}/>
          </div>
        </div>
      </figure>
    </div>
    <p className="fringeViewNotice" role="status">{state.dirty
      ? '待更新笔迹是范围指令，不是修复结果。绿色添加，粉色减去；更新后以引擎范围图为准。'
      : showCoverage ? '关闭范围叠加并回到适应视图，检查干净的前后照片后才能确认。'
      : visible ? '显示的是全尺寸计算后缩小的 sRGB 8 位审核图，不是 100% 原尺寸细节。'
      : '请回到适应视图，让前后两张照片完整显示；放大缩小图不能代替原尺寸验收。'}</p>
  </>;
}
