# SPDX-License-Identifier: GPL-3.0-or-later
"""Official hand proposal asset provenance, not a readiness or quality claim."""
MODEL_ID = 'mediapipe-hand-landmarker-full-float16-v1'
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
MODEL_FILENAME = 'hand_landmarker.task'
MODEL_VERSION = 'float16/1'
MODEL_SHA256 = 'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'
MODEL_SIZE_BYTES = 7_819_105
MODEL_LICENSE = 'Apache-2.0'
PIN_STATUS = 'official-version-stream-sha256-observed-2026-10-25-no-retained-model'
GUIDE = 'https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker'
VERSION_EVIDENCE = 'https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/web/vision/README.md'
LICENSE_EVIDENCE = 'https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf'
CODE_SOURCE = 'https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/tasks/python/vision/hand_landmarker.py'
CODE_LICENSE = 'Apache-2.0'
# Existing repository packaging channel; this is not a fresh dependency audit.
RUNTIME_VERSION = '1.1.1'
RUNTIME_REQUIREMENTS = 'engine/requirements-mediapipe.txt'
LIMITATIONS = (
    'Every output is an unreviewed proposal, including apparently visible points; hidden anatomy is never deformation evidence.',
    'The model card describes gloves, occlusion, held objects and hand decorations including jewelry as out-of-scope reliability cases, not license prohibitions.',
    'There is no automatic jewelry, occlusion or visibility verifier in this adapter. Users must review actual visible anatomy and boundaries.',
    'Handedness is an unconfirmed model hint, not identity, person ownership or a mirroring-independent fact.',
    'World coordinates and z are predictions, not measured anatomy; only explicitly reviewed source-plane geometry can drive the original hand-shape kernel.',
    'No demographic template, identity recognition or medical inference is supplied.',
    'Detector limit is a processing budget, not proof every hand has been detected.',
)

# Internal curated-download profile, never IPC-supplied metadata.
EXTENSION_ID = 'hand-landmarker-v1'
CHECKPOINT_URL = MODEL_URL
FIXED_DOWNLOAD_URL = MODEL_URL
CHECKPOINT_SHA256 = MODEL_SHA256
CHECKPOINT_SIZE_BYTES = MODEL_SIZE_BYTES
