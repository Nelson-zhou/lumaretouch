"""JPEG target writer: freeze once, encode repeatedly, publish once without clobber."""
from io import BytesIO
from hashlib import sha256
import os
import time

from .export_target_size_search import search, EncodedBudgetExceeded, TargetSizeCancelled


class TargetSizeUnmet(ValueError):
    def __init__(self, receipt):
        self.target_size = {**receipt, "published": False}
        self.outputs = []
        super().__init__(f"近似目标大小未满足：{receipt['status']}；未写文件，最佳候选 {receipt['actual_bytes']} B")


class LimitedBuffer(BytesIO):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise EncodedBudgetExceeded("单次 JPEG 编码超过显式字节预算")
        return super().write(data)


def publish_no_clobber(path, data, *, policy, cancelled, frozen_target=False):
    """Adapt legacy collision policy to the single canonical dirfd publisher.

    Frozen destination-plan targets never rename, including retries. Cancellation
    after commit cannot undo a complete output. No replace() fallback exists.
    """
    from .export_destination_commit import commit_encoded_bytes, CommitFailure
    from . import export_destination_runtime as destination
    if destination.active():
        frozen_target = True
        resolved, reason = destination.resolve(path)
        if resolved is None:
            return {"path":path,"skipped":True,"bytes":0,"renamed_from":None,
                    "directory_fsync":False,"reason":reason}
        path = resolved
    if policy not in ("skip_and_report", "recheck"):
        raise ValueError("unknown collision policy")
    absolute = os.path.abspath(path)
    stem, ext = os.path.splitext(absolute)
    candidates = 10000 if policy == "recheck" and not frozen_target else 1
    for index in range(candidates):
        candidate = absolute if index == 0 else f"{stem}-{index:04d}{ext}"
        durable = True
        try:
            result = commit_encoded_bytes(candidate, data, create_missing=destination.create_missing(), cancelled=cancelled)
        except CommitFailure as error:
            if error.committed:
                result = {"path": error.target, "committed": True, "cancelled": False}
                durable = False
            elif isinstance(error.__cause__, FileExistsError) and not frozen_target:
                continue
            else:
                raise
        if result["cancelled"]:
            raise TargetSizeCancelled("提交前已取消；未写目标文件")
        if not result["committed"]:
            raise OSError("publisher returned neither committed nor cancelled")
        return {"path": result["path"], "skipped": False, "bytes": len(data),
                "renamed_from": None if index == 0 else path,
                "directory_fsync": durable,
                "reason": None if durable else "文件已提交；目录持久化同步未确认"}
    return {"path": path, "skipped": True, "bytes": 0, "renamed_from": None,
            "directory_fsync": False,
            "reason": "冻结目标已存在，未覆盖或改名" if frozen_target else "目标已存在；未覆盖，或唯一名称已耗尽"}


def write_target_size(rgb, path, *, target_size, output_profile="srgb", source_icc=None,
                      source_exif=None, metadata_include_gps=False,
                      conflict_policy="skip_and_report", cancelled=lambda: False, progress=None,
                      frozen_target=False):
    from .export import (_profile_bytes, _convert_srgb_to_profile, _filter_exif,
                         _icc_facts, QUALITY_MAPPING_VERSION, _check_policy)
    from .export_target_size_policy import parse_target_size, TargetSize
    import numpy as np
    from PIL import Image

    started = time.monotonic()
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    policy = parse_target_size(target_size.wire() if isinstance(target_size, TargetSize) else target_size,
                               format=ext, bit_depth=8)
    if policy is None:
        raise ValueError("target_size is required")
    _check_policy(conflict_policy)
    from . import export_destination_runtime as destination
    if destination.active():
        frozen_target = True
        resolved, reason = destination.resolve(path)
        if resolved is None:
            from .export_target_size_search import SearchResult
            receipt = SearchResult(None, None, "skipped", (), False).receipt(policy)
            receipt["published"] = False
            return {"path":path,"format":ext,"skipped":True,"bytes":0,"write_ms":0.0,
                    "quality":None,"encoder_quality":None,"target_size":receipt,
                    "quality_mapping_version":QUALITY_MAPPING_VERSION,"reason":reason,
                    "renamed_from":None,"directory_fsync":False}
        path = resolved
    if type(metadata_include_gps) is not bool:
        raise ValueError("metadata_include_gps must be boolean")
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("目标大小仅接收已完成修图的 RGB8；不自动降低位深/丢弃 alpha")
    height, width = rgb.shape[:2]
    if height < 1 or width < 1 or height*width > policy.max_pixels:
        raise ValueError("目标大小像素预算不足；请显式调整预算，不自动缩图")
    if cancelled():
        raise TargetSizeCancelled("已取消")
    # Detached image from immutable packed bytes: edits cannot race later attempts.
    # Source input is already rendered/cropped/upscaled by the existing worker.
    packed = np.ascontiguousarray(rgb).tobytes()
    pixel_digest = sha256(packed).hexdigest()
    image = Image.frombytes("RGB", (width, height), packed)
    del packed
    icc = _profile_bytes(output_profile, source_icc)
    intent = None
    if icc:
        image, intent = _convert_srgb_to_profile(image, icc)
    exif, exif_facts = _filter_exif(source_exif, metadata_include_gps)
    options = {"subsampling": 0}
    if icc:
        options["icc_profile"] = icc
    if exif:
        options["exif"] = exif

    def encode(quality):
        with LimitedBuffer(policy.max_encoded_bytes) as buffer:
            image.save(buffer, format="JPEG", quality=quality, **options)
            return buffer.getvalue()

    result = search(policy, encode, cancelled=cancelled, progress=progress)
    receipt = result.receipt(policy)
    receipt.update({"width": width, "height": height, "bit_depth": 8,
                    "subsampling": "4:4:4", "frozen_pixels_sha256": pixel_digest,
                    "metadata_included_in_measurement": True})
    if result.data is None or (result.status != "matched" and not policy.allow_best_effort):
        raise TargetSizeUnmet(receipt)
    # Validate the selected complete JPEG and embedded policy-critical metadata.
    # This is a single readback, not re-rendering or lossless-pixel equivalence.
    with Image.open(BytesIO(result.data)) as decoded:
        decoded.load()
        if decoded.format != "JPEG" or decoded.size != (width, height) or decoded.mode != "RGB":
            raise ValueError("JPEG 完整性/尺寸校验失败；未写文件")
        if decoded.info.get("icc_profile") != icc:
            raise ValueError("ICC 完整性校验失败；未写文件")
        if decoded.info.get("exif") != exif:
            raise ValueError("EXIF 完整性校验失败；未写文件")
        tags = decoded.getexif()
        if 274 in tags or (not metadata_include_gps and 34853 in tags):
            raise ValueError("JPEG 元数据隐私/方向校验失败；未写文件")
    publication = publish_no_clobber(path, result.data, policy=conflict_policy, cancelled=cancelled, frozen_target=frozen_target)
    receipt["published"] = not publication["skipped"]
    return {**publication, "format": ext, "write_ms": round((time.monotonic()-started)*1000, 1),
            "quality": result.quality, "encoder_quality": result.quality,
            "quality_mapping_version": QUALITY_MAPPING_VERSION, "target_size": receipt,
            "sha256": sha256(result.data).hexdigest(), "conflict_policy": conflict_policy,
            "icc_source": output_profile, "color_intent": intent,
            "color_converted": bool(icc and intent != "srgb_identity"),
            **_icc_facts(icc), **exif_facts, "exif_bytes": len(exif or b""),
            "compress_level": None, "tiff_compression": None,
            "integrity_readback": "jpeg_dimensions_rgb_icc_exif"}
