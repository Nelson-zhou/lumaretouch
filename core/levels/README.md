# Levels contract v1

Independent scalar reference and native parameter validation in Rust. The existing
NumPy/Torch vector pipeline implements the same formulas without a per-pixel IPC
or FFI round trip. This is not a claim that the whole image engine is Rust.

- Domain: display-encoded sRGB, master first, then independent R/G/B.
- Input endpoints 0–1, white minus black at least 1e-5; gamma 0.1–10.
- Active channel: t = clamp((x - input_black)/(input_white-input_black), 0, 1),
  output = output_black + (output_white-output_black) * t^(1/gamma).
- Output endpoints may reverse (inversion) or coincide (flat output).
- An exactly neutral channel bypasses computation, including negative/HDR input;
  disabled module bypasses all channels. Active channels explicitly clip input.
- UI midpoint is input_black + (input_white-input_black) * 0.5^gamma.
- Common pipeline: exposure → levels → curves → HSL. Preview, standard export,
  RGB16 export and full-quality inspection share the recipe path.

References: [GIMP Levels manual](https://docs.gimp.org/3.0/en/gimp-tool-levels.html)
and [GIMP implementation](https://raw.githubusercontent.com/GNOME/gimp/master/app/operations/gimpoperationlevels.c).
The channel order, neutral bypass and clipping policy above are this project's
explicit contract, not a claim of bit-identical GIMP or darktable output.

## Ownership and validation

`levels_controller.py` owns recipe and command rollback via narrow callbacks;
`levels_stage.py` owns vector-stage parameters/timing; UI `LevelsEditor` owns
interaction state; `levelsModel` owns pure parameter transformations; native
`levels_api.rs` validates and queues commands. Engine/App/main only wire ports.

Commands carry document ID and request ID. Document tokens invalidate before a
successful decode starts replacing recipe state. A failed later attach cannot
reuse the previous photo's token. The UI acknowledges only a correlated receipt
and a same-document authoritative snapshot at least as new as the receipt. Recipe
equality alone is not an acknowledgement; a later undo snapshot wins over the
receipt's older recipe. These safeguards also cover new UI curve commands;
legacy curve callers without document ID remain backward compatible.

Validation files cover scalar Rust, NumPy/Torch parity, old-project defaults,
project/preset/batch/history, RGB8/RGB16 export, actual inspection worker, failed
switches and receipt ordering. Tests are written, not yet executed for this candidate.
Histogram, eyedroppers, parametric curves and real-machine performance/visual
acceptance remain separate unfinished work; no placeholder is counted as complete.
