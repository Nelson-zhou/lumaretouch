# SPDX-License-Identifier: Apache-2.0
"""Fixed official artifact identity. No mutable model/config lookup."""
MODEL_ID = 'Swin2SR-classical-sr-x2-64'
MODEL_REVISION = 'cee1c923c6a37361c6e5650b65dcf4be821e5d52'
CHECKPOINT_FILENAME = 'model.safetensors'
CHECKPOINT_SHA256 = 'a515955815ab6dba3a9331d8c75db13a5166a5ffbcebf1a95ab676a5656ac4fb'
CHECKPOINT_SIZE_BYTES = 48460660
CHECKPOINT_URL = ('https://huggingface.co/caidas/swin2SR-classical-sr-x2-64/resolve/'
                  + MODEL_REVISION + '/' + CHECKPOINT_FILENAME)
MODEL_LICENSE = 'Apache-2.0'
INPUT_ALIGNMENT = 8
PARAMETER_PAYLOAD_BYTES = 48366284
HEADER_BYTES = 94368
HEADER_PREFIX_SHA256 = '6e72a861509a89f98ed23a506c791068c6638d58782dee73a72f892201c96888'


def expected_shapes():
    """Explicit HF key contract; independently compared with official header."""
    shapes = {}
    def affine(name, shape, bias=True):
        shapes[name + '.weight'] = tuple(shape)
        if bias:
            shapes[name + '.bias'] = (shape[0],)
    affine('swin2sr.first_convolution', (180, 3, 3, 3))
    affine('swin2sr.conv_after_body', (180, 180, 3, 3))
    affine('swin2sr.embeddings.patch_embeddings.projection', (180, 180, 1, 1))
    affine('swin2sr.embeddings.patch_embeddings.layernorm', (180,))
    affine('swin2sr.layernorm', (180,))
    for stage in range(6):
        prefix = f'swin2sr.encoder.stages.{stage}'
        affine(prefix + '.conv', (180, 180, 3, 3))
        affine(prefix + '.patch_embed.projection', (180, 180, 1, 1))
        for layer in range(6):
            p = prefix + f'.layers.{layer}'
            for name in ('layernorm_before', 'layernorm_after'):
                affine(p + '.' + name, (180,))
            affine(p + '.intermediate.dense', (360, 180))
            affine(p + '.output.dense', (180, 360))
            affine(p + '.attention.output.dense', (180, 180))
            a = p + '.attention.self'
            for name in ('query', 'key', 'value'):
                affine(a + '.' + name, (180, 180), name != 'key')
            shapes[a + '.logit_scale'] = (6, 1, 1)
            affine(a + '.continuous_position_bias_mlp.0', (512, 2))
            affine(a + '.continuous_position_bias_mlp.2', (6, 512), False)
    affine('upsample.conv_before_upsample', (64, 180, 3, 3))
    affine('upsample.upsample.convolution_0', (256, 64, 3, 3))
    affine('upsample.final_convolution', (3, 64, 3, 3))
    return shapes
