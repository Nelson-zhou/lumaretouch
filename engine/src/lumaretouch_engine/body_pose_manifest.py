"""Primary-source pose asset review. No weights, downloads or readiness claims.

The strong expected checksum below is published by two pinned community sources,
not Google-signed or locally verified. First actual acquisition must verify bytes.
"""
MODEL_ID = 'mediapipe-pose-landmarker-full-float16-v1'
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'
MODEL_FILENAME = 'pose_landmarker_full.task'
MODEL_VERSION = 'float16/1'
MODEL_SHA256 = '5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1'
MODEL_SIZE_BYTES = 9398198
PIN_STATUS = 'community-published-exact-version-pin-local-acquisition-unrun'
PIN_SOURCES = (
    'https://github.com/khalid999devs/react-native-pose-detection/blob/c1ff344dd16937f404409326df7242ea92e445b9/packages/core/plugin/src/manifest.ts',
    'https://github.com/khalid999devs/react-native-pose-detection/blob/c1ff344dd16937f404409326df7242ea92e445b9/docs/adr/0004-pin-model-revision-not-latest.md',
    'https://github.com/BotchetDig/workout-gate/blob/c13a65ab1a01e76f33985f754e18b6e254675582/install.sh',
)
# /latest/ is a byte-different ZIP archive. Never fallback or reuse that digest.
MODEL_LICENSE = 'Apache-2.0'
LICENSE_EVIDENCE = (
    'https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf',
    'https://github.com/google-ai-edge/mediapipe/issues/6306',
)
CODE_SOURCE = 'https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/pose_landmarker.py'
GUIDE = 'https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker'
LIMITATIONS = (
    'Model card targets single-person full-body estimation; multiple people are out of its evaluated scope. num_poses is not multi-person shaping validation.',
    'Head visibility, subject scale, pose orientation, lighting, motion and occlusion affect reliability.',
    'Hidden landmarks can be predictions or average positions; no hidden landmark is usable deformation evidence.',
    'Depth is approximate, not metric; no identity or demographic inference, GHUM mesh or SMPL assets are included.',
    'Nearby background moves with shoulder geometry; no background-zero-change promise.',
)
