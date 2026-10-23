import type {MouseEvent,ReactNode} from 'react';
import type {SessionDoc} from '../native';
import {ratingOf,flagOf,FLAG_COLOR,type LibraryResult} from './model';
interface Props {docs:SessionDoc[];total:number;sel:Set<string>;thumbs:Record<string,string>;
 controls:ReactNode;facts?:LibraryResult['facts'];onPickDoc(index:number):void;
 onCellClick(e:MouseEvent,index:number,path:string):void;openAndImport():Promise<unknown>;
 onRetouch():void;setRating(d:SessionDoc,n:number):Promise<void>;cycleFlag(d:SessionDoc):Promise<void>;cyclePick(d:SessionDoc):Promise<void>;}
const isRawDoc=(d:SessionDoc)=>/\.(dng|cr2|cr3|nef|arw|raf|orf|rw2|pef|srw|3fr|x3f|rwl|iiq)$/i.test(d.path)||!!d.thumb?.preview;
export function FilmstripGallery({docs,total,sel,thumbs,controls,facts,onPickDoc,onCellClick,openAndImport,onRetouch,setRating,cycleFlag,cyclePick}:Props){return (
              <section className="gallery">
                {controls}
                <div className="strip">
                  {docs.map((d) => {
                    const rate = ratingOf(d);
                    const flag = d.label ?? "";
                    return (
                      <div key={d.document_id}
                           className={"cell" + (d.loaded ? " on" : "")
                             + (sel.has(d.document_id) ? " sel" : "") + (d.trashed ? " trashed" : "")}
                           role="button" tabIndex={0}
                           title={`${d.name}${d.copy_number ? ` · 副本 ${d.copy_number}` : " · 原图"}`}
                           onContextMenu={e=>{e.preventDefault();window.dispatchEvent(new CustomEvent("lrt-virtual-copy-context",{detail:{documentId:d.document_id}}));}}
                           onClick={(e) => onCellClick(e, d.index, d.document_id)}
                           onKeyDown={(e) => {
                             if (e.key === "Enter") onPickDoc(d.index);
                           }}>
                        {d.thumb && thumbs[d.path] ? (
                          <img alt={d.name} width={d.thumb.w} height={d.thumb.h}
                               src={`data:image/jpeg;base64,${thumbs[d.path]}`} />
                        ) : (
                          <span className="ph">…</span>
                        )}
                        <span className="cellFlag"
                              style={flag && FLAG_COLOR[flag] ? { background: FLAG_COLOR[flag] } : undefined}
                              title={flag ? `色标：${flag}（点击更换）` : "色标（点击设置）"}
                              onClick={(e) => { e.stopPropagation(); void cycleFlag(d); }} />
                        <button title="选取 / 排除 / 移除旗标" onClick={(e)=>{e.stopPropagation();void cyclePick(d);}}>{flagOf(d)==='accepted'?'⚑':flagOf(d)==='rejected'?'×':'⚐'}</button>
                        <span className="cellStars" onClick={(e) => e.stopPropagation()}>
                          {[1, 2, 3, 4, 5].map((n) => (
                            <button key={n} className={n <= rate ? "on" : ""}
                                    title={`${n} 星（再点一次清零）`}
                                    onClick={() => void setRating(d, n)}>★</button>
                          ))}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </section>
);}
export function LibraryGallery({docs,total,sel,thumbs,controls,facts,onPickDoc,onCellClick,openAndImport,onRetouch,setRating,cycleFlag,cyclePick}:Props){return (
          <section className="library">
            <div className="libHead">
              <div>
                <h2>图库</h2>
                <span>{total} 张照片{sel.size ? ` · 已选 ${sel.size}` : ""}</span>
              </div>
              <button className="chip" onClick={() => void openAndImport()}>
                打开照片
              </button>
            </div>
            {controls}
            {docs.length > 0 ? (
              <div className="libGrid">
                {docs.map((d) => (
                  <button key={d.document_id}
                          onContextMenu={e=>{e.preventDefault();window.dispatchEvent(new CustomEvent("lrt-virtual-copy-context",{detail:{documentId:d.document_id}}));}}
                          className={"libCard" + (d.loaded ? " cur" : "") + (sel.has(d.document_id) ? " sel" : "")} aria-pressed={sel.has(d.document_id)}
                          onClick={(e) => { onCellClick(e, d.index, d.document_id); if (!e.shiftKey && !e.metaKey && !e.ctrlKey) onRetouch(); }}>
                    <span className="libThumb">
                      {d.thumb && thumbs[d.path]
                        ? <img alt={d.name} src={`data:image/jpeg;base64,${thumbs[d.path]}`} />
                        : <span className="ph">…</span>}
                    </span>
                    <span className="libMeta">
                      <span className="libName">{d.name}{d.copy_number ? ` · 副本 ${d.copy_number}` : " · 原图"}</span>
                      <span className="libTags">
                        {isRawDoc(d) && <em className="tag raw">RAW</em>}
                        {!!facts?.[d.document_id]?.edited && <em className="tag edited">已编辑</em>}
                        {!!facts?.[d.document_id]?.exported && <em className="tag done">已导出</em>}
                      </span>
                      <span className="libStars">
                        {"★".repeat(ratingOf(d))}{"☆".repeat(5 - ratingOf(d))}
                      </span>
                    </span>
                    {d.label && FLAG_COLOR[d.label] && (
                      <i className="libFlag" style={{ background: FLAG_COLOR[d.label] }} />
                    )}
                  </button>
                ))}
              </div>
            ) : (
              total > 0 ? <div className="libEmpty" role="status">没有符合当前条件的照片，可清空筛选重新查看。</div> : <div className="libEmpty" role="button" tabIndex={0}
                   onClick={() => void openAndImport()}
                   onKeyDown={(e) => { if (e.key === "Enter") void openAndImport(); }}>
                <b>打开照片，开始第一批精修</b>
                <span>支持 JPEG / PNG / TIFF / WebP / DNG；原片只读，编辑写工程记录</span>
              </div>
            )}
          </section>
);}
