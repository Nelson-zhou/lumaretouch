"""Batch synchronization lifecycle with explicit session/editor ports.

Session owns document rows; this controller borrows them only during synchronous
commands. The controller alone owns batch identities, undo ledger and summaries.
"""
from . import brow_shape_scope as BROW, nose_shape_scope as NOSE, eye_shape_scope as EYE, mouth_shape_scope as MOUTH
from . import white_balance_recipe as WB
from dataclasses import dataclass
from typing import Callable
from . import scope as SC, reference_color_scope as RC
from . import sky_replacement_scope as SKY, optics_auto_scope as OA, id_background_scope as ID_BACKGROUND
from .document_versions import DocumentVersions
from .batch_preflight_controller import FrozenBatchController,PlanPorts
from . import creative_derived_source as SOURCE, creative_derived_transfer as TRANSFER

ACTIONS = ("preflight", "commit", "undo", "redo", "state", "people_targets")
KEYS = {"cmd", "action", "docs", "module_scope", "conflict_policy", "batch_id", "preflight_token", "request_id", "local_mask_transfer", "reference_color", "people_transfer"}
POLICIES = ("skip_and_report", "recheck")


def verify_history_source(row, record, ops, previous):
    """Bind scoped history to its target, including dormant derived frames.

    A legacy original-only receipt stays usable for originals. It can never
    authorize a newly derived current row or hide a derived before/after frame.
    """
    states=(row['state'],record['before'],record['after'])
    proof=record.get('source_proof')
    if proof is None:
        if any(SOURCE.record(state) is not None for state in states):
            raise ValueError('Legacy batch history lacks an effective-source proof')
        return
    proof=SOURCE.verify_row(row,proof)
    for state in states[1:]:
        SOURCE.verify_row({**row,'state':state},proof)
    TRANSFER.require_modules(row['state'],SC.params_of(previous,ops),proof,related_states=states[1:])

@dataclass(frozen=True)
class BatchDocuments:
    rows: Callable[[], list[dict]]
    current_index: Callable[[], int]
    remember_current: Callable[[], None]
    index_of: Callable[[str], int]

@dataclass(frozen=True)
class BatchEditor:
    guard: Callable[[str], str | None]
    capture: Callable[[], dict]
    replay: Callable[..., dict]
    face_known_single: Callable[..., tuple[str, str]]
    status: Callable[[], dict]
    mark_dirty: Callable[[], None] = lambda:None
    invalidate: Callable[[], None] = lambda:None
    prepare_optics: Callable | None = None
    prepare_reference: Callable | None = None
    capture_reference: Callable | None = None
    people_restore: Callable | None = None
    people_transfer: Callable | None = None

class BatchSyncController:
    def __init__(self, documents: BatchDocuments, editor: BatchEditor,
                 emit: Callable[[dict], None], clock: Callable[[], float],
                 monotonic: Callable[[], int], history_limit: int, versions=None):
        self.documents = documents
        self.editor = editor
        self.emit = emit
        self.clock = clock
        self.monotonic = monotonic
        self.history_limit = history_limit
        self.ledger = {}
        self.sequence = 0
        self.last_result = None
        self.versions=versions if versions is not None else DocumentVersions()
        self.preflight=FrozenBatchController(PlanPorts(lambda:self.documents.rows(),lambda:self.documents.current_index(),
            lambda:self.documents.remember_current(),lambda:self.editor.capture(),lambda docs:self.target_indices(docs),
            lambda row,**kw:self.editor.face_known_single(row,**kw),lambda *a,**kw:self.commit(*a,**kw),self.editor.prepare_optics,self.editor.prepare_reference,self.editor.capture_reference,self.editor.people_transfer),
            self.versions,lambda event:self.emit(event),monotonic)

    def target_indices(self, docs) -> tuple[list[int], list[dict]]:
        """`docs` → 底片条格号。能收索引也能收路径（宿主两边都可能有）。

        收不到的那一格**不静默丢**：它进 `bad` 列表，调用方把它报进事件里。默默少同步
        两张而用户不知道，是“批量”最阴的一种错。
        """
        if isinstance(docs, (str, bytes)) or not docs:
            raise SC.ScopeError("batch 的 docs 必须是非空的格号/路径列表")
        out: list[int] = []
        bad: list[dict] = []
        for d in docs:
            if isinstance(d, bool) or not isinstance(d, (int, str)):
                bad.append({"doc": str(d), "error": "格号必须是整数或路径"})
                continue
            if isinstance(d, int):
                if 0 <= d < len(self.documents.rows()) and d not in out:
                    out.append(d)
                else:
                    bad.append({"doc": d, "error": "格号超出底片条范围"})
                continue
            match = self.versions.find(self.documents.rows(),d)
            try: i = match[0] if match else self.documents.index_of(d)
            except ValueError as error:
                bad.append({"doc":d,"error":str(error)}); continue
            if i < 0:
                bad.append({"doc": d, "error": "这张图不在底片条里"})
            elif i not in out:
                out.append(i)
        if not out:
            raise SC.ScopeError(f"batch 没有可用目标（全部被拒）：{bad}")
        return out, bad

    def _reject(self,p,message):
        self.emit({"event":"error","error":message})
        if isinstance(p.get("request_id"),str) and 1<=len(p["request_id"])<=128:
            self.preflight.emit_result(p,{"success":False,"error":message,"requires_preflight":True})

    def handle_command(self, p: dict):
        """批量同步（LNX-P0-BATCH / BATCH-001…4）。

        语义：“把当前文档在 `module_scope` 那几个模块里的配方，盖到选中的每一格上”。
        作用域走的就是预设那一份 `scope`，所以“预设能改的”与“批量能同步的”完全一致。

        只改参数，不改原片：目标格的 `state` 是项目记录，源文件一个字节不写。
        逐格历史也能撤销这一笔：非活动格把 commit 前的快照推进它自己的 undo 栈，
        活动格走 `lnx.batch.v1` 在 EDIT_CMDS 里那一步。
        """
        request=p.get("request_id")
        if request is not None and (not isinstance(request,str) or not 1<=len(request)<=128):
            self.emit({"event":"error","error":"invalid batch request identity"});return
        unknown = set(p) - KEYS
        if unknown:
            self._reject(p,f"batch 收到不认识的参数：{sorted(unknown)}")
            return
        action = p.get("action", "state")
        if action not in ACTIONS:
            self._reject(p,f"未知 batch action: {action}（可用：{'/'.join(ACTIONS)}）")
            return
        if action == "state":
            self.emit({"event": "batch_state", "batches": [
                {"batch_id": k, "ops": v["ops"], "targets": len(v["targets"]),
                 "undone": v["undone"], "at_ns": v["at_ns"]} for k, v in self.ledger.items()],
                 "modules": SC.describe()})
            return
        if action == "people_targets":
            try:
                if self.preflight.ports.people_transfer is None:raise ValueError('People transfer adapter unavailable')
                self.preflight.ports.people_transfer(self.preflight,p,None)
            except Exception as error:self._reject(p,str(error))
            return
        if action=="commit" and p.get("preflight_token") is not None:
            try:
                if self.preflight.replay_completed(p):return
            except Exception as error:self._reject(p,str(error));return
        why = self.editor.guard(f"batch {action}")
        if why:
            self._reject(p,why)
            return
        if action=="preflight" or (action=="commit" and p.get("preflight_token") is not None):
            self.preflight.handle(p);return
        try:
            if action in ("undo","redo"):
                from .batch_group_history import restore_group
                from .people_batch_ledger import restore as restore_people
                if self.ledger.get(str(p.get("batch_id")),{}).get("semantic_colour_owned"):
                    from .semantic_colour_batch_ledger import restore as restore_semantic
                    started=False
                    def semantic_write_started():
                        nonlocal started
                        started=True
                    try:body=restore_semantic(self,p,before_write=semantic_write_started)
                    except Exception as error:
                        self.emit({"event":"error","error":str(error)})
                        self.preflight.emit_result(p,{"success":False,"error":str(error),"outcome_unknown":started,
                            "batch_id":p.get("batch_id"),"requires_preflight":True})
                        return
                elif "people_changes" in self.ledger.get(str(p.get("batch_id")),{}):
                    body=restore_people(self,p)
                else:body=restore_group(self,p) if action=="redo" or RC.OP in self.ledger.get(str(p.get("batch_id")),{}).get("ops",[]) else self.undo(p)
                self.preflight.emit_result(p,{**body,"success":True})
                return
            if p.get("people_transfer") is not None:raise SC.ScopeError("People transfer requires a frozen preflight token")
            ops = SC.check_scope(p.get("module_scope"))
            if SC.SEMANTIC.OP in ops:raise SC.ScopeError(SC.SEMANTIC.REASON)
            if ID_BACKGROUND.OP in ops:raise SC.ScopeError("证件照背景必须先逐目标预检，不会复制其他照片的审核范围")
            if SKY.OP in ops:
                raise SC.ScopeError("换天空批量必须逐目标预检，再用冻结 token 提交；不会猜测天空或复制源图区域")
            if RC.OP in ops:raise SC.ScopeError('参考统一必须先逐图预检')
            if OA.OP in ops:raise SC.ScopeError('自动镜头/透视必须先逐目标冻结预检，不能直接复制源照片分析')
            if SC.OP_LOCAL_GRADE in ops:
                raise SC.ScopeError('独立局部调色必须先逐目标预检，再用冻结 token 提交；不允许未审核直传')
            policy = p.get("conflict_policy", "skip_and_report")
            if policy not in POLICIES:
                raise SC.ScopeError(f"conflict_policy 未知：{policy!r}"
                                    f"（可用：{'/'.join(POLICIES)}；没有 overwrite 是冻结的）")
            idxs, bad = self.target_indices(p.get("docs"))
            self.documents.remember_current()
            src = self.editor.capture()
            mods = SC.params_of(src, ops)
            source_row=self.documents.rows()[self.documents.current_index()]
            source_owned=SOURCE.record(src) is not None or any(SOURCE.record(self.documents.rows()[i].get('state') or {}) is not None for i in idxs)
            source_proof=SOURCE.row_proof({**source_row,'state':src}) if source_owned else None
            TRANSFER.require_modules(src,mods,source_proof)
            rows = []
            for i in idxs:
                row = self.documents.rows()[i]
                live = (i == self.documents.current_index())
                blocked = None
                target_proof=None
                try:
                    target_state=src if live else row['state']
                    if source_owned:target_proof=SOURCE.row_proof({**row,'state':target_state})
                    TRANSFER.require_modules(target_state,mods,source_proof)
                except Exception as error:blocked=str(error)[:2000]
                for op in ops:
                    if SC.MODULES[op]["single_face"]:
                        verdict, reason = self.editor.face_known_single(row, live=live)
                        if verdict != "ok":
                            blocked = f"{op}: {reason}"
                            break
                rows.append({"index": i, "path": row["path"], "live": live,
                             "blocked": blocked,
                             "_source_proof":target_proof,
                             "before": SC.params_of(row["state"] if not live else src, ops)})
            if policy == "recheck" and any(r["blocked"] for r in rows):
                raise SC.ScopeError(f"recheck 策略下有目标不合格，整条不提交："
                                    f"{[r['path'] for r in rows if r['blocked']]}")
            source_snapshot=None
            if source_proof is not None:
                SOURCE.verify_row({**source_row,'state':self.editor.capture()},source_proof)
                version=self.versions.version(source_row)
                source_snapshot={'document_id':version.document_id,'revision':str(version.revision),
                                 'path':source_row['path'],'source_proof':source_proof}
            body=self.commit(ops, mods, rows, policy, bad,source_snapshot=source_snapshot)
            self.preflight.emit_result(p,{**body,"success":True,"mode":"direct_unreviewed"})
        except Exception as e:
            self._reject(p,f"batch {action} 被拒：{e}")

    def commit(self, ops: list[str], mods: dict, rows: list[dict],
                      policy: str, bad: list[dict], source_snapshot=None) -> dict:
        """原子提交：先算好每一格的新状态，全部合法才一次性写回。

        中途失败不能留下“同步了一半”的批量——这跟导出那一条“一个目标失败不该拖垮整批，
        但记账要逐格”是同一个要求：skip 是**事先判出来的**，不是跑中途抱的。
        """
        live_idx = self.documents.current_index()
        planned: list[tuple[int, dict, dict]] = []
        applied_rows = []
        proofs={}
        source_proof=(source_snapshot or {}).get('source_proof')
        if source_proof is not None:source_proof=SOURCE.check_row_proof(source_proof)
        source_state=self.editor.capture()
        source_owned=SOURCE.record(source_state) is not None or any(
            SOURCE.record(self.documents.rows()[item['index']].get('state') or {}) is not None
            for item in rows if not item['blocked'])
        if source_snapshot is None and source_owned:
            source_row=self.documents.rows()[live_idx]
            source_proof=SOURCE.row_proof({**source_row,'state':source_state})
            version=self.versions.version(source_row)
            source_snapshot={'document_id':version.document_id,'revision':str(version.revision),
                             'path':source_row['path'],'source_proof':source_proof}
        # A frozen source may have changed or disappeared. Its reviewed scalar
        # recipe remains authoritative; only exact target proofs are rechecked.
        TRANSFER.require_modules({} if source_snapshot is not None else source_state,mods,source_proof)
        for r in rows:
            if r["blocked"]:
                continue
            row = self.documents.rows()[r["index"]]
            if not isinstance(row.get("undo"),list) or not isinstance(row.get("redo"),list):
                raise SC.ScopeError("target history is invalid; no target was written")
            self.versions.check_advance(row)
            before = dict(row["state"]) if r["index"] != live_idx else dict(self.editor.capture())
            prepared=r.get('_prepared_modules') or mods
            proof=r.get('_source_proof')
            if proof is not None:proof=SOURCE.verify_row({**row,'state':before},proof)
            elif source_proof is not None or SOURCE.record(before) is not None:
                if source_snapshot is not None:raise SC.ScopeError('Target lacks its reviewed effective-source proof')
                proof=SOURCE.row_proof({**row,'state':before})
            TRANSFER.require_modules(before,prepared,source_proof)
            new = OA.candidate(before,prepared,local_replace_legacy=r.get('_local_replace_legacy', False))
            TRANSFER.require_candidate(before,new,prepared,source_proof)
            if OA.OP in ops:
                if r.get('_optics_prepared') is None:raise SC.ScopeError('缺少冻结目标镜头/透视预检')
                version=self.versions.version(row)
                new['_optics']=OA.verify_target(r['_optics_prepared'],before,new,row,version.document_id,version.revision,prepared[OA.OP])
            if RC.OP in ops:
                version=self.versions.version(row)
                recipe=RC.verify_target(r.get('_reference_prepared'),before,new,row,version.document_id,version.revision,prepared[RC.OP])
                RC.apply_verified(new,recipe)
            if ID_BACKGROUND.OP in ops:ID_BACKGROUND.validate_target(new,row["path"],(row["src_h"],row["src_w"]))
            if SKY.OP in ops:
                SKY.validate_target(new["_sky_replacement"],row["path"],(row["src_h"],row["src_w"]))
            if BROW.OP in ops and OA.OP not in ops: BROW.validate_target(new,row)
            if NOSE.OP in ops and OA.OP not in ops: NOSE.validate_target(new,row)
            if EYE.OP in ops and OA.OP not in ops: EYE.validate_target(new,row)
            if MOUTH.OP in ops and OA.OP not in ops: MOUTH.validate_target(new,row)
            WB.prepare_state(new)
            if proof is not None:SOURCE.verify_row({**row,'state':new},proof)
            proofs[r['index']]=proof
            planned.append((r["index"], before, new))
            applied_rows.append(r)
        if not planned:
            raise SC.ScopeError("所有目标都不合格，这一批一个也没写（见 preflight 里的 blocked）")
        for idx,before,new in planned:
            if proofs[idx] is not None:
                row=self.documents.rows()[idx]
                SOURCE.verify_row({**row,'state':self.editor.capture() if idx==live_idx else row['state']},proofs[idx])
        self.sequence += 1
        batch_id = f"batch-{self.sequence:03d}-{int(self.clock() * 1000)}"
        targets: dict[str, dict] = {}
        fr=None
        # Render/validate the live target before committing any parked rows.
        live_plan=next((item for item in planned if item[0]==live_idx),None)
        if live_plan is not None:
            idx,before,new=live_plan;self.versions.advance(self.documents.rows()[idx])
            try:
                fr=self.editor.replay(new,mode="batch",replayed_for=f"batch:{batch_id}",
                                      **({'strict_local':True} if SOURCE.record(new) is not None or ID_BACKGROUND.OP in ops or SC.OP_LOCAL_GRADE in ops or SKY.OP in ops or OA.OP in ops or BROW.OP in ops or NOSE.OP in ops or EYE.OP in ops or MOUTH.OP in ops or RC.OP in ops else {}))
                # A render may be expensive. Do not publish parked candidates
                # whose provenance changed while the active target rendered.
                for target_index,_,_ in planned:
                    if proofs[target_index] is not None:
                        target=self.documents.rows()[target_index]
                        SOURCE.verify_row({**target,'state':self.editor.capture() if target_index==live_idx else target['state']},proofs[target_index])
            except Exception as error:
                try:
                    rollback=self.editor.replay(before,mode="batch",replayed_for=f"batch_rollback:{batch_id}")
                    if rollback is not None:self.emit(rollback)
                except Exception as rollback_error:
                    self.editor.invalidate()
                    self.emit({"event":"engine_warn","warn":f"batch rollback failed: {rollback_error}; reload the active document"})
                raise SC.ScopeError(f"live target failed before parked writes: {error}") from error
        self.editor.mark_dirty()
        for idx, before, new in planned:
            row = self.documents.rows()[idx]
            if idx != live_idx:
                self.versions.advance(row)
                row["state"] = new
                row["undo"].append(before)
                if len(row["undo"]) > self.history_limit:del row["undo"][0]
                row["redo"].clear()
            targets[str(idx)] = {"path": row["path"], "before": before, "after": new,
                "applied":OA.before_params(new, ops),"live":idx==live_idx,"document_id":self.versions.version(row).document_id,
                **({'source_proof':proofs[idx]} if proofs[idx] is not None else {}),
                "local_key":SC.LOCAL_GRADE.undo_key(new) if SC.OP_LOCAL_GRADE in ops else None}
        self.ledger[batch_id] = {"ops": ops, "targets": targets, "at_ns": self.monotonic(),
                                   "undone": False, "policy": policy,"source_snapshot":source_snapshot}
        self.last_result = {"kind": "commit", "batch_id": batch_id,
                           "applied": [r["index"] for r in applied_rows],
                           "skipped": [{"index": r["index"], "path": r["path"],
                                        "reason": r["blocked"]} for r in rows if r["blocked"]]}
        body = {"event": "batch_committed", "batch_id": batch_id, "module_scope": ops,
                "applies": mods, "policy": policy,
                "targets": [r["index"] for r in applied_rows],
                "skipped": [{"index": r["index"], "path": r["path"], "reason": r["blocked"]}
                            for r in rows if r["blocked"]],
                "rejected_docs": bad, "doc_state": self.editor.status()}
        if fr is not None:
            fr.pop("render_ms", None)
            body["frame"] = fr
        self.emit(body)
        if fr is not None:
            self.emit(fr)
        return body

    def undo(self, p: dict) -> None:
        """撤销这一批（BATCH-004）：没被动过的还原，被动过的**报冲突不动它**。

        判据不是“时间戳新旧”，而是“这一格上那几个模块现在的参数，还是不是我当初写
        进去的那组”：相等 → 同步之后没人碰，还原安全；不等 → 用户在同步后又编辑了，
        抹掉他的后续修改就是把人的工弄没。比较范只限 `module_scope`，因为同批之外
        的模块本来就没被我们写过。
        """
        bid = str(p.get("batch_id") or "")
        b = self.ledger.get(bid)
        if b is None:
            raise SC.ScopeError(f"没有这批同步的记录：{bid!r}（可用："
                                f"{', '.join(self.ledger) or '无'}）")
        if b["undone"]:
            raise SC.ScopeError(f"这批已经撤销过了：{bid}")
        ops = b["ops"]
        # 先把当前这一格的 live 状态存回去再比。不存就是用**陈快照**当事实：
        # “同步后又被编辑”那一笔还停在 live 字段里，而 row["state"] 还是 commit 时那一版，
        # 一比就“没冲突”——本轮实测就是这个 bug：被编辑过的那一格也被还原了。
        self.documents.remember_current()
        restored, conflicts, planned = [], [], []
        history_proofs={}
        for key, rec in b["targets"].items():
            idx = int(key)
            if rec.get("document_id"):
                found=self.versions.find(self.documents.rows(),rec["document_id"])
                idx=found[0] if found is not None else len(self.documents.rows())
            if idx >= len(self.documents.rows()) or self.documents.rows()[idx]["path"] != rec["path"]:
                conflicts.append({"index": idx, "path": rec["path"],
                                  "reason": "这一格已经不在底片条上（或换了图），不能还原"})
                continue
            row = self.documents.rows()[idx]
            cur = row["state"]
            if rec.get('local_key') is not None and SC.LOCAL_GRADE.undo_key(cur) != rec['local_key']:
                conflicts.append({'index':idx,'path':rec['path'],
                    'reason':'局部组、旧调色槽或关联 LUT 已在同步后修改；不覆盖后续编辑'})
                continue
            if OA.before_params(cur, ops) != rec["applied"]:
                conflicts.append({"index": idx, "path": rec["path"],
                                  "reason": "同步后又被编辑过：不抹后续修改",
                                  "now": OA.before_params(cur, ops), "applied": rec["applied"]})
                continue
            # Conflict checks are scoped; restoration must use the same scope.
            # Restoring the whole old snapshot would erase later unrelated edits.
            try:
                verify_history_source(row,rec,ops,rec['before'])
                restored_state = SC.restore_modules(cur, rec["before"], ops)
                if rec.get('source_proof') is not None:
                    TRANSFER.require_candidate(cur,restored_state,SC.params_of(rec['before'],ops),rec['source_proof'])
                    SOURCE.verify_row({**row,'state':restored_state},rec['source_proof'])
                if ID_BACKGROUND.OP in ops:ID_BACKGROUND.validate_target(restored_state,row["path"],(row["src_h"],row["src_w"]))
                if SKY.OP in ops:
                    SKY.validate_target(restored_state["_sky_replacement"],row["path"],(row["src_h"],row["src_w"]))
                if OA.OP in ops:OA.validate_restoration(restored_state,row)
                WB.prepare_state(restored_state)
                self.versions.check_advance(row)
            except Exception as error:
                conflicts.append({"index": idx, "path": rec["path"],
                                  "reason": f"还原配方与后续修改不兼容：{str(error)[:500]}"})
                continue
            planned.append((idx, row, cur, restored_state))
            history_proofs[idx]=rec.get('source_proof')
        # Validate every candidate first, then render the active target before any
        # parked writes. An invalid cross-module combination is an explicit conflict.
        live_idx = self.documents.current_index()
        for idx,row,previous,restored_state in planned:
            if history_proofs[idx] is not None:SOURCE.verify_row(row,history_proofs[idx])
        live = next((item for item in planned if item[0] == live_idx), None)
        if live is not None:
            _, row, previous, restored_state = live
            self.versions.advance(row)
            try:
                frame = self.editor.replay(restored_state, mode="batch", replayed_for=f"batch_undo:{bid}",
                                          **({'strict_local':True} if SOURCE.record(restored_state) is not None else {}))
                for target_index,target,_,_ in planned:
                    if history_proofs[target_index] is not None:
                        SOURCE.verify_row({**target,'state':self.editor.capture() if target_index==live_idx else target['state']},history_proofs[target_index])
                if frame is not None:
                    self.emit(frame)
            except Exception as error:
                try:
                    frame = self.editor.replay(previous, mode="batch", replayed_for=f"batch_undo_rollback:{bid}")
                    if frame is not None:
                        self.emit(frame)
                except Exception as rollback_error:
                    self.editor.invalidate()
                    self.emit({"event": "engine_warn", "warn": f"batch undo rollback failed: {rollback_error}; reload the active document"})
                raise SC.ScopeError(f"batch undo live target failed before parked writes: {error}") from error
        for idx, row, previous, restored_state in planned:
            if idx != live_idx:
                self.versions.advance(row)
            row["state"] = restored_state
            self.editor.mark_dirty()
            restored.append(idx)
        b["undone"] = True
        self.last_result = {"kind": "undo", "batch_id": bid, "restored": restored,
                           "conflicts": [{"index": c["index"], "path": c["path"],
                                          "reason": c["reason"]} for c in conflicts]}
        body={"event": "batch_undone", "batch_id": bid, "module_scope": ops,
              "restored": restored, "conflicts": conflicts, "doc_state": self.editor.status()}
        self.emit(body)
        return body

    def summary(self) -> dict:
        """批量同步台账（不是导出任务队列）：撤销入口要能拿到 batch_id。

        `last_result` 是上一笔 commit/undo 的**事实**（写了哪几格、跳过哪几格及原因、
        冲突哪几格）：UI 要显示“同步了 3 张，2 张因为多人照片没动”这句话，只能拿
        引擎报的这份，不能自己数多选框里有几个——那是“自报了个没发成的成功”。
        """
        items = [{"batch_id": k, "module_scope": v["ops"], "targets": len(v["targets"]),
                  "undone": v["undone"]} for k, v in self.ledger.items()]
        un = [i for i in items if not i["undone"]]
        return {"batches": items, "undoable": [i["batch_id"] for i in un],
                "last": un[-1]["batch_id"] if un else None,
                "last_result": getattr(self, "last_result", None)}

