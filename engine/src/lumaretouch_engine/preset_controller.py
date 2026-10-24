"""Module presets: validated operations and correlated, post-history receipts.

The dispatcher calls finish() after its history bookkeeping. Legacy events remain
available. Receipt replay is bounded to this engine session/cache; clients must
query an uncertain request, never automatically resubmit a mutation.
"""
from . import brow_shape_scope as BROW, nose_shape_scope as NOSE, eye_shape_scope as EYE, mouth_shape_scope as MOUTH
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable
from . import scope as SC, preset_store as PS, reference_color_scope as RC
from .preset_transaction import apply_with_rollback, PresetApplyError
from .preset_organisation_store import OrganisationError
from . import local_grade_layers as LG
from . import sky_replacement_scope as SKY, optics_auto_scope as OA, id_background_scope as ID_BACKGROUND
from . import creative_derived_transfer as DERIVED, creative_derived_source as SOURCE
from . import body_scalar_transfer_review as BODY_REVIEW

ACTIONS = ("list", "preflight", "apply", "save", "import", "delete", "xmp_inspect")
LEGACY_KEYS = {"cmd", "action", "id", "path", "modules", "module_scope", "name", "kind", "force", "note", "local_mask_transfer", "preflight_token"}
FIELDS = {"list": set(), "apply": {"id", "document_id", "preflight_token", "xmp_review_ack", "spill_review_ack", "shadow_review_ack", "torso_review_ack", "waist_review_ack", "head_review_ack"},
          "preflight": {"id", "document_id", "local_mask_transfer", "module_scope"},
          "save": {"id", "name", "kind", "force", "note", "module_scope", "document_id", "local_mask_transfer"},
          "import": {"path", "id", "force", "xmp_ack"}, "xmp_inspect": {"path"}, "delete": {"id"}}
MAX_RECEIPTS = 64
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_CACHE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class PresetPorts:
    guard: Callable[[str], str | None]
    document_id: Callable[[], str]
    capture: Callable[[], dict]
    replay: Callable[..., dict]
    face_check: Callable[[], tuple[str, str]]
    status: Callable[[], dict]
    invalidate: Callable[[], None]
    target_row: Callable[[], dict] = lambda: {}
    revision: Callable[[], str] = lambda: ''
    advance: Callable[[], None] = lambda: None
    prepare_optics: Callable | None = None
    prepare_reference: Callable | None = None
    prepare_crop: Callable | None = None
    verify_crop: Callable | None = None
    prepare_xmp: Callable | None = None
    verify_xmp: Callable | None = None
    prepare_spill: Callable | None = None
    verify_spill: Callable | None = None
    prepare_shadow: Callable | None = None
    verify_shadow: Callable | None = None
    prepare_torso: Callable | None = None
    verify_torso: Callable | None = None
    prepare_waist: Callable | None = None
    verify_waist: Callable | None = None
    torso_history_identity: Callable | None = None
    waist_history_identity: Callable | None = None
    prepare_head: Callable | None = None
    verify_head: Callable | None = None
    head_history_identity: Callable | None = None


class PresetController:
    def __init__(self, ports: PresetPorts, emit: Callable[[dict], None]):
        self.ports = ports; self.emit = emit; self.last = None
        self._receipts = OrderedDict(); self._pending = {}; self._effect_started = False
        self._scalar_receipt = {}
        from .local_grade_preset_review import PresetReviews
        self.reviews = PresetReviews()

    def last_applied(self):
        if not self.last: return None
        try: current = OA.before_params(self.ports.capture(), self.last["ops"])
        except Exception: return None
        return {"id": self.last["id"], "name": self.last["name"]} if current == self.last["params"] else None

    def state(self):
        available = True
        try: docs, errors = PS.list_all()
        except Exception as error:
            available = False; docs = []
            errors = [{"file": PS.preset_dir(), "error": f"读预设目录失败：{error}"}]
        return {"list": docs, "errors": errors, "modules": SC.describe(), "dir": PS.preset_dir(),
                "schema": SC.PRESET_SCHEMA, "last_applied": self.last_applied(), "available": available, "organisation_protocol": 1, "xmp_import_protocol": 1}

    @staticmethod
    def request_id(p):
        value = p.get("request_id")
        try: return value if type(value) is str and 0 < len(value.encode("utf-8")) <= 128 else None
        except UnicodeError: return None

    @staticmethod
    def document_identity(p):
        value = p.get("document_id")
        try: return value if type(value) is str and 0 < len(value) <= 64 and len(value.encode("utf-8")) <= 128 else None
        except UnicodeError: return None

    def _validate(self, p, correlated):
        action = p.get("action", "list")
        if action not in ACTIONS: raise SC.ScopeError(f"未知 preset action: {action}")
        allowed = (FIELDS[action] | {"cmd", "action", "request_id"}) if correlated else LEGACY_KEYS
        if set(p) - allowed: raise SC.ScopeError(f"preset 收到不认识的参数：{sorted(set(p)-allowed)}")
        if correlated:
            if p.get("cmd", "preset") != "preset": raise SC.ScopeError("preset command mismatch")
            if "force" in p and type(p["force"]) is not bool: raise SC.ScopeError("force 必须是布尔值")
            for key in ("id", "name", "path", "kind", "note"):
                if key in p and type(p[key]) is not str: raise SC.ScopeError(f"{key} 必须是字符串")
            for key in ({"id"} if action in ("apply", "preflight", "save", "delete") else {"path"} if action in ("import", "xmp_inspect") else set()):
                if not p.get(key, "").strip(): raise SC.ScopeError(f"preset {action} 需要 {key}")
            if action == "save":
                if not p.get("name", "").strip(): raise SC.ScopeError("预设名称不能为空")
                if p["name"] != p["name"].strip() or len(p["name"]) > 80:
                    raise SC.ScopeError("预设名称最多 80 个字符，前后不能含空白")
                scope = p.get("module_scope")
                if type(scope) is not list or any(type(op) is not str for op in scope):
                    raise SC.ScopeError("module_scope 必须是模块名数组")
                SC.check_scope(p.get("module_scope"))  # New UI must choose explicitly.
            if action in ("apply", "preflight", "save"):
                document = self.document_identity(p)
                if document is None or document != self.ports.document_id():
                    raise SC.ScopeError("照片已经变化，请在当前照片上重新选择操作")
        if action in ("apply", "preflight", "save"):
            reason = self.ports.guard(f"preset {action}")
            if reason: raise SC.ScopeError(reason)
        return action

    def handle_command(self, p: dict):
        request = self.request_id(p); raw_action = p.get("action", "list")
        action = raw_action if type(raw_action) is str and raw_action in ACTIONS else "invalid"
        result = {"event": "preset_result", "protocol": 1, "request_id": request, "action": action,
                  "success": False, "outcome_unknown": False}
        if action in ("apply", "preflight", "save"):
            result["document_id"] = self.document_identity(p)
        digest = None; self._effect_started = False; self._scalar_receipt = {}
        try:
            if "request_id" in p and request is None: raise SC.ScopeError("preset request_id invalid")
            raw = json.dumps(p, sort_keys=True, allow_nan=False, ensure_ascii=False)
            if len(raw.encode()) > 65536: raise SC.ScopeError("preset command exceeds 64 KiB")
            digest = sha256(raw.encode()).hexdigest()
            if request in self._receipts:
                old_digest, old_result, _ = self._receipts[request]
                if old_digest != digest: raise SC.ScopeError("preset request_id reused with different arguments")
                self._pending[request] = (digest, {**deepcopy(old_result), "replayed": True})
                return
            action = self._validate(p, request is not None)
            if action == "list":
                catalog = self.state(); event = {"event": "preset_list", **catalog}; self.emit(event)
                if not catalog["available"]: raise SC.ScopeError("无法读取预设目录，详见目录错误")
                evidence = {"catalog": catalog}
            elif action == "preflight":
                doc = PS.find(p['id'])
                if 'module_scope' in p and (type(p['module_scope']) is not list
                        or p['module_scope']!=list(doc['modules'])):
                    raise SC.ScopeError('预设预检的预期模块与已存储配方不同；请刷新后重新选择')
                # Optional request scope binds the transport expectation only.
                # The actual stored preset remains the sole admission authority.
                reviewed_row=self.ports.target_row()
                reviewed_identity=(reviewed_row.get('document_id'),reviewed_row.get('path'),self.ports.document_id(),self.ports.revision())
                state = self.ports.capture()
                # The stored preset, never a caller's claimed module_scope,
                # decides whether this source can use the general route.
                DERIVED.require_modules(state, doc['modules'])
                family=BODY_REVIEW.select(doc['modules'])
                if family is not None and family.port_name in ('waist','head') and getattr(self.ports,family.port_name+'_history_identity') is None:
                    raise SC.ScopeError('身体参数预设缺少当前完整人物身份审核端口')
                for op in doc['modules']:
                    if SC.MODULES[op]['single_face']:
                        verdict, reason = self.ports.face_check()
                        if verdict != 'ok': raise SC.ScopeError(f'{op}：{reason}')
                evidence = self.reviews.prepare(doc, state, reviewed_row,
                    reviewed_identity[2], reviewed_identity[3], p.get('local_mask_transfer'), self.ports.prepare_optics, self.ports.prepare_reference,
                    self.ports.prepare_crop, self.ports.verify_crop, self.ports.prepare_xmp, self.ports.verify_xmp,
                    self.ports.prepare_spill, self.ports.verify_spill, self.ports.prepare_shadow, self.ports.verify_shadow,
                    self.ports.prepare_torso, self.ports.verify_torso,
                    self.ports.prepare_waist, self.ports.verify_waist,
                    self.ports.prepare_head, self.ports.verify_head)
                if family is not None:
                    current=self.ports.target_row()
                    from .optics_candidate_identity import fingerprint
                    if (current is not reviewed_row
                            or (current.get('document_id'),current.get('path'),self.ports.document_id(),self.ports.revision())!=reviewed_identity
                            or fingerprint(self.ports.capture())!=fingerprint(state)):
                        token=evidence['preflight_token']
                        self.reviews.pending.pop(token,None);self.reviews.targets.pop(token,None)
                        raise SC.ScopeError('身体长度预检期间目标发生变化，请重新审核')
            elif action == "xmp_inspect":
                from .preset_xmp_import import inspect
                evidence = inspect(p["path"])
            elif action == "apply": evidence = self.apply(p)
            elif action == "save": evidence = self.save(p)
            elif action == "import":
                path = str(p.get("path") or "")
                if not path: raise SC.ScopeError("preset import 需要 path")
                if path.lower().endswith(".xmp") or "xmp_ack" in p:
                    from .preset_xmp_import import load
                    doc = load(path, p.get("xmp_ack"))
                else:
                    doc = {k: v for k, v in PS.load_file(path).items() if k != "builtin"}
                    if "xmp_import" in doc: raise SC.ScopeError("Portable XMP presets require fresh compatibility acknowledgment; use XMP inspection")
                if p.get("id"): doc["id"] = str(p["id"])
                doc = SC.validate_preset(doc); self._effect_started = True
                saved = PS.save(doc, force=bool(p.get("force")))
                self.emit({"event": "preset_imported", "preset": doc, "path": saved, "dir": PS.preset_dir()})
                evidence = {"preset": doc, "id": doc["id"], "path": saved, "module_scope": list(doc["modules"])}
            else:
                self._effect_started = True; gone = PS.delete(str(p.get("id") or ""))
                self.emit({"event": "preset_deleted", "path": gone, "id": p.get("id")})
                evidence = {"id": p.get("id"), "path": gone}
            result.update(success=True, **evidence)
        except Exception as error:
            unknown = self._effect_started and not isinstance(error, SC.ScopeError)
            if isinstance(error, PresetApplyError):
                unknown = not error.rolled_back
                result.update(rolled_back=error.rolled_back, requires_reload=error.requires_reload)
            if isinstance(error, OrganisationError):
                unknown = error.outcome_unknown
            if isinstance(error, PS.PresetStorageError):
                unknown = error.outcome_unknown
                result["operation_committed"] = error.committed
            result.update(error=str(error)[:2000], error_code="outcome_unknown" if unknown else "rejected", outcome_unknown=unknown)
            self.emit({"event": "error", "error": f"preset {action}：{error}"})
        finally:
            if action == 'apply':result.update(deepcopy(self._scalar_receipt))
            if request is not None and request not in self._pending:
                self._pending[request] = (digest, result)

    def finish(self, p: dict, dispatch_error: str | None = None):
        """Call once after history bookkeeping, including dispatcher-level failure."""
        request = self.request_id(p)
        if request is None: return
        action = p.get("action", "list")
        safe_action = action if type(action) is str and action in ACTIONS else "invalid"
        digest, result = self._pending.pop(request, (None, {"event": "preset_result", "protocol": 1,
            "request_id": request, "action": safe_action, "document_id": self.document_identity(p),
            "success": False, "outcome_unknown": False}))
        if dispatch_error and not result.get("replayed"):
            result.update(success=False, outcome_unknown=bool(result.get("success") or result.get("outcome_unknown")),
                          error_code="dispatch_failed", error=dispatch_error[:2000])
        if result.get("success") and result["action"] == "apply" and not result.get("replayed"):
            try: result["doc_state"] = self.ports.status()
            except Exception as error:
                result.update(success=False, outcome_unknown=True, error_code="state_confirmation_failed", error=str(error)[:2000])
        from .custom_lut_scope import public_view
        result = public_view(result)
        # Compact acknowledgment identities survive failures and bounded receipt
        # fallbacks. A replay never gains a new token or fresh image approval.
        scalar_keys=('torso_review_ack','waist_review_ack','head_review_ack')
        scalar_scope=any(op in result.get('module_scope',[]) for op in (SC.TORSO_LENGTH.OP,SC.WAIST_LENGTH.OP,SC.HEAD_SIZE.OP))
        review_fields = {key: deepcopy(result[key]) for key in ('module_scope', 'preflight_token', *scalar_keys)
                         if key in result} if any(key in result for key in scalar_keys) or scalar_scope else {}
        try:
            json.dumps(result, allow_nan=False, ensure_ascii=False).encode("utf-8")
            raw = json.dumps(result, allow_nan=False, ensure_ascii=True)
        except (TypeError, ValueError, OverflowError, UnicodeError):
            unknown = bool(result.get("success") or result.get("outcome_unknown"))
            result = {"event": "preset_result", "protocol": 1, "request_id": request, "action": safe_action,
                      "document_id": self.document_identity(p), "success": False, "outcome_unknown": unknown,
                      "error_code": "invalid_receipt", "error": "无法序列化预设结果，请检查实际状态", **review_fields}
            raw = json.dumps(result)
        size = len(raw.encode()) + 1  # server.emit uses ASCII escaping plus a newline.
        if size > MAX_RESULT_BYTES:
            unknown = bool(result.get("success") or result.get("outcome_unknown")) and result["action"] != "list"
            result = {"event": "preset_result", "protocol": 1, "request_id": request, "action": result["action"],
                      "document_id": self.document_identity(p), "success": False, "outcome_unknown": unknown, "error_code": "receipt_too_large",
                      "error": "预设结果超过容量限制，请检查实际状态，不要重复提交", **review_fields}
            size = len(json.dumps(result).encode()) + 1
        if digest is not None and request not in self._receipts:
            self._receipts[request] = (digest, deepcopy(result), size)
            while len(self._receipts) > MAX_RECEIPTS or sum(v[2] for v in self._receipts.values()) > MAX_CACHE_BYTES:
                self._receipts.popitem(last=False)
        self.emit(result)

    def apply(self, p):
        self._scalar_receipt = {}
        pid = str(p.get("id") or "")
        if not pid: raise SC.ScopeError("preset apply 需要 id")
        reviewed_row=self.ports.target_row()
        reviewed_identity=(reviewed_row.get('document_id'),reviewed_row.get('path'),self.ports.document_id())
        reviewed_revision=self.ports.revision()
        previous = self.ports.capture()
        source_proof = None
        scalar_acks={key:p[key] for key in ('torso_review_ack','waist_review_ack','head_review_ack') if key in p}
        if scalar_acks and (len(scalar_acks)!=1 or any(key in p for key in ('xmp_review_ack','spill_review_ack','shadow_review_ack'))):
            raise SC.ScopeError('身体长度审核确认不能与其他目标图审核确认混用')
        if p.get('preflight_token') is not None:
            pending=self.reviews.pending.get(p['preflight_token']) if type(p['preflight_token']) is str else None
            selected=BODY_REVIEW.select(pending['modules']) if pending is not None else None
            if selected is not None and selected.port_name in ('waist','head') and getattr(self.ports,selected.port_name+'_history_identity') is None:
                raise SC.ScopeError('身体参数预设缺少当前完整人物身份审核端口')
            spill_ack={'spill_review_ack':p['spill_review_ack']} if 'spill_review_ack' in p else {}
            shadow_ack={'shadow_review_ack':p['shadow_review_ack']} if 'shadow_review_ack' in p else {}
            record = self.reviews.claim(p['preflight_token'], pid, previous, reviewed_row,
                                       reviewed_identity[2], reviewed_revision, self.ports.verify_crop, self.ports.verify_xmp, p.get("xmp_review_ack"),
                                       self.ports.verify_spill, verify_shadow=self.ports.verify_shadow,
                                       verify_torso=self.ports.verify_torso, verify_waist=self.ports.verify_waist, verify_head=self.ports.verify_head,
                                       **spill_ack, **shadow_ack, **scalar_acks)
            doc, mods = record['preset'], record['modules']
            source_proof = record.get('source_proof')
            family=BODY_REVIEW.select(mods)
            if family is not None:
                # Echo only an acknowledgment accepted by the frozen review.
                # Invalid/missing acks remain correctable pre-mutation rejections.
                self._scalar_receipt = {'module_scope':list(mods), 'preflight_token':p['preflight_token'],
                                       family.ack_key:deepcopy(p[family.ack_key])}
        else:
            doc = PS.find(pid); mods = doc['modules']
            mods = DERIVED.require_modules(previous, mods)
            family=BODY_REVIEW.select(mods)
            if doc.get("xmp_import") is not None: raise SC.ScopeError("XMP adaptation requires current target-image review before apply")
            if p.get("xmp_review_ack") is not None: raise SC.ScopeError("Unexpected XMP review acknowledgment")
            if "spill_review_ack" in p: raise SC.ScopeError('祛染色目标图审核确认必须属于当前冻结预检')
            if "shadow_review_ack" in p: raise SC.ScopeError('原图阴影目标图审核确认必须属于当前冻结预检')
            if scalar_acks: raise SC.ScopeError('身体长度目标图审核确认必须属于当前冻结预检')
            if family is not None or SC.ORIGINAL_SHADOW.OP in mods or SC.SPILL_REMOVAL.OP in mods or LG.OP in mods or OA.OP in mods or RC.OP in mods or SC.OP_CROP in mods: raise SC.ScopeError('含目标审核模块的预设必须先查看本目标预检，再确认应用')
            if SOURCE.record(previous) is not None:
                source_proof = SOURCE.row_proof({**self.ports.target_row(), 'state':previous})
        DERIVED.require_modules(previous, mods, source_proof)
        ops = list(mods)
        if SC.SPILL_REMOVAL.OP not in ops and "spill_review_ack" in p:
            raise SC.ScopeError('未选择祛染色模块，不能附带目标图审核确认')
        if SC.ORIGINAL_SHADOW.OP not in ops and "shadow_review_ack" in p:
            raise SC.ScopeError('未选择原图阴影模块，不能附带目标图审核确认')
        if any(family is None or key!=family.ack_key for key in scalar_acks):
            raise SC.ScopeError('未选择对应身体长度模块，不能附带目标图审核确认')
        verify_scalar=getattr(self.ports,'verify_'+family.port_name) if family is not None else None
        for op in ops:
            if SC.MODULES[op]["single_face"]:
                verdict, reason = self.ports.face_check()
                if verdict != "ok": raise SC.ScopeError(f"{op} 不能作用在这张图上：{reason}")
        before = OA.before_params(previous, ops)
        state = OA.candidate(previous, mods, local_replace_legacy=bool(p.get('preflight_token') and record['transfer'] and record['transfer']['legacy_removed']))
        if OA.OP in ops:
            state['_optics']=OA.verify_target(record['optics'],previous,state,self.ports.target_row(),self.ports.document_id(),self.ports.revision(),mods[OA.OP])
        if RC.OP in ops:
            recipe=RC.verify_target(record['reference'],previous,state,self.ports.target_row(),self.ports.document_id(),self.ports.revision(),mods[RC.OP])
            RC.apply_verified(state,recipe)
        if SC.SPILL_REMOVAL.OP in ops:
            row=self.ports.target_row()
            SC.SPILL_REMOVAL.validate_target(state,row["path"],(row["src_h"],row["src_w"]))
        if SC.ORIGINAL_SHADOW.OP in ops:
            row=self.ports.target_row()
            SC.ORIGINAL_SHADOW.validate_target(state,row["path"],(row["src_h"],row["src_w"]))
        if family is not None:
            row=self.ports.target_row()
            family.scope.validate_target(state,row["path"],(row["src_h"],row["src_w"]))
        if ID_BACKGROUND.OP in ops:
            row=self.ports.target_row()
            ID_BACKGROUND.validate_target(state,row["path"],(row["src_h"],row["src_w"]))
        if SKY.OP in ops:
            row=self.ports.target_row()
            SKY.validate_target(state["_sky_replacement"],row["path"],(row["src_h"],row["src_w"]))
        if BROW.OP in ops and OA.OP not in ops: BROW.validate_target(state,self.ports.target_row())
        if NOSE.OP in ops and OA.OP not in ops: NOSE.validate_target(state,self.ports.target_row())
        if EYE.OP in ops and OA.OP not in ops: EYE.validate_target(state,self.ports.target_row())
        if MOUTH.OP in ops and OA.OP not in ops: MOUTH.validate_target(state,self.ports.target_row())
        DERIVED.require_candidate(previous, state, mods, source_proof)
        if SC.OP_CROP in ops:
            if self.ports.verify_crop is None:raise SC.ScopeError('裁剪预设缺少完整目标审核端口')
            self.ports.verify_crop(self.ports.target_row(),state,self.ports.document_id(),self.ports.revision(),record.get('crop'))
        if SC.SPILL_REMOVAL.OP in ops:
            if self.ports.verify_spill is None:raise SC.ScopeError('祛染色预设缺少完整目标前后图审核端口')
            self.ports.verify_spill(self.ports.target_row(),previous,state,self.ports.document_id(),str(self.ports.revision()),record.get('spill'))
        if SC.ORIGINAL_SHADOW.OP in ops:
            if self.ports.verify_shadow is None:raise SC.ScopeError('原图阴影预设缺少完整目标前后图审核端口')
            self.ports.verify_shadow(self.ports.target_row(),previous,state,self.ports.document_id(),str(self.ports.revision()),record.get('shadow'))
        if family is not None:
            if verify_scalar is None:raise SC.ScopeError('身体长度预设缺少完整目标前后图审核端口')
            verify_scalar(self.ports.target_row(),previous,state,self.ports.document_id(),str(self.ports.revision()),record.get(family.preset_key))
            history_scalar=getattr(self.ports,family.port_name+'_history_identity')
            if family.port_name in ('waist','head') and history_scalar is None:
                raise SC.ScopeError('身体参数预设缺少当前完整人物身份审核端口')
        if source_proof is not None:
            SOURCE.verify_row({**self.ports.target_row(), 'state':self.ports.capture()}, source_proof)
        if family is not None:
            current=self.ports.target_row()
            if (current is not reviewed_row
                    or (current.get('document_id'),current.get('path'),self.ports.document_id())!=reviewed_identity
                    or self.ports.revision()!=reviewed_revision):
                raise SC.ScopeError('身体长度目标在冻结审核期间发生变化，未写入照片')
        def verify_after():
            current=self.ports.target_row()
            if ((family is not None and current is not reviewed_row)
                    or (current.get('document_id'),current.get('path'),self.ports.document_id())!=reviewed_identity):
                raise SC.ScopeError('预设渲染期间目标文档发生变化')
            if self.ports.revision()!=published_revision:raise SC.ScopeError('预设渲染期间目标版本发生变化')
            if source_proof is not None:SOURCE.verify_row({**current,'state':self.ports.capture()},source_proof)
            if SC.SPILL_REMOVAL.OP in ops:
                actual=self.ports.capture()
                if SC.SPILL_REMOVAL.undo_key(actual) != SC.SPILL_REMOVAL.undo_key(state):
                    raise SC.ScopeError('祛反光目标依赖在重放期间变化')
                proof=deepcopy(record['spill']);proof['revision']=str(published_revision)
                self.ports.verify_spill(current,previous,actual,self.ports.document_id(),str(published_revision),proof)
            if SC.ORIGINAL_SHADOW.OP in ops:
                actual=self.ports.capture()
                if SC.ORIGINAL_SHADOW.undo_key(actual) != SC.ORIGINAL_SHADOW.undo_key(state):
                    raise SC.ScopeError('原图阴影目标依赖在重放期间变化')
                proof=deepcopy(record['shadow']);proof['revision']=str(published_revision)
                self.ports.verify_shadow(current,previous,actual,self.ports.document_id(),str(published_revision),proof)
            if family is not None:
                actual=self.ports.capture()
                if family.scope.undo_key(actual) != family.scope.undo_key(state):
                    raise SC.ScopeError('身体长度目标依赖在重放期间变化')
                proof=deepcopy(record[family.preset_key]);proof['revision']=str(published_revision)
                verify_scalar(current,previous,actual,self.ports.document_id(),str(published_revision),proof)
            if SC.OP_CROP in ops:
                proof=deepcopy(record['crop']);proof['revision']=str(published_revision)
                self.ports.verify_crop(current,state,self.ports.document_id(),str(published_revision),proof)
            if doc.get('xmp_import') is not None:
                proof=deepcopy(record['xmp']);proof['revision']=str(published_revision)
                self.ports.verify_xmp(current,previous,self.ports.capture(),self.ports.document_id(),str(published_revision),doc['xmp_import']['source_sha256'],proof)
        if p.get('preflight_token') is not None:self.ports.advance()
        def verify_rollback():
            current=self.ports.target_row()
            if ((family is not None and current is not reviewed_row)
                    or (current.get('document_id'),current.get('path'),self.ports.document_id())!=reviewed_identity):
                raise SC.ScopeError('预设失败后目标已切换，无法确认回滚')
            rollback_revision=str(self.ports.revision())
            if SC.ORIGINAL_SHADOW.OP in ops:
                from .original_shadow_transfer_review import rollback_record
                prior=rollback_record(record['shadow'],previous,rollback_revision)
                self.ports.verify_shadow(current,previous,self.ports.capture(),self.ports.document_id(),rollback_revision,prior)
            if SC.SPILL_REMOVAL.OP in ops:
                from .spill_transfer_review import rollback_record
                prior=rollback_record(record['spill'],previous,rollback_revision)
                self.ports.verify_spill(current,previous,self.ports.capture(),self.ports.document_id(),rollback_revision,prior)
            if family is not None:
                prior=family.review.rollback_record(record[family.preset_key],previous,rollback_revision)
                verify_scalar(current,previous,self.ports.capture(),self.ports.document_id(),rollback_revision,prior)
        published_revision=self.ports.revision()
        self._effect_started = True
        scalar_write_started=False
        def replay_scalar(value, **kwargs):
            nonlocal scalar_write_started
            # The generic transaction predates body scalar admission and only marks
            # its forward replay strict. Rollback must use the same full gate.
            if kwargs.get('mode')=='preset_rollback' and not scalar_write_started:
                raise SC.ScopeError('身体长度尚未写入，拒绝用旧快照覆盖已变化的目标')
            current=self.ports.target_row()
            if (current is not reviewed_row
                    or (current.get('document_id'),current.get('path'),self.ports.document_id()) != reviewed_identity
                    or self.ports.revision() != published_revision):
                raise SC.ScopeError('身体长度重放目标或版本已变化，不能写入或回滚到另一目标')
            actual=self.ports.capture()
            SOURCE.verify_row({**current,'state':actual},source_proof)
            if (kwargs.get('mode')=='preset_rollback'
                    and family.scope.undo_key(actual) not in (family.scope.undo_key(previous),family.scope.undo_key(state))):
                raise SC.ScopeError('身体长度失败后支持、审核或其他身体操作已改变，拒绝覆盖当前依赖')
            if history_scalar is not None:
                identity=history_scalar(current,actual,self.ports.document_id(),str(published_revision))
                frozen=record[family.preset_key]
                if (type(identity) is not dict or set(identity)!=family.review.IDENTITY_FIELDS
                        or identity['document_id']!=reviewed_identity[2]
                        or identity['revision']!=str(published_revision)
                        or identity['source_proof']!=source_proof
                        or identity['people_sha256']!=frozen['before_people_sha256']
                        or (kwargs.get('mode')=='preset' and identity['candidate_sha256']!=frozen['before_sha256'])):
                    raise SC.ScopeError('身体长度重放前的完整照片或人物上下文已变化，未写入或覆盖回滚')
            else:
                # Legacy torso hosts still have the full verifier. Recheck its
                # frozen people proof before a write, not after stale state has
                # already been installed. Waist/head admission requires its explicit
                # current-state identity port above and cannot use this fallback.
                proof=deepcopy(record[family.preset_key]);proof['revision']=str(published_revision)
                if kwargs.get('mode')=='preset_rollback':
                    proof=family.review.rollback_record(proof,previous,published_revision)
                    verify_scalar(current,previous,value,self.ports.document_id(),str(published_revision),proof)
                else:
                    verify_scalar(current,actual,value,self.ports.document_id(),str(published_revision),proof)
            # Read-only ports must not rebase this write onto a newly selected
            # row or newly observed revision. Recheck after their callbacks.
            latest=self.ports.target_row()
            if (latest is not reviewed_row
                    or (latest.get('document_id'),latest.get('path'),self.ports.document_id())!=reviewed_identity
                    or self.ports.revision()!=published_revision):
                raise SC.ScopeError('身体长度写入前的最后目标围栏已变化')
            live=self.ports.capture()
            SOURCE.verify_row({**latest,'state':live},source_proof)
            from .optics_candidate_identity import fingerprint
            if fingerprint(live)!=fingerprint(actual):
                raise SC.ScopeError('身体长度身份审核期间当前配方发生变化，拒绝写入')
            if history_scalar is not None:
                # People may live outside capture(); a second current identity
                # closes drift introduced during the first read-only callback.
                if (identity['candidate_sha256']!=fingerprint(actual)
                        or history_scalar(latest,live,self.ports.document_id(),str(published_revision))!=identity):
                    raise SC.ScopeError('身体长度写入前完整人物上下文再次发生变化')
            else:
                verify_scalar(latest,previous if kwargs.get('mode')=='preset_rollback' else live,
                              value,self.ports.document_id(),str(published_revision),proof)
            final_row=self.ports.target_row()
            if (final_row is not reviewed_row
                    or (final_row.get('document_id'),final_row.get('path'),self.ports.document_id())!=reviewed_identity
                    or self.ports.revision()!=published_revision):
                raise SC.ScopeError('身体长度最终审核回调改变了写入目标')
            final_state=self.ports.capture()
            SOURCE.verify_row({**final_row,'state':final_state},source_proof)
            if fingerprint(final_state)!=fingerprint(actual):
                raise SC.ScopeError('身体长度最终审核回调改变了当前配方')
            if kwargs.get('mode')=='preset':scalar_write_started=True
            return self.ports.replay(value, **{**kwargs, 'strict_local':True})
        frame = apply_with_rollback(replay_scalar if family is not None else self.ports.replay, previous, state, preset_id=pid,
                                    emit=self.emit, invalidate=self.ports.invalidate, verify_after=verify_after if source_proof is not None or family is not None or SC.ORIGINAL_SHADOW.OP in ops or SC.SPILL_REMOVAL.OP in ops or SC.OP_CROP in ops or doc.get("xmp_import") is not None else None,
                                    verify_rollback=verify_rollback if family is not None or SC.ORIGINAL_SHADOW.OP in ops or SC.SPILL_REMOVAL.OP in ops else None,
                                    strict_local=family is not None or SC.ORIGINAL_SHADOW.OP in ops or SC.SPILL_REMOVAL.OP in ops or doc.get("xmp_import") is not None or SC.OP_CROP in ops or SOURCE.record(state) is not None or ID_BACKGROUND.OP in ops or LG.OP in ops or SKY.OP in ops or OA.OP in ops or BROW.OP in ops or NOSE.OP in ops or EYE.OP in ops or MOUTH.OP in ops or RC.OP in ops)
        after = OA.before_params(state, ops)
        self.last = {"id": pid, "name": doc["name"], "ops": ops, "params": after}
        render_ms = frame.pop("render_ms")
        self.emit({"event": "preset_applied", "id": pid, "kind": doc["kind"], "name": doc["name"],
                   "modules": ops, "before": before, "after": after, "render_ms": render_ms, "doc_state": self.ports.status()})
        self.emit(frame)
        return {"id": pid, "name": doc["name"], "module_scope": ops, "before": before, "after": after,
                "document_id": self.ports.document_id(), "preflight_token":p.get('preflight_token'),
                "source_proof":source_proof,
                **({family.ack_key:deepcopy(p[family.ack_key])} if family is not None else {})}

    def save(self, p):
        requested = p.get("module_scope")
        ops = SC.check_scope([op for op in SC.transferable_ops() if op not in (OA.OP,RC.OP,SC.SPILL_REMOVAL.OP,SC.TORSO_LENGTH.OP,SC.WAIST_LENGTH.OP,SC.HEAD_SIZE.OP,SC.COLLARBONE.OP)] if requested is None else requested)
        state = self.ports.capture()
        if SOURCE.record(state) is not None and set(ops) - SC.DERIVED_PARAMETER_OPS:
            raise SC.ScopeError('合成来源只能通过通用预设保存明确选择的全局参数模块')
        mods = DERIVED.require_modules(state, SC.params_of(state, ops))
        if SC.CUSTOM_LUT.OP in mods:
            mods[SC.CUSTOM_LUT.OP] = SC.CUSTOM_LUT.portable(mods[SC.CUSTOM_LUT.OP])
        if SKY.OP in mods and mods[SKY.OP]["recipe"]["enabled"]:
            from .sky_replacement_assets import verify
            verify(mods[SKY.OP]["recipe"]["asset"])
        if LG.OP in mods:
            policy = LG.options(p.get('local_mask_transfer'))
            chosen, _ = LG.choose(mods[LG.OP]['groups'], policy)
            if not chosen: raise SC.ScopeError('所选类型没有可保存的局部调色组')
            mods[LG.OP] = {'groups': LG.portable({'version':1,'layers':chosen})}
            from .local_grade_runtime import verify_original
            verify_original(mods[LG.OP]['groups'], self.ports.target_row())
        elif p.get('local_mask_transfer') is not None: raise SC.ScopeError('未选择独立局部调色模块，不能附带蒙版迁移选项')
        doc = {"schema": SC.PRESET_SCHEMA, "id": p.get("id") or "", "name": p.get("name") or str(p.get("id") or ""),
               "kind": p.get("kind") or "custom", "note": p.get("note") or "", "modules": mods}
        clean = SC.validate_preset(doc); self._effect_started = True
        saved = PS.save(clean, force=bool(p.get("force")))
        self.emit({"event": "preset_saved", "preset": clean, "path": saved})
        return {"preset": clean, "id": clean["id"], "path": saved, "module_scope": ops, "document_id": self.ports.document_id()}
