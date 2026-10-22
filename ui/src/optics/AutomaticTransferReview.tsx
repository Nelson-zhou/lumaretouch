/** Read-only target evidence shared by preset and batch frozen reviews. */
import type {OpticalTargetReview} from './transferReviewModel';
export function AutomaticTransferReview({report}:{report:OpticalTargetReview}){
  if(!report.success)return <p role="alert">此目标未通过镜头/透视预检：{report.error??'没有可信结果，未应用'}</p>;
  const image=report.comparison;
  const safe=image&&Number.isInteger(image.width)&&Number.isInteger(image.height)&&image.width>0&&image.height>0&&image.width<=320&&image.height<=320&&
    image.domain==='post-manual-liquify-pre-crop-normalized'&&[image.before,image.after].every(s=>typeof s==='string'&&s.startsWith('data:image/png;base64,')&&s.length<=1024*1024);
  return <section aria-label="目标镜头透视重新计算预检">
    <strong>本目标重新匹配与解算，尚未应用</strong>
    <p>{report.lens?`${report.lens.camera_model} / ${report.lens.lens_model}，实际标定：${report.lens.flags.join('、')}`:'此请求关闭自动镜头配置'}</p>
    {report.analysis?<p>依据 {report.analysis.lines} 条线，置信度 {Math.round(report.analysis.confidence*100)}%，残差 {report.analysis.residual_degrees.toFixed(2)}°。{report.analysis.message}</p>:<p>此请求不执行自动透视；仅应用其镜头与手动参数。</p>}
    <p>自动收边倍率 {((report.crop_zoom??1)*100).toFixed(1)}%。源图或编辑版本改变后必须重新预检。</p>
    {safe&&image&&<div style={{display:'flex',flexWrap:'wrap',gap:12}}>
      <figure><figcaption>本次候选上游效果，镜头/透视之前</figcaption><img src={image.before} width={image.width} height={image.height} alt="该目标完整编辑画布的只读分析输入缩略图"/></figure>
      <figure><figcaption>本目标新镜头/透视结果，最终裁剪之前</figcaption><img src={image.after} width={image.width} height={image.height} alt="目标自身重新解算后的只读结果缩略图，不是源照片矩阵复制"/></figure>
    </div>}
    <small>{report.note} 比较图仅用于预检显示，不用于最终出片；批量仅前两张附比较图，其余目标显示独立解算报告。</small>
  </section>;
}
