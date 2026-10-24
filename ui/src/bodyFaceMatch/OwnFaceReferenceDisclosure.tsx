// SPDX-License-Identifier: GPL-3.0-or-later
import type {SourceImage} from '../legShape/sourcePreview';
import type {OwnFaceReferenceSupport, ReferenceSourceStage} from './reference';

/** Read-only actual measured reference; deliberately no donor selector. */
export function OwnFaceReferenceDisclosure({image, support, stage, busy, loaded, accepted, onLoaded, onAccepted}: {
  image: SourceImage | null; support: OwnFaceReferenceSupport | undefined; stage: ReferenceSourceStage | undefined;
  busy: boolean; loaded: boolean; accepted: boolean; onLoaded: (ready: boolean) => void; onAccepted: (accepted: boolean) => void;
}) {
  if (!image || !support || !stage) return <p role="alert">缺少本人的实测来源脸部参考，不能生成或确认匹配效果。</p>;
  return <section aria-label="本人的实测来源脸部参考">
    <p>唯一参考是当前人物在肖像效果之前的有效来源阶段中的实测脸部皮肤。下图洋红色显示实际参考范围，不是任意脸框、其他人物、身体范围或后续修饰后的脸。</p>
    <figure style={{margin: '8px 0'}}>
      <img src={image.url} alt="实际采样来源阶段中的本人脸部参考范围（洋红色）" style={{width: '100%', height: 'auto'}}
        onLoad={event => onLoaded(event.currentTarget.naturalWidth === image.displayWidth && event.currentTarget.naturalHeight === image.displayHeight)}
        onError={() => onLoaded(false)}/>
      <figcaption>真实参考叠图，不是完成效果。{stage === 'verified-repair-base' ? '参考含已验证并冻结的现有修复。' : '参考来自当前不可变来源。'}有效采样 {support.reference_samples} 个；实际支撑像素 {support.support_pixels} 个；保护其他人脸 {support.protected_face_boxes} 个。</figcaption>
    </figure>
    <p className="muted">来源阶段审核网格 {image.decodedWidth} × {image.decodedHeight}，显示尺寸 {image.displayWidth} × {image.displayHeight}；脸部观察采样网格 {support.face_skin_observation.producer_width} × {support.face_skin_observation.producer_height}。这是审核代理图，不是 100% 或全分辨率测量图；全来源数值参考会另行重算，效果以本次真实完整候选的前后对比为准。此图不证明分割或照片质量已验收。只匹配色度，不匹配亮度，也不复制脸部 RGB。</p>
    <label><input type="checkbox" checked={accepted} disabled={busy || !loaded} onChange={event => onAccepted(event.target.checked)}/>
      我已查看实际参考范围，确认它只属于当前人物的来源脸部，并接受它不是后续修饰后的脸。</label>
    {!loaded && <p role="status">参考图尚未按回执尺寸加载成功，暂不能授权候选。</p>}
  </section>;
}
