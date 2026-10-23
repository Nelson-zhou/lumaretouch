"""Server/task integration adapter, deliberately not registered before shared review.

Use after the existing edit barrier and per-document export snapshots are frozen.
No calls into rendering or mutable server document state exist in this module.
"""
from __future__ import annotations
import json
from pathlib import Path
from .export_destination_policy import DestinationError, freeze, restore, inspect_directory


class DestinationController:
    def __init__(self):
        self._preview = None

    def invalidate(self):
        self._preview = None

    def preview(self, sources, policy, settings, revision, *, protected_sources):
        self._preview = freeze(sources, policy, settings, revision, protected_sources=protected_sources)
        return self._preview.payload()

    def attach_to_task(self, task, plan_id, revision, frame_receipts):
        """Attach to T.new_task result BEFORE ledger persistence/thread startup.

        frame_receipts is authoritative item_id -> frozen receipt from server capture.
        The existing task's images/options/recipes remain untouched.
        """
        plan = self._preview
        if plan is None or plan.plan_id != plan_id or plan.intent_revision != revision:
            raise DestinationError("stale_destination_preview")
        if task.get("kind") != "export" or task.get("state") != "queued":
            raise DestinationError("destination_requires_queued_export")
        if any(e.disposition == "needs_confirmation" for e in plan.entries):
            raise DestinationError("destination_product_dialog_required")
        if {e.item_id: e.frame_receipt for e in plan.entries} != frame_receipts:
            raise DestinationError("destination_frames_changed")
        if set(task["inputs"].get("images", [])) != {e.source_path for e in plan.entries}:
            raise DestinationError("destination_batch_changed")
        # Bind options rather than merely retaining an informational copy.
        for key, value in json.loads(plan.settings_json).items():
            if task["inputs"].get(key) != value:
                raise DestinationError("destination_export_options_changed")
        task["inputs"]["destination_plan"] = plan.payload()
        self._preview = None

    @staticmethod
    def target_for_item(task, item_id, frame_receipt):
        """Called from BOTH RGB16 and 8-bit branches, also on session retry.

        Returns None for an explicitly skipped item; never select a fresh retry name.
        Restore on its own is not permission to render: existing recipe_persisted
        guard must still hold across process restarts.
        """
        plan = restore(task["inputs"]["destination_plan"])
        matches = [e for e in plan.entries if e.item_id == item_id]
        if len(matches) != 1 or matches[0].frame_receipt != frame_receipt:
            raise DestinationError("destination_item_frame_mismatch")
        entry = matches[0]
        if entry.disposition == "skip":
            return None
        if entry.disposition != "write":
            raise DestinationError("destination_product_dialog_required")
        source = Path(entry.source_path).stat()
        if (source.st_dev, source.st_ino, source.st_size, source.st_mtime_ns) != entry.source_stamp:
            raise DestinationError("destination_source_changed")
        inspect_directory(Path(entry.target).parent)
        # Existing target may be a successful prior commit with missing receipt.
        # Never overwrite it, silently mark success, or rename again on retry.
        if Path(entry.target).exists() or Path(entry.target).is_symlink():
            raise DestinationError("destination_retry_target_exists_review_required")
        return entry.target
