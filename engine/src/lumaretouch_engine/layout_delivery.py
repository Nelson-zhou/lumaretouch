"""Compose frozen export outputs, preserving originals; no printer submission here."""
from __future__ import annotations
import io
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from PIL import Image, ImageCms, ImageOps
from .layout_spec import geometry, LAYOUT_ITEM


def compose(spec, records, out_dir, boundary, destination_plan=None):
    g = geometry(spec)
    sources = []
    for record in records:
        if record.get("state") != "succeeded" or not record.get("out") or record.get("layout_usable") is False:
            raise ValueError("排版需要本批每张图片实际成功出片；失败/跳过项目不能用旧文件替代")
        sources.extend([record["out"]] * spec["copies"])
    if not sources:
        raise ValueError("排版没有可用图片")
    count = math.ceil(len(sources) / len(g["cells"]))
    if count > 200:
        raise ValueError("单批排版最多 200 页，请分批导出")
    planned = {}
    if destination_plan:
        from .export_destination_policy import restore
        plan = restore(destination_plan)
        planned = {e.item_id.removeprefix('layout::'):e for e in plan.entries if e.item_id.startswith('layout::')}
        expected = {f'page-{i+1:04}.png' for i in range(count)} | {'layout.pdf','manifest.json'}
        if set(planned) != expected: raise ValueError('排版页数与冻结输出不一致')
        if any(e.disposition != 'write' for e in planned.values()): raise ValueError('排版目标被跳过或尚未确认')
        if any(os.path.lexists(e.target) for e in planned.values()): raise ValueError('排版冻结目标已存在；请核对已导出文件，重试不改名')
        destination = Path(planned['manifest.json'].target).parent
        stage = Path(tempfile.mkdtemp(prefix='.lrt-layout-'))
    else:
        root = Path(out_dir).resolve()
        stage = Path(tempfile.mkdtemp(prefix=".lrt-layout-", dir=root))
        destination = root / ("layout-" + uuid.uuid4().hex)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    profile_bytes = profile.tobytes()
    pages = []
    try:
        for index in range(count):
            if boundary() == "stop":
                raise InterruptedError("排版已取消；已导出的照片保持不变")
            page = Image.new("RGB", (g["width_px"], g["height_px"]), "white")
            try:
                for slot, path in enumerate(sources[index * len(g["cells"]):(index + 1) * len(g["cells"])]):
                    with Image.open(path) as source:
                        icc = source.info.get("icc_profile")
                        if not icc:
                            raise ValueError(f"出片缺少 ICC，拒绝猜测颜色空间：{path}")
                        rgb = ImageCms.profileToProfile(source.convert("RGB"),
                            ImageCms.ImageCmsProfile(io.BytesIO(icc)), profile, outputMode="RGB")
                        x0, y0, x1, y1 = g["cells"][slot]
                        size = (x1 - x0, y1 - y0)
                        placed = (ImageOps.fit(rgb, size, method=Image.Resampling.LANCZOS)
                                  if spec["fit"] == "cover" else
                                  ImageOps.contain(rgb, size, method=Image.Resampling.LANCZOS))
                        page.paste(placed, (x0 + (size[0] - placed.width) // 2,
                                            y0 + (size[1] - placed.height) // 2))
                        placed.close()
                        rgb.close()
                filename = f"page-{index + 1:04}.png"
                page.save(stage / filename, dpi=(spec["dpi"], spec["dpi"]), icc_profile=profile_bytes)
                # Append one closed page at a time; save_all retains decoded
                # image handles and can otherwise grow to many GB for albums.
                page.save(stage / "layout.pdf", append=bool(index),
                    dpi=(g["width_px"] * 25.4 / g["width_mm"], g["height_px"] * 25.4 / g["height_mm"]),
                    quality=100, subsampling=0, title="LumaRetouch photo layout")
                pages.append(filename)
            finally:
                page.close()
        if boundary() == "stop":
            raise InterruptedError("排版已取消；已导出的照片保持不变")
        manifest = {"schema": "lrt.layout.v1", "spec": spec, "page_count": count,
                    **{k: v for k, v in g.items() if k != "cells"}, "pages": pages,
                    "profile": "sRGB", "bits": 8, "pdf": "layout.pdf", "sources": sources}
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        for artifact in stage.iterdir():
            with artifact.open("rb") as handle:
                os.fsync(handle.fileno())
        directory_fd = os.open(stage, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        if planned:
            from .export_destination_commit import commit_encoded_bytes
            from .watermark_delivery import DeliveryError
            manifest['pages'] = [Path(planned[x].target).name for x in pages]
            manifest['pdf'] = Path(planned['layout.pdf'].target).name
            (stage / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            committed = []
            try:
                # Manifest last: partial publication cannot masquerade as a full sheet set.
                for filename in pages + ['layout.pdf','manifest.json']:
                    if boundary() == 'stop': raise InterruptedError('排版已取消；已提交页面保留')
                    result = commit_encoded_bytes(planned[filename].target, (stage/filename).read_bytes(),
                        create_missing=json.loads(plan.policy_json)['create_missing'])
                    committed.append({'path':result['path'], 'committed':result['committed'], 'variant':'layout'})
            except Exception as error:
                committed.extend(getattr(error,'outputs',[]))
                raise DeliveryError(str(error), committed) from error
            return {**{k:v for k,v in manifest.items() if k not in ('sources','spec')},
                    'directory':str(destination), 'manifest':planned['manifest.json'].target,
                    'pdf':planned['layout.pdf'].target, 'pages':[planned[x].target for x in pages], 'outputs':committed}
        os.rename(stage, destination)
        return {**{k: v for k, v in manifest.items() if k not in ("sources", "spec")}, "directory": str(destination), "manifest": str(destination / "manifest.json"),
                "pdf": str(destination / "layout.pdf"), "pages": [str(destination / x) for x in pages]}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def finish_layout(engine, task, spec, out_dir):
    if not spec:
        return None
    if task is None:
        return {"error": "排版任务缺少固定输入台账"}
    try:
        records = [r for r in task["items"] if r["path"] != LAYOUT_ITEM]
        destination_plan = task['inputs'].get('destination_plan')
        if destination_plan:
            from .export_destination_policy import restore
            layout_entries = [e for e in restore(destination_plan).entries if e.item_id.startswith('layout::')]
            if layout_entries and any(e.disposition == 'skip' for e in layout_entries):
                receipt = {'out_skipped':True, 'skip_reason':'冻结排版目标存在，整套排版按策略跳过', 'outputs':[]}
                engine._task_item(task, LAYOUT_ITEM, receipt)
                task['layout'] = receipt
                return receipt
        receipt = compose(spec, records, out_dir, lambda: engine._task_boundary(task), destination_plan)
        engine._task_item(task, LAYOUT_ITEM, {"out": receipt["manifest"]})
        task["layout"] = receipt
        return receipt
    except Exception as error:
        receipt = {"error": f"{type(error).__name__}: {error}", "sources_preserved": True, "outputs":getattr(error,"outputs",[])}
        engine._task_item(task, LAYOUT_ITEM, {"error": receipt["error"], "stage": "layout", "outputs":receipt["outputs"]})
        task["layout"] = receipt
        return receipt
