/** Package creation is explicit; previews are not claims of verified runtime acceptance. */
import {useProjectPackage,type Dependency} from './useProjectPackage';
function DependencyList({rows}:{rows:Dependency[]}){
  return <ul>{rows.map((row,index)=><li key={row.id??index}>
    <b>{row.type??row.kind??'依赖'}</b> · {row.path??row.source_path??row.id??'内嵌重放资产'}
    <br/>{row.included||row.include||row.status==='mandatory-in-project'||row.status==='bundled'?'包含':'不包含 / 保留依赖声明'} · {row.status??''}{row.reason&&` · ${row.reason}`}
    <br/>许可：{row.licence??row.license??'未声明，不推定可转移'} · 来源：{typeof row.provenance==='string'?row.provenance:JSON.stringify(row.provenance??'工程记录')}
    {(row.sha256||row.sha256_expected)&&<small style={{display:'block',overflowWrap:'anywhere'}}>SHA-256：{row.sha256??row.sha256_expected}</small>}
  </li>)}</ul>;
}
export function ProjectPackagePanel({projectOpen,onChanged}:{projectOpen:boolean;onChanged:()=>void}){
  const flow=useProjectPackage(onChanged),blocked=flow.busy||!!flow.pending;
  return <section className="projCard" aria-label="便携工程包">
    <h3>便携工程与依赖恢复</h3>
    <p>工程 JSON、历史、稳定文档身份和内嵌重放资产保留。外部原件由你选择；模型权重不会自动打包或下载。</p>
    <label><input type="checkbox" checked={flow.originals} disabled={blocked} onChange={e=>flow.setOriginals(e.target.checked)}/>包含照片原片（只读复制）</label>
    <label><input type="checkbox" checked={flow.references} disabled={blocked} onChange={e=>flow.setReferences(e.target.checked)}/>包含外部参考原件（内嵌重放资产始终保留）</label>
    <div><button disabled={blocked||!projectOpen} onClick={()=>void flow.previewCreate()}>预览打包清单</button>
      <button disabled={blocked} onClick={()=>void flow.previewRestore()}>选择工程包并预检</button></div>
    {flow.preview&&<div>
      <h4>{flow.mode==='create'?'待打包清单':'待恢复清单'}</h4>
      {flow.preview.bytes!==undefined&&<p>计划内容大小：{flow.preview.bytes.toLocaleString()} 字节</p>}
      <DependencyList rows={flow.preview.dependencies??[]}/>
      {!!flow.preview.embedded_assets?.length&&<details><summary>必须保留的内嵌重放资产（{flow.preview.embedded_assets.length}）</summary><DependencyList rows={flow.preview.embedded_assets}/></details>}
      {flow.preview.model_dependencies!==undefined&&<details><summary>模型依赖声明（不包含权重）</summary><p>{JSON.stringify(flow.preview.model_dependencies)}</p></details>}
      {(flow.preview.warnings??[]).map((warning,index)=><p key={index}>{warning}</p>)}
      <p>未包含的来源不会被悄悄删除。请保留原始文件；恢复后原片可用下方“找回缺失原图”修复，参考依赖请在对应工具中重新选择（例如天空替换的素材选择器）。</p>
      <button disabled={blocked} onClick={()=>void flow.commit()}>{flow.mode==='create'?'选择目标并确认创建':'选择恢复位置并确认恢复'}</button>
    </div>}
    {flow.result&&<p role="status">状态：{flow.result.status}{flow.result.progress!==undefined&&` · ${typeof flow.result.progress==='string'?flow.result.progress:JSON.stringify(flow.result.progress)}`}</p>}
    {flow.pending&&<div><p>操作编号：{flow.pending}。关闭面板或刷新后仍查询原操作，不自动重新创建。</p>
      <button disabled={flow.busy} onClick={()=>void flow.readback()}>查询原操作结果</button>
      <button disabled={flow.busy} onClick={()=>void flow.cancel()}>请求安全取消</button></div>}
    {flow.canResetPreview&&<button disabled={flow.busy} onClick={flow.resetPreview}>结束未知的只读预检，重新选择工程包</button>}
    {flow.unknown&&<p role="alert">结果尚未确认。取消失败也不代表已经停止；请查询原操作并核对目标，不要重复提交。</p>}
    {flow.result?.status==='completed'&&<div>
      <p>已完成：{flow.result.destination??flow.result.project_path}</p>
      {flow.result.manifest_sha256&&<p style={{overflowWrap:'anywhere'}}>完整清单 SHA-256：{flow.result.manifest_sha256}</p>}
      {!!flow.result.missing_dependencies?.length&&<><h4>仍需修复的依赖</h4><DependencyList rows={flow.result.missing_dependencies}/></>}
      {flow.result.project_path&&<button disabled={blocked} onClick={()=>void flow.openRestored()}>打开恢复后的工程（不丢弃未保存修改）</button>}
    </div>}
    {flow.error&&<p role="alert">{flow.error}</p>}
  </section>;
}
