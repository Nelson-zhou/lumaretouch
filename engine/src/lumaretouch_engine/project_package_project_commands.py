"""Existing project create/open/save route, extracted without behavioral changes."""
import os
from . import project as PJ, tasks as T, white_balance_recipe as WB
from .project import ProjectError
from .shm import monotonic_ns
from .vram import LightOp, RepairOp

def handle(self, p: dict, emit, _current_writer):
    """项目：创建 / 打开 / 保存 / 标签 / 回收站。

    铁律沿用 cmd_session 与 cmd_exposure：参数先全量校验、跑靶与导出互斥、
    被拒不留半截状态、事件只有一个组装点。额外一条：`save` 在没有项目时**不隐式
    造工程**——“保存”在用户手里意思固定，默默在项目根建一个未命名工程是把决定
    权偷走（而他会以为已经存到自己选的地方）。
    """
    unknown = set(p) - self.PROJECT_KEYS
    if unknown:
        emit({"event": "error", "error": f"project 收到不认识的参数：{sorted(unknown)}"})
        return
    action = p.get("action")
    if action not in self.PROJECT_ACTIONS:
        emit({"event": "error", "error": f"未知 project action: {action}"
              f"（可用：{'/'.join(self.PROJECT_ACTIONS)}，名单在 ready 的 project_actions 里）"})
        return
    if action == 'create':
        # create saves an empty project but deliberately preserves live _docs.
        # It cannot launder these unknown edits via runtime.switch/new_workspace.
        from .final_canvas_flip_recovery import guard_create as guard_flip_create
        from .white_balance_auto_recovery import guard_create as guard_auto_create
        guard_flip_create(self)
        guard_auto_create(self)
    if action == "state":
        emit({"event": "project_state", **self._project_state()})
        return
    if self.bench is not None and self.bench.is_alive() and action in ("create", "open"):
        emit({"event": "error", "error": f"跑靶进行中，拒绝 project {action}：先 bench_stop"
              "（这两条会换底片条与会话，跑靶的读数就不再属于一张图）"})
        return
    if self._export is not None and self._export.is_alive():
        # 导出线程拿着的是“开始那一刻”的底片条快照：中途换工程会让账单对着
        # 一份已经不存在的集合说话（与 history 同一条守卫，但这里连 tag 也拦：
        # 批量报告里每一行都要能回到当时那一格）
        # 唯一的例外是“暂停中的批次 + save”：TASK-008 要的是“中断后重开仍然 paused”，
        # 而这一格只能在这里发生——用户暂停了一批没跑完的活儿，关应用前必然要存
        # 一次工程。一刀切拒绝等于把验收用例逼成“先继续跑完再存”，而那批已经没有
        # “未完成的批次”可供恢复了。worker 睡着的时候不写任何文件，存盘是安全的。
        if not (action == "save" and (self._export_task or {}).get("state") == T.PAUSED):
            emit({"event": "error", "error": f"导出进行中，拒绝 project {action}：等 export_done"
                  "（批次暂停到条目边界上时允许 save，那正是 TASK-008 要恢复的那一份）"})
            return
    if action == "create":
        name, directory = p.get("name"), p.get("directory")
        if not isinstance(name, str) or not name.strip():
            emit({"event": "error", "error": "project create 需要 name（非空字符串）"})
            return
        if not isinstance(directory, str) or not directory:
            emit({"event": "error", "error": "project create 需要 directory（可写目录）"})
            return
        try:
            path = PJ.project_path_for(directory, name)
        except (ProjectError, OSError) as e:
            emit({"event": "error", "error": f"项目建不出来：{e}"})
            return
        # 换工程参照不是丢工（create 不动 _docs，旧文件也不动），但得把“手上还拿着
        # 一份未存的活”说出去：UI 拿 replaced_dirty 才能把“切走了”与“切走了且没存”分开
        self._project_path_prev = self._project_path
        replaced_dirty = bool(self._project_dirty)
        prj = PJ.new_project(name, directory)
        try:
            info = PJ.save(prj, path)
        except (ProjectError, OSError) as e:
            emit({"event": "error", "error": f"项目写盘失败：{e}"})
            return
        self._project_source_notice = {}
        self._project, self._project_path = prj, info["path"]
        from .project_recovery_runtime import owner as recovery_owner
        recovery_owner(self, emit).switch()
        self._semantic_workspace_reset();self._document_versions().new_workspace()
        # 新建的是**空**工程，而底片条上那些活还在内存里：脏标记不能清成 False，
        # 否则徽章会说“已保存”而磁盘上一张图都没有——那比多亮一次危险得多。
        # （create 本身不丢工：它不动 _docs；真正会丢工的是 open，那一条另有守卫。）
        self._project_saved_ns = info["updated_ns"]
        self._project_disk_sha256 = info["sha256"]
        self._project_dirty = bool(self._docs)
        emit({"event": "project_created", "requested_directory": os.path.abspath(directory),
              "replaced": self._project_path_prev, "replaced_dirty": replaced_dirty,
              "bytes": info["bytes"], "sha256": info["sha256"],
              "write_ms": info["write_ms"], **self._project_state()})
        self.emit_session_state()
        return
    if action == "open":
        path = p.get("path")
        if not isinstance(path, str) or not path:
            emit({"event": "error", "error": "project open 需要 path（项目文件路径）"})
            return
        if not os.path.isfile(path):
            emit({"event": "error", "error": f"项目文件不存在：{path}"})
            return
        # 换工程先问一句：底片条会被整张表换掉，手上的活没存就是真的丢了。
        # 拿 force=true 显式跨过是另一回事——那才是用户自己说的“我不需要这一份”。
        # 默认直接换是“静默丢工”，本仓最贵的那一族坑就在这一格上。
        # P1-8：老 gate 只看 `self._project is not None and self._project_dirty`——
        # 那一条把"从没 project create/save 过但已经改了图"的未命名会话直接放过，
        # 换工程会静默丢工。`_project_dirty` 在 1223 行的真改判据里就已经被置 True
        # （不需要 _project 存在）；这里以 dirty 为唯一判据，未命名与已命名两条一起护。
        if self._project_dirty and not p.get("force"):
            _pname = (self._project or {}).get("name")
            _who = f"当前工程「{_pname}」" if _pname else "当前未命名工程"
            _hint = ("先 project save，或带 force=true 重开" if _pname
                     else "先 project create + project save 落一份，或带 force=true 重开")
            emit({"event": "error", "error": f"{_who}保存之后又改过（未保存）：{_hint}"})
            return
        t0 = monotonic_ns()
        try:
            from .project_recovery_runtime import owner as recovery_owner
            backup = recovery_owner(self, emit).store.backup_before_migration(path)
            if backup['required']:
                prj = backup['project']
                prj['_source_path'] = os.path.abspath(path)
                prj['_source_sha256'] = backup['sha256']
                emit({'event':'project_migration_backup', 'path':backup['backup_path'],
                      'sha256':backup['sha256'], 'original_untouched':True})
            else:
                prj = PJ.load(path)
            for document in prj["docs"]:
                for version in document["versions"]:
                    if version.get("recipe") is not None:
                        WB.prepare_state(version["recipe"])
        except (ValueError, RuntimeError, OSError) as e:
            emit({"event": "error", "error": f"项目打开失败：{e}"})
            return
        dc = {"RepairOp": RepairOp, "LightOp": LightOp}
        rows, notes = [], []
        for prow in prj["docs"]:
            try:
                recipe, dropped = PJ.active_recipe(prj, prow["path"], dc_types=dc, document_id=prow["document_id"])
            except ProjectError as e:
                # 一张图坏了不把整个工程锁在外面：这一格降级成“没调过”，原因跟着走
                recipe, dropped = None, [{"at": "recipe", "reason": str(e)}]
            st = self._fresh_doc_state()
            if isinstance(recipe, dict):
                extra = set(recipe) - set(st)
                if extra:
                    notes.append({"path": prow["path"],
                                  "reason": f"配方里有本版本不认识字段：{sorted(extra)}"})
                st.update({k: v for k, v in recipe.items() if k in st})
            if dropped:
                notes.append({"path": prow["path"], "dropped": dropped})
            row = self._new_row(prow["path"], state=st, budget=prow.get("budget"))
            row.update({"tags": list(prow.get("tags") or []), "label": prow.get("label"),
                        "trashed": bool(prow.get("trashed")),
                        "fingerprint": prow.get("fingerprint"),
                        # 项目里的格子都是“被打开并调过”的（哪怕配方是空的）：不置这一位，
                        # load_image 会把它当刚扫出来的新图，把宿主要的那步 precompute 跳掉
                        "opened": True})
            from .virtual_copy_project import restore_row
            try: restore_row(prj, prow, row, PJ, dc)
            except (ValueError,TypeError) as error:
                emit({"event":"error","error":str(error)}); return
            rows.append(row)
        for candidate in rows:
            WB.prepare_state(candidate["state"])
        notes.extend({"reason": note} for note in prj.get("migration_notes", []))
        try:people_history=self._people_stage_project(prj,rows)
        except (ValueError,RuntimeError,OSError) as error:
            emit({"event":"error","error":"People project history rejected: "+str(error)});return
        with self._doclock:
            self._docs = rows
        self._semantic_workspace_reset();self._document_versions().new_workspace()
        # 工程带着自己那一档预览尺寸回来：代理档不只是“快不快”，逐点层（逐点掩膜/
        # 笔迹/形变场）就活在那一档的像素坐标上。拿默认档重开就会把刚恢复的笔迹当成
        # “尺寸不对”清掉——那正是“保存重开后配方少了一半”的形状。只有一致的预算才沿用；
        # 不一致（手工换过档）就走引擎默认，并由 _proxy 不配那条守卫逐张作废。
        budgets = {int(r["budget"]) for r in rows if r.get("budget")}
        proxy_budget = next(iter(budgets)) if len(budgets) == 1 else None
        if proxy_budget is not None and self._proxy_budget is None:
            self._proxy_budget = proxy_budget
        self._people_load(prj,people_history)
        self._project, self._project_path = prj, os.path.abspath(path)
        from .project_recovery_runtime import owner as recovery_owner
        recovery_owner(self, emit).switch()
        self._project_saved_ns, self._project_dirty = prj.get("updated_ns"), False
        self._project_disk_sha256 = prj.get("_source_sha256")
        # 写手环境不一致：说出口，不拒开。同一份配方在另一版 numpy/torch 上算出的
        # 字节可能差几 LSB（逐层舍入方向），用户看到“重开后画面微妙不同”时得有一条
        # 能指认的原因，而不是只能怀疑自己记错了。旧版本工程没这一格也算不一致吗？
        # 不算：缺键是“没说”，不是“说了不一样”，这里只在两边都有值且不同时响。
        w = prj.get("writer")
        if w and w != _current_writer():
            diff = sorted(k for k in set(w) | set(_current_writer())
                          if w.get(k) != _current_writer().get(k))
            emit({"event": "engine_warn",
                  "warn": f"这份工程由另一套环境写下（差异项：{diff}；"
                          f"它写时 engine={w.get('engine')} torch={w.get('torch')}，"
                          f"现在是 engine={_current_writer()['engine']} "
                          f"torch={_current_writer().get('torch')}）。"
                          "重开照常编辑，但逐层舍入可能与保存前差几 LSB"})
        # 上一份工程的会话与历史在新底片条上没有意义：索引重置、栈清空
        self._doc_index, self._doc_path = -1, None
        self._image_loaded = False
        self._history_bind(None)
        missing = [m for m in PJ.missing_sources(prj) if not m["exists"]]
        changed = self._source_fingerprint_drift(prj)
        # Keep opening audit visible across later state/edit/save events.
        self._project_source_notice = {
            "changed": changed[:12], "changed_count": len(changed),
            "missing": missing[:12], "missing_count": len(missing),
        }
        # 重开默认展哪一张：先定下来再发事件，否则 `project_opened` 里的
        # auto_opened 与随后那一摞 shm_ready/image_ready 对不上人（上报与执行
        # 隔了一拍就是这种形状：事件说“没开”，视口上却亮着一张）。
        # 回收站里的格子不当默认那张：一份全在回收站里的工程，重开就该是空视口。
        target = None
        if p.get("document_id") is not None or p.get("index") is not None:
            target = self._row_target(p)
            if target is None:
                return
        elif isinstance(p.get("doc"), str) and p["doc"] != "none":
            target = self._row_target({"action": "open", "path": p["doc"]})
            if target is None:
                return
        elif rows and p.get("doc") != "none":
            target = next((r for r in rows if r["document_id"] == prj.get("active_document_id") and not r["trashed"]), None)
            if target is None: target = next((r for r in rows if not r["trashed"]), None)
        emit({"event": "project_opened", "docs": len(rows),
              "auto_opened": (target or {}).get("path"),
              # 叫 task_restore 而不叫 tasks：下面那份 `**self._project_state()` 里有一个
              # `tasks`（台账格数），字典字面量后写的吃先写的——同一个名字在这一行里
              # 一个是清单一个是整数（上一轮 dropped 就漂过同一形，而这一形是本轮
              # 端到端用例直接响出来的：len(7) 那种 TypeError 就是它）
              "task_restore": self._tasks_restore(prj),
              "proxy_budget": self._proxy_budget,
              "missing": missing, "missing_count": len(missing),
              "changed": changed[:12], "changed_count": len(changed),
              "restore_ms": round((monotonic_ns() - t0) / 1e6, 2),
              "saved_ns": prj.get("updated_ns"),
              "assets": len(prj.get("assets") or {}),
              "notes": notes[:12], "notes_count": len(notes),
              **self._project_state()})
        self.emit_session_state()
        if target is not None:
            cmd = {"path": target["path"], "document_id": target["document_id"]}
            if self._proxy_budget:
                cmd["max_px"] = int(self._proxy_budget)
            # 重开那一张走的就是 load_image 同一条路（守卫/尺寸比对/预计算重挂/事件形状
            # 全部同源），不在这里写第二份“把配方装回去”
            # 但关键点不在工程文件里（它是派生物）：配方靠它的那几层必须在这里主动补
            # 一次分析，不然就是“重开后那一层形变悄悄消失”（CORE-001）。后端跟着存下来的
            # 那一个走：点名 mediapipe 而后端不在时报错，不静默回落成 template 凑一层假形变。
            if self._recipe_needs_landmarks(target.get("state") or {}) and (target.get("state") or {}).get("_precompute") is None:
                cmd["precompute"] = True
                cmd["backend"] = ((target.get("state") or {}).get("_precompute_backend")
                                   or "mediapipe")
            self.cmd_load_image(cmd)
        return
    if action == "save":
        if self._project is None:
            emit({"event": "error", "error": "还没有项目：先 project create，"
                  "或 project open 打开已有工程（保存不会静默在未命名工程里造文件）"})
            return
        prj, facts = self._project_build(self._project)
        try:
            info = PJ.save(prj, self._project_path)
        except (ProjectError, OSError) as e:
            # 写失败不能清脏标记：那时徽章说“已保存”而磁盘上还是旧的一份，
            # 用户相信那句话才会真的丢工
            emit({"event": "error", "error": f"项目保存失败，脏状态原样保留：{e}"})
            return
        self._project = prj
        self._project_saved_ns, self._project_dirty = info["updated_ns"], False
        self._project_disk_sha256 = info["sha256"]
        emit({"event": "project_saved", "bytes": info["bytes"], "sha256": info["sha256"],
              "write_ms": info["write_ms"], "path": info["path"],
              # 清单逐条发（上限 12 条，多了只报数）：“哪一层没存进去”必须能在批量
              # 报告里复查，只在批级别说一句“有丢弃”是没法查的
              "dropped": prj.get("dropped", [])[:12],
              "assets": len(prj.get("assets") or {}), **facts, **self._project_state()})
        self.emit_session_state()
        return
    # tag / trash：改的是底片条那一格，而校验只有一份（project.set_tags / set_trashed）
    row = self._row_target(p)
    if row is None:
        return
    shim = {"docs": self._docs}
    try:
        if action == "tag":
            self._document_versions().check_advance(row)
            PJ.set_tags({"docs":[row]}, row["path"], p.get("tags"))
            if p.get("label") is not None:
                row["label"] = str(p["label"])[:64]
            self._document_versions().advance(row)
        else:
            from .virtual_copy_host import affected
            linked = affected(self._docs, [row["document_id"]], "trash" if p.get("trashed",True) else "restore")
            for target in linked: self._document_versions().check_advance(target)
            for target in linked:
                target["trashed"] = bool(p.get("trashed",True))
                self._document_versions().advance(target)
    except ProjectError as e:
        emit({"event": "error", "error": f"{action} 被拒，工程记录原样未动：{e}"})
        return
    if action == "trash" and 0 <= self._doc_index < len(self._docs) and self._docs[self._doc_index].get("trashed"):
        self._remember_current(); self._cancel_snapshot("trash")
        self._load_id = ""; self._image_loaded = False
        self._doc_index, self._doc_path = -1, None; self._history_bind(None)
    # 工程记录也改了（与 EDIT_CMDS 那条“真改了文档状态”是两件事，这里必须自己上）
    self._project_dirty = True
    emit({"event": "project_edited", "action": action, "path": row["path"],
          "tags": list(row.get("tags") or []), "label": row.get("label"),
          "trashed": bool(row.get("trashed")), **self._project_state()})
    self.emit_session_state()
