export type ReferenceReview={version:1;method:string;recipe:{strength:number;log2_gains:number[]};fit:{consensus_count:number;consensus_fraction:number;residual_p90_stops:number};geometry:Record<string,unknown>;new_gamut_fraction:number;warnings:string[];target:{document_id:string;revision:string};proof:string};
export function validReferenceReview(v:unknown,id:string,revision:string){
  const r=v as ReferenceReview;
  return !!r&&r.version===1&&r.method==='matched-patch-linear-rgb-v1'&&r.target?.document_id===id&&r.target?.revision===revision&&
    /^[a-f0-9]{64}$/.test(r.proof)&&Array.isArray(r.recipe?.log2_gains)&&r.recipe.log2_gains.length===3&&r.recipe.log2_gains.every(n=>Number.isFinite(n)&&Math.abs(n)<=2)&&
    Number.isFinite(r.recipe.strength)&&r.recipe.strength>=0&&r.recipe.strength<=1&&Number.isFinite(r.new_gamut_fraction)&&r.new_gamut_fraction>=0&&
    Number.isFinite(r.fit?.residual_p90_stops)&&Number.isFinite(r.fit?.consensus_fraction)&&r.fit.consensus_fraction>=.65&&r.fit.consensus_fraction<=1&&Array.isArray(r.warnings)&&r.warnings.every(w=>typeof w==='string');
}
export function ReferenceColorReview({value:r}:{value:ReferenceReview}){
  return <details open><summary>对应区域参考校正 · 程度 {Math.round(r.recipe.strength*100)}%</summary>
    <p>线性 RGB 增益（档）：{r.recipe.log2_gains.map(x=>x.toFixed(3)).join(' / ')} · 有效对应 {r.fit.consensus_count} · 同意率 {Math.round(r.fit.consensus_fraction*100)}% · 残差 P90 {r.fit.residual_p90_stops.toFixed(3)} 档</p>
    <p>采样预计新增越界 {Math.round(r.new_gamut_fraction*10000)/100}%</p>
    <ul>{r.warnings.map(w=><li key={w}>{w}</li>)}</ul>
    <details><summary>来源支持与覆盖诊断</summary><pre>{JSON.stringify(r.geometry,null,2)}</pre></details>
  </details>;
}
