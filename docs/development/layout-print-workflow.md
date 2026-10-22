# Layout and system-print implementation (development only)

Status: code implementation, statically read only. No build, type check, test,
product execution, visual acceptance or physical printer acceptance was run.

## Frozen scope and traceability

- Frozen handbook extraction `baseline_probe/manual-text.txt` lines 61,
  299–305 and 1292: ordinary/ID-photo layout, paper orientation and photo paper,
  resolution, rows/columns, spacing/margins, mm/cm/in, saved templates, system print.
- Repository `ui/src/spec/workflows.json`, guide `32483`, preserves the same
  export/layout/template/system-print workflow. Original public reference:
  https://www.pixcakeai.com/guide/32483
- AI development package `功能需求验收映射.json`: LNX-EXPORT-001/002/003
  (collision/atomic submission, frozen recipe, format validation) and LNX-P0-TASK
  govern delivery. The package does not provide a separate exhaustive layout
  parameter registry; new defaults are explicit LumaRetouch design choices,
  not claimed competitor defaults. No frozen specification/status was rewritten.
- Optional album product integration (handbook line 83) is not replaced or
  claimed complete by this grid-layout package.

## Connected implementation

`LayoutControls` sends layout alongside the existing `runExport`. Rust forwards
it to `cmd_export`, which validates and freezes it with the original image recipe.
`layout_spec.py` owns physical geometry. `layout_delivery.py` reads only successful
outputs from this same task, after the existing full-resolution render, crop,
watermark and output-profile pipeline. Original sources and individual exported
files, including RGB16 TIFFs, are untouched. Partial watermark delivery whose
primary output was skipped is not silently treated as a fresh printable image.

A `layout://pages` virtual ledger item records layout success/failure. It is not
part of the original image list or decode input. Existing retry intersects its
pending list with the original images; a layout-only retry therefore decodes
zero images and composes from successful image ledger outputs. Failed or skipped
photos block layout instead of inserting blank cells or stale on-disk files.
Cancellation and pause are checked between pages and before publication. Retry
uses frozen parameters; restarted tasks retain the existing no-live-recipe gate.

The output is a uniquely named directory containing real PNG pages, a multi-page
PDF, and `manifest.json`. Publication renames a completed staging directory;
intermediate page files are flushed and removed on failure. A retry never
clobbers a preceding layout directory. Page count is ceil(images × copies /
(rows × columns)); final unused slots remain white. ID dimensions must fit the
specified grid. Contain preserves the image with possible white padding; cover
uses explicit central cropping. This is dimensional ID layout, not automatic
passport-photo compliance certification.

All lengths are converted through mm. Raster boundaries are rounded to nearest
pixel; their physical tolerance is half a pixel. PDF uses separate effective X/Y
DPI to keep the MediaBox at exact requested millimetres after raster rounding.
Pages are appended to PDF one at a time and closed rather than retaining all
uncompressed images. Limits are 60 million pixels/page and 200 pages/batch.
Templates persist locally, preserve physical lengths across unit changes, reject
invalid records, and refuse same-name overwrite with a visible error.

## Colour and print contract

Each source output's embedded ICC is converted with Pillow ImageCms/LittleCMS to
sRGB. Missing/invalid ICC rejects the layout instead of relabelling Adobe RGB or
another space as sRGB. Print pages are explicitly **8-bit sRGB**, not RGB16 master
exports. PNG embeds sRGB ICC and nominal DPI. Pillow's PDF raster encoding uses
high-quality JPEG (not a lossless-master claim); PDF DeviceRGB samples have already
been converted to sRGB. The original RGB16 files remain untouched.

Rust `layout_print_api.rs` reuses GTK 3 / GdkPixbuf / Cairo already in Tauri's lock
file. It runs `PrintOperationAction::PrintDialog` only after an explicit click,
uses the actual completed receipt, rejects stale/incomplete receipts and changed
page dimensions, and draws in physical mm with full-page origin. The print dialog
remains responsible for final user approval. Non-100% scaling, multi-page-per-sheet
and mismatched page dimensions are rejected rather than silently resizing ID
photos. Hardware margins and printer colour management remain physical/device
constraints: the UI explicitly asks users to check them. An accepted GTK operation
means submitted to the backend, never verified paper output. Cancel keeps files.
Opening the PDF uses `xdg-open` with an exact receipt-owned path, no shell command
string, remote service, online upload or automatic print submission.

## Upstream implementation references

- GTK high-level print lifecycle, page setup, draw-page and explicit PrintDialog:
  https://gtk-rs.org/gtk3-rs/stable/0.18/docs/gtk/struct.PrintOperation.html
- PrintContext physical units and Cairo context:
  https://gtk-rs.org/gtk3-rs/stable/0.18/docs/gtk/struct.PrintContext.html
- gtk-rs GDK Cairo/Pixbuf community binding implementation (reused, not copied):
  https://raw.githubusercontent.com/gtk-rs/gtk3-rs/0.18/gdk/src/cairo_interaction.rs
- Pillow official PDF append and DPI behavior:
  https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#pdf
- Pillow ImageCms:
  https://pillow.readthedocs.io/en/stable/reference/ImageCms.html

GTK remains the system LGPL library; gtk-rs bindings use MIT and Pillow retains
its existing notice. Only a direct dependency edge to the already-locked GTK
package was added, not a new printing SDK or external service.
