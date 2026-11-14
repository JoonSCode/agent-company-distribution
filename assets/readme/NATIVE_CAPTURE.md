# Native terminal screenshot provenance

The README pictures are **actual Orca terminal screenshots**, captured on
2026-11-14 from the unchanged installed Company renderer. Their inputs are
synthetic English search-release tasks with illustrative `demo-planner`,
`demo-builder` and `demo-reviewer` assignments, **not provider models or live model
execution**. Specialist assignments remain unknown. Synthetic task review states
do not approve the overall goal, authenticate staffing, or prove concurrency.

The PNGs are lossless rectangular crops of native app-window captures, not
stdout rasterization, a browser terminal, redrawn cards or recolored pixels.
Only the terminal content is published: no application sidebar, tab bar, window
controls, shell prompt, account information, private paths or real work records.
Private raw windows are retained for review, not distributed.

## Inputs and limits

- [Pinned input manifest](native-fixture/view.json), [record](native-fixture/record.json),
  [organization claims](native-fixture/claims.json), [dependency plan](native-fixture/plan.json).
  These are newly authored public-safe fixtures; no private reference capture is included.
- [Machine-readable capture receipt](capture-native.json) records renderer, raw,
  PNG and decoded-pixel hashes, exact crop boxes, dimensions and displayed links.
- [Wide screenshot](company-native.png): 94 columns × 32 rows, eight full-field
  cards, eight of nine recorded dependencies visible; `t2 → t5` is undrawn.
- [Narrow screenshot](company-native-narrow.png): 48 columns × 32 rows, page 1
  of 2, four cards and one of nine links visible. Header/navigation truncation
  is the renderer's actual `~` truncation, not image clipping or retouching.
- [Wide text](company-native.txt) and [narrow text](company-native-narrow.txt) are
  plain frames from these exact inputs and declared dimensions, not the image
  generation source. Unicode mode retains the shipped Korean interface labels.
- `합성 시연 | 연결 일부만 기록 | 실행 관측 없음` means synthetic demonstration,
  partial recorded links, no execution observation. The native footer is preserved.

These are declared PTY sizes in a new owned Orca terminal, not evidence of
automatic host-pane resizing. The host's existing dark background and font were
not changed. `--palette dark` chooses local foreground/status colors only; it
is not theme detection, a changed default, or a terminal-theme setting.
The resident viewer was used for native colors; `--once` prints a plain frame.

## Reproduce the terminal content

Use an existing Python 3.13 and a **new empty terminal you own** in Orca, from
the distribution root. Use an already-dark terminal for this explicit palette;
do not alter another session, user theme or font. No installation, credentials,
worker/model launch or Orca service call is needed for the renderer.

```sh
saved_size="$(stty size)"
stty rows 32 cols 94
env -u NO_COLOR TERM=xterm-256color COLORTERM=truecolor \
  python3.13 -B skills/company-orchestration/scripts/status_tui.py \
  --manifest assets/readme/native-fixture/view.json --palette dark --layout wide
# Press q to leave the resident viewer, then restore this owned PTY's size.
stty rows "${saved_size% *}" cols "${saved_size#* }"
```

Repeat with `cols 48` for the narrow view; leave `--layout wide` unchanged.
This affects only the caller-owned PTY's declared geometry, not Orca pane layout.
For a checked text-only frame (not a native screenshot):

```sh
python3.13 -B skills/company-orchestration/scripts/status_tui.py \
  --manifest assets/readme/native-fixture/view.json --palette dark --layout wide \
  --once --width 94 --height 32
```

Capture the actual Orca app window through a native window-capture tool. The
recorded capture used the app-scoped native `computer_use` window capture in
vision mode, without accessibility overlays. An OS window screenshot is also
native, but its bytes, geometry and crop coordinates will differ. Never render
saved text into an image as a substitute. Inspect the raw window privately first.

## Lossless crop and checks

For this capture's 1456 × 1294 raw windows, the half-open crop rectangles are
`(380, 51, 1390, 721)` (wide, 1010 × 670 PNG) and
`(380, 51, 891, 721)` (narrow, 511 × 670 PNG). Coordinates are capture-specific;
reinspect any new raw image rather than applying them blindly.

With Pillow available in a separate capture-tool environment, a crop can be
saved and its decoded pixels compared without resizing, drawing or recoloring:

```python
from PIL import Image
raw = Image.open("raw.png")
box = (380, 51, 1390, 721)  # only for the recorded wide-window geometry
crop = raw.crop(box)
crop.save("crop.png")
assert Image.open("crop.png").tobytes() == raw.crop(box).tobytes()
```

Review the resulting PNG itself for readable colors and privacy. Require the
entire footer and relevant route boundaries; retain omissions and truncation
honestly. Do not mask secrets inside a publishable crop: make a clean new
synthetic capture instead. Publish no raw app windows. The shipped PNGs have no
embedded text/EXIF metadata. Different display/font/capture implementations may
produce different pixels; the receipt binds these assets, not all reproductions.

From the distribution root, verify the public PNG/text byte hashes:

```sh
python3.13 - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('assets/readme')
receipt = json.loads((root / 'capture-native.json').read_text())
for frame in receipt['frames']:
    for ext, key in [('png', 'png_sha256'), ('txt', 'text_sha256')]:
        path = root / (frame['name'] + '.' + ext)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == frame[key], path
print('native asset hashes match')
PY
```

The historical `company-demo*.png` and `capture.json` remain separately identified
stdout-rasterized assets for the original three-task no-model demo. They are not
the README's native screenshots. The development-only `release/capture_demo.py`
regenerates those historical assets only; it does **not** perform native capture.
The regular no-model demo and its default English ASCII presentation are unchanged.
