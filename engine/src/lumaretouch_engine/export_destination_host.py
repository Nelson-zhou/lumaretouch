"""Correlated command adapter for Engine.cmd_export_destination (pending registration)."""
from .export_destination_policy import DestinationError, Policy


def dispatch(controller, command, *, capture, emit):
    """capture(ids, options, revision) runs server's authoritative edit barrier and
    returns (Source records, frozen export options, all project original paths).
    This is a required host dependency, not a fallback to client-supplied paths.
    """
    request_id = command.get("request_id")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise DestinationError("invalid_destination_request_id")
    try:
        action = command.get("action")
        if action == "cancel":
            controller.invalidate()
            result = {"cancelled": True}
        elif action == "preview":
            if set(command) - {"cmd", "action", "request_id", "policy", "document_ids", "intent_revision", "export_options"}:
                raise DestinationError("unknown_destination_fields")
            sources, options, originals = capture(command["document_ids"], command["export_options"], command["intent_revision"])
            result = controller.preview(sources, Policy(**command["policy"]), options,
                                        command["intent_revision"], protected_sources=originals)
        else:
            raise DestinationError("unknown_destination_action")
        emit({"event": "export_destination_result", "request_id": request_id, "status": "ready", "value": result})
    except (ValueError, TypeError, KeyError, OSError) as exc:
        controller.invalidate()
        # Paths remain local; native mailbox must not forward these to telemetry.
        emit({"event": "export_destination_result", "request_id": request_id, "status": "failed", "error": str(exc)})
