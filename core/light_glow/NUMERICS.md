# Deterministic SDR artistic light diffusion

This is the original v1 numerical definition, **AUTHORED / UNRUN**. It is neither
an implementation of an undisclosed vendor model nor a measured physical filter.
Floating sums are f64, stored planes/results are f32. No external code is copied.

## Highlight seed

Unpremultiply an input pixel with positive alpha to linear-SDR c in [0,1]^3.
Let Y = 0.2126 R + 0.7152 G + 0.0722 B. The threshold t starts a fixed local
0.10-wide smooth transition, shortened when necessary at white:

    q = clamp((Y-t) / min(0.10,1-t), 0, 1)
    m = q*q*(3-2*q)

At t=1, select only Y exactly 1. Transparent pixels never supply radiance.
The nine initial planes are three `m * premultiplied RGB` seeds, three original
premultiplied RGB channels, and three copies of alpha. This is explicit luminance
selection, not AI recognition of illuminated regions, people or scenes.

## Finite diffusion and dispersion

For radius R and scattering d, channel reaches are:

    red = ceil(R*(1+0.25*d)); green = R; blue = ceil(R*(1-0.25*d)).

For channel reach r, apply three normalized separable box kernels with integer
radii `floor(r/3)`, `floor((r+1)/3)`, `floor((r+2)/3)`. Their radii sum exactly r.
Each pass is horizontal then vertical. This explicitly defined three-pass box
cascade is not relabelled as an exact Gaussian. It supplies a smooth finite halo;
channel-specific reach creates actual dispersion, not just a saturation edit.
Darktable's mature soften operator provides a real precedent for repeated box
diffusion, but its source, coefficients and colour pipeline were not ported.

Image boundaries extend by clamping the nearest sample at each pass. Tile-region
internal clamping cannot affect output because the entire combined support is
provided. Sliding sums are O(region pixels plus line initialization), independent
of radius for each interior pixel. A nonzero-sample count resets truly empty
windows exactly to zero, preventing roundoff residue from becoming a coloured
halo after a lightness adjustment. There is no FFT, downsample or proxy upscale.

Normalize each blurred seed channel by its corresponding blurred alpha to obtain
H, and normalize blurred original RGB by the same alpha to obtain B. This prevents
transparent black from darkening the diffusion field. A zero denominator gives
zero H; current original c supplies B. The original alpha is never replaced.

## Bounded exposure and tint

For positive H and gain g=2^exposure_ev, independently transform each component
with `g*H / (1 + (g-1)*H)`. This maps [0,1] to [0,1], keeps black/white endpoints,
and is identity at zero EV. It is a declared SDR shoulder, not clipped scene HDR
or a claim that every source value doubles for +1 EV.

Then use conventional HSL of the linear RGB halo (not perceptual encoded sRGB):
rotate hue by hue_deg; for each of saturation and lightness apply `v+a*(1-v)`
when adjustment a>=0 or `v+a*v` otherwise. The hue of an achromatic halo is
conventionally zero before rotation. Exact zero radiance bypasses tint entirely,
so even +1 lightness cannot create light outside its true support. Positive but
very faint halos can be substantially brightened by the explicit lightness knob;
this artistic behavior is not masked illumination estimation.

Call the tinted/exposed halo G, strength k and V=max(G). For each channel c:

    black_mist:
      delta = G - m*c
      out = c + k*delta*(delta>=0 ? (1-c) : c)

    white_mist:
      weight = k*V
      softened = c + 0.35*weight*(B-c)
      out = (1-weight)*softened + k*G

    glow:
      out = c + k*G*(1-c)

Black mist redistributes selected light: local highlight peaks can darken while
nearby regions gain a restrained halo. It is not energy-conserving optics because
of the explicit SDR headroom weights. White mist mixes a broad veiling field with
true base-detail diffusion; it is not merely the glow response with a renamed
strength knob. Digital glow adds light through available SDR headroom. The three
responses are mathematically distinct, though uniform or neutral cases may agree.

These equations remain in [0,1] in exact arithmetic. Out-of-domain numerical
results beyond 1e-12 fail. Only harmless roundoff at this tolerance is bounded;
actual HDR/negative input is rejected before processing and never clipped into
this domain. Multiply RGB by the original alpha, then store f32. Alpha is copied.

## Effect-range diagnostic

Coverage is `max_c(abs(output_premultiplied[c]-input_premultiplied[c]))`, computed
from final stored f32 RGB. It is in [0,1], exactly zero wherever output is unchanged.
It describes the actual changed pixels, not just the pre-blur highlight seed.
The UI may render a labelled green diagnostic with a declared display gain but
must not replace coverage with threshold data, claim semantic detection, or burn
the diagnostic into exported pixels.

Only strength=0 is the guaranteed bit-exact whole-operation neutral shortcut.
All metadata, geometry, pixel and budget checks still apply. Other mathematically
unchanged cases may incur harmless floating roundoff and are covered by numerical
fixtures rather than a blanket bitwise promise.
