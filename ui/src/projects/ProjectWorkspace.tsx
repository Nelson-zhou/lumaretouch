/** Presentational project workspace; state and native I/O live in its domain hook. */
import type {ProjectState} from '../native';
import type {ProjectWorkflow} from './useProjectWorkflow';
export function ProjectWorkspace({workflow,project,projectSuffix,hasImage,onEnterRetouch}:{
  workflow:ProjectWorkflow;project:ProjectState|null;projectSuffix:string;hasImage:boolean;onEnterRetouch:()=>void;
}){
  return (
          <section className="projects">
            <div className="projHead">
              <div>
                <h2>项目管理</h2>
                <span>{project?.open
                  ? `${project.name ?? "未命名工程"} · ${project.docs ?? 0} 张 · ${project.dirty ? "有未保存修改" : "已保存"}`
                  : "尚未打开工程 · 新建或打开一个本地工程"}</span>
              </div>
              <button className="chip" disabled={!project?.open}
                onClick={() => { void workflow.save(); }}>
                保存工程
              </button>
            </div>
            <div className="projGrid">
              <div className="projCard">
                <h3>新建项目</h3>
                <label>项目名
                  <input value={workflow.name} onChange={(e) => workflow.setName(e.target.value)}
                    placeholder="例：2026 秋 婚礼跟拍" />
                </label>
                <button className="tb primary"
                  onClick={async () => { await workflow.createAndRemember(); }}>
                  选择目录并新建
                </button>
                <p>工程是单文件 JSON（{projectSuffix}），原片只读，编辑写工程记录。</p>
              </div>
              <div className="projCard">
                <h3>打开工程</h3>
                <button className="tb"
                  onClick={async () => { await workflow.openAndRemember(); }}>
                  浏览并打开工程文件
                </button>
                <button className="tb" disabled={!hasImage}
                  onClick={() => onEnterRetouch()}>进入精修</button>
                <p>换工程前请先保存：未保存的修改会被引擎拦住，不会静默丢失。</p>
              </div>
              <div className="projCard">
                <h3>最近工程</h3>
                {workflow.recent.length ? (
                  <ul className="recentList">
                    {workflow.recent.map((p) => (
                      <li key={p.path}>
                        <button title={p.path}
                          onClick={() => void workflow.openRecent(p.path, p.name)}>
                          <b>{p.name}</b><span>{p.path}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : <p>还没有打开过工程。</p>}
              </div>
            </div>
            {workflow.error && <div className="projErr">{workflow.error}</div>}
          </section>
  );
}
