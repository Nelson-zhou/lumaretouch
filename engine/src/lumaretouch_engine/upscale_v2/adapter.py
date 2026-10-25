"""Fail-closed public adapter, deliberately without a production load path.

Neither a path, an environment SHA, an editable manifest nor a caller boolean
can turn on this backend. Completing admission requires a separately reviewed
source change, safe loader, bounded executor, measured resource envelope and
real acceptance evidence. This module performs no filesystem/network probing.
"""

from dataclasses import dataclass
from typing import NoReturn

from .architecture import CONTRACT_VERSION, architecture_for


@dataclass(frozen=True)
class BackendCapability:
    model_id: str
    contract: str
    available: bool
    state: str
    blockers: tuple[str, ...]
    network_scale: int
    output_mode: str = "restore_native_dimensions"
    installation_verified: bool = False
    inference_run: bool = False


class BackendUnavailable(RuntimeError):
    def __init__(self, status: BackendCapability):
        self.status = status
        super().__init__("AI clarity backend unavailable: " + "; ".join(status.blockers))


def capability(model_id: str = "RealESRGAN_x2plus") -> BackendCapability:
    spec = architecture_for(model_id)
    return BackendCapability(
        model_id=spec.model_id, contract=CONTRACT_VERSION, available=False,
        state="source_contract_only_unavailable", network_scale=spec.scale,
        blockers=(
            "official_checkpoint_sha256_unestablished",
            "checkpoint_specific_license_review_pending",
            "authenticated_runtime_distribution_hashes_missing",
            "installed_code_config_integrity_admission_unimplemented",
            "safe_checkpoint_file_loader_unimplemented",
            "bounded_stream_production_reservation_and_admission_unimplemented",
            "device_workspace_and_host_resource_envelopes_unmeasured",
            "checkpoint_compatibility_numeric_tile_and_photo_acceptance_unrun",
        ),
    )


def restore_native_candidate(*, model_id: str = "RealESRGAN_x2plus", **request) -> NoReturn:
    """Always refuse before source consumption, optional imports or allocation.

The future request/receipt/transaction owner remains outside this adapter. Do
not infer a supported production request schema from ``request``: it is unused
and exists only to provide an explicit unavailable boundary for integration.
No identity/no-op/Lanczos/sharpen result is returned as a successful AI result.
"""
    raise BackendUnavailable(capability(model_id))
