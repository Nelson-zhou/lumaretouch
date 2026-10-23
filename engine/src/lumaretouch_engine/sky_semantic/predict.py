"""Pinned semantic-only OneFormer adapter, used solely inside an offline worker.

No inverse-person heuristic, pretrained factory, generic tokenizer, custom model
code, remote code, unrestricted pickle, automatic CPU fallback, or networking.
"""
import hashlib
import importlib.abc
import importlib.metadata
import io
import json
from pathlib import Path
import sys
from . import manifest as M


class SemanticOnly(importlib.abc.MetaPathFinder):
    """Fail before unsupported imports; never impersonate the regex dependency."""
    DENIED = ('regex', 'transformers.processing_utils', 'transformers.tokenization_utils_base',
              'transformers.tokenization_utils_tokenizers', 'transformers.tokenization_python',
              'transformers.utils.chat_parsing', 'transformers.models.auto.auto_factory',
              'transformers.modeling_layers', 'transformers.generation.utils',
              'transformers.utils.auto_docstring', 'transformers.modeling_gguf_pytorch_utils')

    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == item or fullname.startswith(item + '.') for item in self.DENIED):
            raise ImportError('语义专用运行库不支持此路径：' + fullname)
        return None


def activate():
    if any(name == 'transformers' or name.startswith('transformers.') or name == 'regex'
           for name in sys.modules):
        raise ValueError('语义模型必须在全新隔离工作进程中加载，不能替换现有运行库')
    sys.meta_path.insert(0, SemanticOnly())
    root, receipt = M.verify()
    # Wheel-tag verification used the host's packaging without any ML imports.
    # The fresh worker now uses only the pinned private copy for model imports.
    for name in tuple(sys.modules):
        if name == 'packaging' or name.startswith('packaging.'):
            del sys.modules[name]
    sys.path.insert(0, str(root / 'runtime'))  # not site.addsitedir: never run .pth
    return root, receipt


def host_identity():
    from packaging.version import Version
    versions = {name: importlib.metadata.version(name) for name in ('torch', 'torchvision', 'numpy', 'Pillow')}
    minimum = {'torch': '2.6', 'torchvision': '0.21', 'numpy': '2.1', 'Pillow': '11'}
    if any(Version(versions[name]) < Version(value) for name, value in minimum.items()):
        raise ValueError('当前选择的引擎运行库未满足语义模型最低版本；不会自动更换显卡运行库')
    return {'python': '.'.join(map(str, sys.version_info[:3])), **versions}


def prepare_image(source, processor):
    """Bounded semantic input only. Original 16-bit working pixels stay intact."""
    import numpy as np
    from .immutable_input import prepare_rgb8, target_size
    if (not isinstance(source, np.ndarray) or source.dtype not in (np.uint8, np.uint16)
            or source.ndim != 3 or source.shape[2] != 3):
        raise ValueError('自动选区需要真实工作色域 RGB8/RGB16 源图')
    target_size(int(source.shape[1]), int(source.shape[0]))
    if source.dtype == np.uint16:
        rgb = np.empty(source.shape, np.uint8)
        for y in range(0, source.shape[0], 128):
            rgb[y:y + 128] = ((source[y:y + 128].astype(np.uint32) + 128) // 257).astype(np.uint8)
    else:
        rgb = source
    return prepare_rgb8(rgb)


def prepare_input(source, *, immutable_input=None):
    """Exclusive decoded-source or already-preprocessed canonical transport."""
    from . import immutable_input as I
    if immutable_input is not None:
        if source is not None:
            raise ValueError('自动选区不能同时使用解码源与规范输入包')
        packet = I.check(immutable_input)
        return I.array(packet), packet['input_sha256'], packet
    if source is None:
        raise ValueError('自动选区缺少真实输入源')
    pixels, digest = prepare_image(source, None)
    return pixels, digest, None


def predict(source, device, *, installation=None, immutable_input=None):
    # Validate before model loading; a prepared packet never visits a resizer.
    pixels, digest, packet = prepare_input(source, immutable_input=immutable_input)
    root = installation if installation is not None else activate()[0]
    runtime = host_identity()
    import numpy as np
    import torch
    from torchvision.transforms.v2 import functional as tvF
    from transformers.models.oneformer.configuration_oneformer import OneFormerConfig
    from transformers.models.oneformer.modeling_oneformer import OneFormerForUniversalSegmentation
    if device not in ('cpu', 'cuda') or (device == 'cuda' and not torch.cuda.is_available()):
        raise ValueError('所选自动选区设备不可用；不会静默切换设备')
    if device == 'cuda' and torch.cuda.mem_get_info()[0] < 2 * 1024**3:
        raise ValueError('自动选区显存预算不足；请释放显存或明确选择 CPU')
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)
    data = json.loads((root / 'model/config.json').read_text())
    processor = json.loads((root / 'model/preprocessor_config.json').read_text())
    lock = M.lock()
    if (data.get('model_type') != 'oneformer' or data.get('is_training') is not False
            or data.get('backbone_config', {}).get('model_type') != 'swin'
            or len(data.get('id2label', {})) != 150
            or any(data['id2label'].get(k) != label for k, label in lock['class_labels'].items())):
        raise ValueError('官方模型类别或结构身份不符合固定语义任务')
    config = OneFormerConfig.from_dict(data)
    # Explicit built-in class construction, no AutoModel/from_pretrained or
    # remote-code execution. This sets the equivalent trust boundary to false.
    config.trust_remote_code = False
    config._attn_implementation = 'eager'
    config.backbone_config._attn_implementation = 'eager'
    model = OneFormerForUniversalSegmentation(config)
    checkpoint = root / 'model/pytorch_model.bin'
    raw = checkpoint.read_bytes()
    if len(raw) != lock['files'][-1]['size'] or hashlib.sha256(raw).hexdigest() != lock['files'][-1]['sha256']:
        raise ValueError('载入前模型字节发生变化')
    state = torch.load(io.BytesIO(raw), map_location='cpu', weights_only=True)
    del raw
    if not isinstance(state, dict) or not all(isinstance(k, str) and type(v) is torch.Tensor for k, v in state.items()):
        raise ValueError('模型不是固定的纯张量参数字典')
    model.load_state_dict(state, strict=True)
    del state
    model.eval().to(device=device, dtype=torch.float32)
    tensor = torch.from_numpy(pixels).permute(2, 0, 1).unsqueeze(0).to(device=device, dtype=torch.float32)
    mean = torch.tensor(processor['image_mean'], device=device).view(1, 3, 1, 1)
    std = torch.tensor(processor['image_std'], device=device).view(1, 3, 1, 1)
    tensor = (tensor * float(processor['rescale_factor']) - mean) / std
    from .task_tokens import derive
    derived = derive(root / 'model')
    if derived['token_ids'] != lock['task']['token_ids']:
        raise ValueError('官方固定任务的词表与 BPE 推导不匹配')
    task = torch.tensor([derived['token_ids']], dtype=torch.long, device=device)
    with torch.inference_mode():
        output = model(pixel_values=tensor, task_inputs=task, return_dict=True,
                       output_hidden_states=False, output_attentions=False)
        classes = output.class_queries_logits[0].softmax(-1)[:, :-1]
        masks = output.masks_queries_logits[0].sigmoid()
        if classes.shape[1] != 150 or not torch.isfinite(classes).all() or not torch.isfinite(masks).all():
            raise ValueError('语义模型返回了无效类别或非有限值')
        shape = pixels.shape[:2]
        best = torch.full(shape, -1.0, device=device)
        winner = torch.zeros(shape, dtype=torch.int16, device=device)
        total = torch.zeros(shape, device=device)
        support = {key: torch.zeros(shape, device=device) for key in lock['classes']}
        # Official semantic einsum + bilinear logits resize, class-chunked to
        # avoid materializing 150 full-size float maps. Strict > preserves the
        # same first-class tie rule as argmax, not a guessed semantic heuristic.
        for start in range(0, 150, 16):
            end = min(150, start + 16)
            scores = torch.einsum('qc,qhw->chw', classes[:, start:end], masks)
            scores = tvF.resize(scores[None], size=list(shape),
                                interpolation=tvF.InterpolationMode.BILINEAR)[0]
            maximum, index = scores.max(0)
            replace = maximum > best
            winner = torch.where(replace, (index + start).to(torch.int16), winner)
            best = torch.maximum(best, maximum)
            total += scores.sum(0)
            for key, ids in lock['classes'].items():
                selected = [i - start for i in ids if start <= i < end]
                if selected:
                    support[key] += scores[selected].sum(0)
        labels = winner.cpu().numpy()
        fields, supports = {}, {}
        for key, ids in lock['classes'].items():
            fields[key] = (np.isin(labels, ids).astype(np.uint8) * 255)
            supports[key] = ((support[key] / total.clamp_min(1e-12)).clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
    result = {'fields': fields, 'supports': supports, 'input_sha256': digest,
              'input_size': [pixels.shape[1], pixels.shape[0]], 'model': M.identity(),
              'host': runtime, 'device': device, 'pixels': pixels,
              'confidence_note': '类别支持度是未校准的相对分数，不是正确率。'}
    if packet is not None:
        from .immutable_input import metadata
        result['_immutable_input'] = metadata(packet)
    return result
