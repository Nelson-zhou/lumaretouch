# Source and licence review (2026-10-24)

- Björn Ottosson, "A perceptual color space for image processing":
  https://bottosson.github.io/posts/oklab/ . Primary author explains perceptual
  L/a/b and supplies the linear-sRGB equations, updated 2021-01-25. The author
  explicitly releases those conversion examples to the public domain and also
  offers MIT: https://bottosson.github.io/misc/License.txt . We elect the stated
  public-domain grant for the mathematical conversion constants; attribution is
  retained here and in lib.rs. Our operation implementation is GPL-3.0-or-later.
- Durand and Dorsey, "Fast Bilateral Filtering for the Display of High-Dynamic-Range
  Images" (SIGGRAPH 2002), primary author project:
  https://people.csail.mit.edu/fredo/PUBLI/Siggraph2002/ . Consulted for the mature
  base/detail separation idea. No source archive or code was acquired or reused.
  This implementation is NOT that paper's bilateral filter or HDR tone mapper.
- Paris and Durand bilateral survey/project:
  https://people.csail.mit.edu/sparis/bf/ . Considered edge-aware filtering and
  implementation complexity. No downloaded code, dependency or inferred licence.
- Crow, "Summed-Area Tables for Texture Mapping" (SIGGRAPH 1984), original paper
  visible at https://citeseerx.ist.psu.edu/document?doi=c769616122353ff8f9444ac708cea22fc4032685&repid=rep1&type=pdf .
  Summed-area rectangle accumulation is independently implemented. Publisher
  DOI https://dl.acm.org/doi/10.1145/800031.808600 returned HTTP 403 during review.
  The paper is not claimed open-source; no paper text or code is distributed.
- Knutsson and Westin, "Normalized and Differential Convolution" (CVPR 1993),
  confirmed in the primary author's publication list:
  https://staff.gitlab-pages.liu.se/publications/hankn25/ . Our weighted box
  numerator/denominator is a simple independent normalized convolution, not a
  port of their differential-convolution implementation. No third-party code
  or licence inferred from the publication citation.

Existing project dependencies are unchanged. No new model, external binary,
remote service, proprietary asset, pigment material or cosmetic detector is used.
No claim is made that these sources establish eye-makeup photographic quality.
