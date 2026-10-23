"""One-shot source patches: pre-fence capture proof and post-history receipts."""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable

from .repair_record import RepairOp, check_repair_fields
from .white_balance_controller import identity, error_text

PROOF_KEYS = ("document_id", "capture_id", "ticket", "generation", "recipe_document_id", "recipe_revision")
CLONE_KEYS = {"cmd", "action", "request_id", "kind", "stroke", *PROOF_KEYS}
COMMAND_KEYS = {"cmd", "action", "request_id", "polygon", "offset", *PROOF_KEYS}


@dataclass(frozen=True)
class SourcePatchPorts:
    guard: Callable[[], str | None]
    document_id: Callable[[], str]
    prepare_proof: Callable[[dict], dict]
    apply: Callable[[dict], dict]
    status: Callable[[], dict]
    needs_reload: Callable[[], bool]


class SourcePatchApplyError(ValueError):
    def __init__(self, message, *, rolled_back):
        super().__init__(message)
        self.rolled_back = rolled_back


class SourcePatchController:
    def __init__(self, ports, emit):
        self.ports, self.emit = ports, emit
        self.pending = None
        self.cache = OrderedDict()

    @staticmethod
    def _digest(p):
        raw = json.dumps(p, sort_keys=True, allow_nan=False, ensure_ascii=False).encode("utf-8")
        if len(raw) > 65536:
            raise ValueError("Source-patch request exceeds 64 KiB")
        return sha256(raw).hexdigest()

    def prepare(self, p):
        """Called BEFORE mutation fencing/invalidation; own a single-use proof."""
        result = {"event": "source_patch_result", "protocol": 1, "action": "apply",
                  "request_id": identity(p.get("request_id"), 128),
                  **{key: identity(p.get(key), 128) for key in PROOF_KEYS},
                  "success": False, "outcome_unknown": False, "requires_reload": False, "error": None}
        pending = self.pending = {"result": result, "digest": None, "proof": None, "started": False}
        try:
            kind = "clone_stamp" if p.get("cmd") == "clone_stamp" else "source_patch"
            keys = CLONE_KEYS if kind == "clone_stamp" else COMMAND_KEYS
            if (p.get("cmd") not in ("source_patch", "clone_stamp") or p.get("action") != "apply"
                    or set(p) != keys or (kind == "clone_stamp" and p.get("kind") != kind)):
                raise ValueError("Invalid source-patch action or fields")
            if result["request_id"] is None or any(result[key] is None for key in PROOF_KEYS):
                raise ValueError("Invalid source-patch request identity")
            digest = pending["digest"] = self._digest(p)
            if result["request_id"] in self.cache:
                old_digest, cached = self.cache[result["request_id"]]
                if old_digest != digest:
                    raise ValueError("Source-patch request ID reused with different parameters")
                pending["result"] = {**deepcopy(cached), "replayed": True}
                return False
            if p["document_id"] != self.ports.document_id():
                raise ValueError("Photo changed; source patch was not applied")
            reason = self.ports.guard()
            if reason:
                raise ValueError(reason)
            proof = self.ports.prepare_proof(p)
            if type(proof) is not dict or any(proof.get(key) != p[key] for key in PROOF_KEYS):
                raise ValueError("Source-patch capture proof does not match the request")
            if proof.get("kind", "source_patch") != kind:
                raise ValueError("Repair capture proof kind does not match request")
            result["kind"] = kind
            clean = check_repair_fields({"op_id": 0, "kind": kind,
                                        "weight": proof.get("weight"), "params": proof.get("params"),
                                        "source_binding": proof.get("source_binding")})
            # No borrowed mutable coordinates or coverage survive capture invalidation.
            pending["proof"] = {**{key: proof[key] for key in PROOF_KEYS},
                                "params": clean["params"], "weight": clean["weight"].copy(), "kind": kind}
            if clean.get("source_binding") is not None:
                from .creative_derived_repair_commands import INTERNAL_KEYS
                pending["proof"].update({key:deepcopy(proof.get(key)) for key in INTERNAL_KEYS})
            h, w = clean["weight"].shape
            dx, dy = clean["params"]["offset"]
            if (dx == 0 and dy == 0) or (kind == "clone_stamp" and clean["params"]["opacity"] == 0):
                count = self.ports.status()["counts"]["repair"]
                if type(count) is not int or count < 0:
                    raise ValueError("Invalid repair operation count")
                result.update(success=True, no_change=True, op_id=None, before_count=count, after_count=count)
                pending["proof"] = None
                return False
            return True
        except Exception as error:
            result["error"] = error_text(error)
            self.emit({"event": "error", "error": result["error"]})
            return False

    def handle(self, p):
        pending = self.pending
        if pending is None or pending["proof"] is None or pending["digest"] != self._digest(p):
            raise ValueError("Source patch must be prepared before the document mutation fence")
        result = pending["result"]
        proof, pending["proof"] = pending["proof"], None
        try:
            pending["started"] = True
            evidence = self.ports.apply(proof)
            result.update(success=True, no_change=False, **evidence)
        except Exception as error:
            rolled_back = isinstance(error, SourcePatchApplyError) and error.rolled_back
            result.update(error=error_text(error), outcome_unknown=not rolled_back,
                          requires_reload=self.ports.needs_reload())
            self.emit({"event": "error", "error": result["error"]})

    def finish(self, p, dispatch_error=None):
        """Only the dispatcher calls this, after its normal history transaction."""
        pending, self.pending = self.pending, None
        if pending is None:
            result = {"event": "source_patch_result", "protocol": 1, "action": "apply",
                      "request_id": identity(p.get("request_id"), 128),
                      **{key: identity(p.get(key), 128) for key in PROOF_KEYS},
                      "success": False, "outcome_unknown": False,
                      "requires_reload": self.ports.needs_reload(),
                      "error": error_text(dispatch_error or "Source patch produced no prepared outcome")}
            digest = None
        else:
            result, digest = pending["result"], pending["digest"]
        if dispatch_error:
            result.update(success=False, outcome_unknown=bool(pending and pending["started"]),
                          requires_reload=self.ports.needs_reload(), error=error_text(dispatch_error))
        if result["success"] and not result.get("replayed"):
            try:
                status = self.ports.status()
                if status["document_id"] != result["document_id"]:
                    raise ValueError("Photo changed before the source-patch receipt")
                result["history"] = {key: status["history"][key] for key in ("undo_steps", "redo_steps")}
                result["counts"] = deepcopy(status.get("counts", {}))
            except Exception as error:
                result.update(success=False, outcome_unknown=bool(pending and pending["started"]),
                              error=error_text(error))
        try:
            bounded = len(json.dumps(result, allow_nan=False).encode("utf-8")) <= 16384
        except (ValueError, TypeError, UnicodeError):
            bounded = False
        if not bounded:
            result = {key: result.get(key) for key in ("event", "protocol", "action", "request_id", *PROOF_KEYS)}
            result.update(success=False, outcome_unknown=bool(pending and pending["started"]),
                          requires_reload=self.ports.needs_reload(), error="Source-patch receipt exceeded its bound")
        rid = result.get("request_id")
        if rid and digest and rid not in self.cache:
            self.cache[rid] = (digest, deepcopy(result))
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
        self.emit(result)


def apply_to_engine(engine, proof, emit):
    """Repair-local transaction; failed display publication restores the old recipe."""
    pipe = engine._vram
    previous = (engine._repair_ops, engine._redo_ops, engine._op_seq)
    # Replay allocates new repair tensors and cache entries. Preserve the prior
    # references rather than quantizing pixels or rebuilding from a display frame.
    pipeline_before = dict(vars(pipe))
    committed = False
    try:
        from .creative_derived_source import record
        if record(engine) is not None or proof.get("source_binding") is not None:
            from .creative_derived_repair_commands import verify_state
            verify_state(engine,proof)
        op = RepairOp(engine._op_seq + 1, proof["weight"], proof["params"], proof.get("kind", "source_patch"),
                      source_binding=deepcopy(proof.get("source_binding")))
        info = pipe.add_repair(op)
        committed = True
        engine._repair_ops, engine._redo_ops = list(pipe.repair_ops), list(pipe.redo_ops)
        engine._op_seq = op.op_id
        frame = engine._write_current_frame(op.kind)
        frame["doc_state"] = engine.doc_state()
        emit(frame)
        return {"op_id": op.op_id, "kind": op.kind, "recipe_version": op.params["version"],
                "applied": info["applied"], "repair_ms": info["repair_ms"],
                "before_count": len(previous[0]), "after_count": len(engine._repair_ops)}
    except Exception as error:
        engine._repair_ops, engine._redo_ops, engine._op_seq = previous
        if not committed:
            raise SourcePatchApplyError(f"Source patch rejected without changing the recipe: {error}", rolled_back=True) from error
        vars(pipe).clear()
        vars(pipe).update(pipeline_before)
        try:
            rollback = engine._write_current_frame("source_patch_rollback")
            rollback["doc_state"] = engine.doc_state()
            emit(rollback)
        except Exception as rollback_error:
            engine._vram = None
            raise SourcePatchApplyError(f"Source-patch recipe restored but frame recovery failed; reopen the photo: {rollback_error}",
                                        rolled_back=False) from error
        raise SourcePatchApplyError(f"Source patch failed; the previous recipe and frame were restored: {error}", rolled_back=True) from error


def get_controller(engine, emit):
    owner = engine.__dict__.get("_source_patch_owner")
    if owner is None:
        from .source_patch_capture import make_controller
        capture = make_controller(engine, emit)
        owner = SourcePatchController(SourcePatchPorts(
            guard=lambda: engine._guard_editable("source patch"), document_id=lambda: engine._load_id,
            prepare_proof=capture.prepare_apply, apply=lambda proof: apply_to_engine(engine, proof, emit),
            status=lambda: engine.doc_state(), needs_reload=lambda: engine._vram is None), emit)
        owner.capture = capture
        engine._source_patch_owner = owner
    return owner
