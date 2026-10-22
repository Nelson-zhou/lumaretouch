"""Private, offline, killable prompted-selection worker; no installation path."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import resource


def image_url(image, *, rgb=False):
    from PIL import Image
    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS if rgb else Image.Resampling.NEAREST)
    output = io.BytesIO()
    image.save(output, format='PNG')
    data = output.getvalue()
    if len(data) > 4*1024**2:
        raise ValueError('Prompted image preview exceeds transport budget')
    return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')


def run(directory):
    from PIL import Image
    from .prompted_mask_source import decode_source, inference_image, Predictor, check_prompts
    root = Path(directory)
    raw = (root/'request.json').read_bytes()
    if len(raw) > 65536: raise ValueError('Prompted worker request exceeds budget')
    request = json.loads(raw)
    if set(request) != {'path', 'source', 'device', 'prompts'}:
        raise ValueError('Invalid prompted worker request')
    source = decode_source(request['path'], request['source'], device='cpu')
    image, digest = inference_image(source)
    result = {'source_image': image_url(Image.fromarray(image), rgb=True),
              'source': request['source'], 'input_sha256': digest,
              'inference_size': [image.shape[1], image.shape[0]]}
    if request['prompts'] is not None:
        prompts = check_prompts(request['prompts'])
        prediction = Predictor(request['device']).predict(source, prompts)
        masks = prediction.pop('masks')
        result.update(prediction)
        result['prompts'] = prompts
        result['candidates'] = [image_url(Image.fromarray(mask*255)) for mask in masks]
        fields = []
        for mask in masks:
            out = io.BytesIO()
            Image.fromarray(mask*255).save(out, format='PNG')
            fields.append(base64.b64encode(out.getvalue()).decode('ascii'))
        result['_mask_fields'] = fields
    data = json.dumps(result, allow_nan=False, separators=(',', ':')).encode()
    if len(data) > 8*1024**2: raise ValueError('Prompted result exceeds transport budget')
    with (root/'result.json').open('xb') as output:
        output.write(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    from .inspection_worker import bind_parent
    bind_parent(args.parent_pid)
    # Torch GPU maps can exceed a small RLIMIT_AS without consuming that much
    # RAM. Admission is done by the owner; bound CPU time and file output here.
    for key, limit in ((resource.RLIMIT_CPU, 180), (resource.RLIMIT_FSIZE, 8*1024**2)):
        _, hard = resource.getrlimit(key)
        limit = limit if hard == resource.RLIM_INFINITY else min(hard, limit)
        resource.setrlimit(key, (limit, limit))
    os.environ['OMP_NUM_THREADS'] = '2'
    os.environ['OPENBLAS_NUM_THREADS'] = '2'
    try:
        run(args.directory)
    except Exception as error:
        with (Path(args.directory)/'error.json').open('w') as output:
            json.dump({'error': str(error)[:2000]}, output)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
