# Sources, originality and licensing

Read on 2026-10-24. Research only; no upstream runtime, source distribution, model,
image, face dataset, code excerpt or binary was downloaded/copied into this module.

- Product behavior: [PixCake expression management](https://wiki.pixcakeai.com/guide/9406.html).
  Proprietary product documentation is a behavior reference, not code or image
  permission. No PixCake artwork/UI/code is included or reverse engineered.
- Landmarks: [Google's Face Landmarker guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker)
  describes the face mesh, landmark output, expressions and transforms. The
  [v0.10.35 face-landmarker source](https://github.com/google-ai-edge/mediapipe/blob/v0.10.35/mediapipe/tasks/python/vision/face_landmarker.py)
  supplies public mesh topology context. The eight alignment anchors are an
  original bounded engineering choice, not a Google recommendation or algorithm.
- [MediaPipe code LICENSE](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE)
  is Apache-2.0. Existing `docs/model-licenses/models.json` separately registers
  the Face Landmarker bundle, revision float16/1, 3,758,596 bytes and SHA256
  64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff.
  This module does not re-verify those model bytes or independently establish
  model/data/runtime rights. Keep the existing model-license and no-identity-use
  restrictions; source Apache licensing does not independently prove every
  weight or training-data license. Identity confirmation is human, not inference.
- Mature multiscale practice: [OpenCV image-pyramid tutorial](https://docs.opencv.org/4.13.0/dc/dff/tutorial_py_pyramids.html)
  and [MultiBandBlender reference](https://docs.opencv.org/4.13.0/d5/d4b/classcv_1_1detail_1_1MultiBandBlender.html).
  The independent implementation uses Gaussian reduction, Laplacian differences
  and matched reconstruction, with an additional conservative hard support cap.
  It does not bind to OpenCV, copy its implementation or claim numerical identity
  with OpenCV's image-stitching blender.
- [OpenCV licensing](https://opencv.org/license/) identifies versions 4.5+ as
  Apache-2.0 and older releases as BSD-3-Clause. No OpenCV dependency is introduced.

New original code is GPL-3.0-or-later, consistent with the repository license.
A future package that actually redistributes MediaPipe, OpenCV, model files or
other upstream components must retain the applicable licenses/attributions and
satisfy its independent artifact/runtime/privacy release gates. This research is
not approval to download, install, execute or package those components.
