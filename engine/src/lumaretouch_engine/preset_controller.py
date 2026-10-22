"""Module presets: validated operations and correlated, post-history receipts.

The dispatcher calls finish() after its history bookkeeping. Legacy events remain
available. Receipt replay is bounded to this engine session/cache; clients must
query an uncertain request, never automatically resubmit a mutation.
"""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable
from . import scope as SC, preset_store as PS
from .preset_transaction import apply_with_rollback, PresetApplyError
from . import local_grade_layers as LG
from . import sky_replacement_scope as SKY

ACTIONS = ("list", "preflight", "apply", "save", "import", "delete")
LEGACY_KEYS = {"cmd", "action", "id", "path", "modules", "module_scope", "name", "kind", "force", "note", "local_mask_transfer", "preflight_token"}
FIELDS = {"list": set(), "apply": {"id", "document_id", "preflight_token"},
          "preflight": {"id", "document_id", "local_mask_transfer"},
          "save": {"id", "name", "kind", "force", "note", "module_scope", "document_id", "local_mask_transfer"},
          "import": {"path", "id", "force"}, "delete": {"id"}}
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


class PresetController:
    def __init__(self, ports: PresetPorts, emit: Callable[[dict], None]):
        self.ports = ports; self.emit = emit; self.last = None
        self._receipts = OrderedDict(); self._pending = {}; self._effect_started = False
        from .local_grade_preset_review import PresetReviews
        self.reviews = PresetReviews()

    def last_applied(self):
        if not self.last: return None
        try: current = SC.params_of(self.ports.capture(), self.last["ops"])
        except Exception: return None
        return {"id": self.last["id"], "name": self.last["name"]} if current == self.last["params"] else None

    def state(self):
        available = True
        try: docs, errors = PS.list_all()
        except Exception as error:
            available = False; docs = []
            errors = [{"file": PS.preset_dir(), "error": f"读预设目录失败：{error}"}]
        return {"list": docs, "errors": errors, "modules": SC.describe(), "dir": PS.preset_dir(),
                "schema": SC.PRESET_SCHEMA, "last_applied": self.last_applied(), "available": available}

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
            for key in ({"id"} if action in ("apply", "preflight", "save", "delete") else {"path"} if action == "import" else set()):
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
        digest = None; self._effect_started = False
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
                for op in doc['modules']:
                    if SC.MODULES[op]['single_face']:
                        verdict, reason = self.ports.face_check()
                        if verdict != 'ok': raise SC.ScopeError(f'{op}：{reason}')
                evidence = self.reviews.prepare(doc, self.ports.capture(), self.ports.target_row(),
                    self.ports.document_id(), self.ports.revision(), p.get('local_mask_transfer'))
            elif action == "apply": evidence = self.apply(p)
            elif action == "save": evidence = self.save(p)
            elif action == "import":
                path = str(p.get("path") or "")
                if not path: raise SC.ScopeError("preset import 需要 path")
                doc = {k: v for k, v in PS.load_file(path).items() if k != "builtin"}
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
            if isinstance(error, PS.PresetStorageError):
                unknown = error.outcome_unknown
                result["operation_committed"] = error.committed
            result.update(error=str(error)[:2000], error_code="outcome_unknown" if unknown else "rejected", outcome_unknown=unknown)
            self.emit({"event": "error", "error": f"preset {action}：{error}"})
        finally:
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
        try:
            json.dumps(result, allow_nan=False, ensure_ascii=False).encode("utf-8")
            raw = json.dumps(result, allow_nan=False, ensure_ascii=True)
        except (TypeError, ValueError, OverflowError, UnicodeError):
            unknown = bool(result.get("success") or result.get("outcome_unknown"))
            result = {"event": "preset_result", "protocol": 1, "request_id": request, "action": safe_action,
                      "document_id": self.document_identity(p), "success": False, "outcome_unknown": unknown,
                      "error_code": "invalid_receipt", "error": "无法序列化预设结果，请检查实际状态"}
            raw = json.dumps(result)
        size = len(raw.encode()) + 1  # server.emit uses ASCII escaping plus a newline.
        if size > MAX_RESULT_BYTES:
            unknown = bool(result.get("success") or result.get("outcome_unknown")) and result["action"] != "list"
            result = {"event": "preset_result", "protocol": 1, "request_id": request, "action": result["action"],
                      "document_id": self.document_identity(p), "success": False, "outcome_unknown": unknown, "error_code": "receipt_too_large",
                      "error": "预设结果超过容量限制，请检查实际状态，不要重复提交"}
            size = len(json.dumps(result).encode()) + 1
        if digest is not None and request not in self._receipts:
            self._receipts[request] = (digest, deepcopy(result), size)
            while len(self._receipts) > MAX_RECEIPTS or sum(v[2] for v in self._receipts.values()) > MAX_CACHE_BYTES:
                self._receipts.popitem(last=False)
        self.emit(result)

    def apply(self, p):
        pid = str(p.get("id") or "")
        if not pid: raise SC.ScopeError("preset apply 需要 id")
        previous = self.ports.capture()
        if p.get('preflight_token') is not None:
            record = self.reviews.claim(p['preflight_token'], pid, previous, self.ports.target_row(),
                                       self.ports.document_id(), self.ports.revision())
            doc, mods = record['preset'], record['modules']
        else:
            doc = PS.find(pid); mods = doc['modules']
            if LG.OP in mods: raise SC.ScopeError('含独立局部调色的预设必须先查看目标预检，再确认应用')
        ops = list(mods)
        for op in ops:
            if SC.MODULES[op]["single_face"]:
                verdict, reason = self.ports.face_check()
                if verdict != "ok": raise SC.ScopeError(f"{op} 不能作用在这张图上：{reason}")
        before = SC.params_of(previous, ops)
        if p.get('preflight_token') is not None: self.ports.advance()
        state = SC.apply_modules(previous, mods, local_replace_legacy=bool(p.get('preflight_token') and record['transfer']['legacy_removed']))
        if SKY.OP in ops:
            row=self.ports.target_row()
            SKY.validate_target(state["_sky_replacement"],row["path"],(row["src_h"],row["src_w"]))
        self._effect_started = True
        frame = apply_with_rollback(self.ports.replay, previous, state, preset_id=pid,
                                    emit=self.emit, invalidate=self.ports.invalidate, strict_local=LG.OP in ops or SKY.OP in ops)
        after = SC.params_of(state, ops)
        self.last = {"id": pid, "name": doc["name"], "ops": ops, "params": after}
        render_ms = frame.pop("render_ms")
        self.emit({"event": "preset_applied", "id": pid, "kind": doc["kind"], "name": doc["name"],
                   "modules": ops, "before": before, "after": after, "render_ms": render_ms, "doc_state": self.ports.status()})
        self.emit(frame)
        return {"id": pid, "name": doc["name"], "module_scope": ops, "before": before, "after": after,
                "document_id": self.ports.document_id(), "preflight_token":p.get('preflight_token')}

    def save(self, p):
        requested = p.get("module_scope")
        ops = SC.check_scope(list(SC.transferable_ops()) if requested is None else requested)
        mods = SC.params_of(self.ports.capture(), ops)
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
