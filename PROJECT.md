# Loopscooper — Loop Detection & Export

## Overview

Loopscooper is a tool for automatically detecting seamless audio loops in music files and exporting them for use in game audio systems. It is a heavily modified fork of [arkrow's PyMusicLooper](https://github.com/arkrow/PyMusicLooper), reimagined around a single interactive workflow: detect, preview, refine, and export.

Where the original tool exposed many separate commands (`play`, `split-audio`, `extend`, `export-points`, `tag`), Loopscooper distills everything into a single command with a guided, iterative workflow.

Loopscooper provides two interfaces:
- **CLI** — single command with an interactive, menu-driven workflow
- **Web** — drag-and-drop interface served via a lightweight Flask server

## Use Case

In game audio development, it's common to structure music as:
1. **Intro** — plays once when the track starts
2. **Loop** — repeats seamlessly while the player is in a zone
3. **Outro** — plays when transitioning out of the zone

Loopscooper detects the loop point in an audio file and exports the loop sections as individual WAV files. Game developers can then programmatically play the intro, loop N times, and play the outro.

## Installation

```bash
# Using uv (recommended)
uv tool install git+https://github.com/<user>/loopscooper.git

# From source
git clone https://github.com/<user>/loopscooper.git
cd loopscooper
uv pip install -e .
```

Pre-requisites: Python >=3.10, ffmpeg (for additional audio formats).

## Usage

### CLI

Loopscooper has a single command. The audio file is passed as a positional argument.

```bash
# Basic usage — finds file in CWD, auto-detects BPM, interactive preview & export
loopscooper song.wav

# Absolute path
loopscooper /Users/youruser/Music/song.wav

# Relative path
loopscooper ./music/song.wav
```

If the file is not found in the current working directory, the script will attempt to resolve it as a relative or absolute path. If still not found, it errors with a message asking the user to provide a valid file path.

### Web Interface

```bash
# From the project root
python web/server.py

# Or with the venv
.venv/bin/python web/server.py
```

The server listens on port 8282 by default (configurable via `PORT` environment variable).

### Systemd Service

A systemd unit file is provided at `weblooperscoop.service`:

```bash
sudo cp weblooperscoop.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now weblooperscoop
```

Access the interface at `http://localhost:8282`.

### Complete Interactive Session (CLI)

```
$ loopscooper song.wav

Detected BPM: 100.00
Beat Duration: 0.600s

Suggested Loop Lengths (4/4 time):
  1 bar (4 beats):  2.400s
  2 bars (8 beats): 4.800s

Enter loop duration window (min,max in seconds) [2.4,4.8]: 2,8

Analyzing audio for loops (2-8s)...

Discovered loop points (25/47 displayed)

  Index │ Loop Start │ Loop End  │ Length
────────┼────────────┼───────────┼────────
      0 │ 0:12.345   │ 0:16.789  │ 0:04.444
      1 │ 0:24.567   │ 0:29.012  │ 0:04.445
      ...

Preview loop index (e.g., 0p, or "done" to skip): 0p
Previewing loop #0... (Ctrl+C to stop)

Preview loop index (e.g., 3p, or "done" to skip): done

Re-detect loops? (enter min,max duration or n) [n]: 2,6

Analyzing audio for loops (2-6s)...

Discovered loop points (15/20 displayed)

  Index │ Loop Start │ Loop End  │ Length
────────┼────────────┼───────────┼────────
      0 │ 0:30.123   │ 0:32.456  │ 0:02.333
      ...

Preview loop index (e.g., 0p, or "done" to skip): done

Re-detect loops? (enter min,max duration or n) [n]: n

Enter loop indices to export (e.g., 0,1-3,5-8,10): 0,1-3,5-8,10

Exporting 9 loop(s) to song-samples/...
Exported song-01.wav (0:04.444)
...

Successfully exported 9 loop(s) to song-samples/
```

### Complete Web Session

1. Navigate to `http://localhost:8282`
2. Drag & drop an audio file (or click to select)
3. Analysis runs automatically — displays BPM, musical key, 1-bar / 2-bar suggestions
4. Loop candidates shown in a table with Type badges (1 Bar / 2 Bars)
5. Click any row to preview that loop (plays loop section only, no intro)
6. Click the same row again to stop previewing
7. Check boxes next to loops you want to export
8. Click **Export Selected** to download a ZIP of the chosen loops

### Phase 1 — Auto-detect BPM and Key

Runs immediately on launch. Uses librosa beat tracking to estimate the track's tempo. Displays:

- Detected BPM (to 2 decimal places)
- Beat duration in seconds
- **Musical key** (e.g., "C major", "A minor") — detected via the Krumhansl-Schmuckler algorithm
- **1 bar** (4 beats) suggested loop length
- **2 bars** (8 beats) suggested loop length

These suggestions are based on 4/4 time, the most common time signature. They are used as default loop duration constraints for detection.

### Phase 2 — Duration Window Prompt (CLI only)

User enters a comma-separated pair of values for min and max loop duration in seconds (e.g., `2,8`). This controls the range of loop lengths the detection algorithm will consider.

- **Blank input** — uses the BPM-derived defaults (1-bar to 2-bar)
- **`2,8`** — sets min_loop_duration=2s, max_loop_duration=8s
- The prompt shows the current defaults in brackets, e.g., `[2.4,4.8]`

### Phase 3 — Detect Loops

Runs after the duration window is set. Uses librosa for audio analysis and chroma-based cross-correlation to find the best repeating sections. The loop duration constraints (from the BPM or user input) determine the range of loop lengths considered.

Displays a table of discovered loop candidates with index, start time, end time, and length.

### Phase 4 — Preview

User previews individual loops by entering their index followed by `p` (e.g., `0p`, `3p`). Each preview plays the loop section in a continuous loop — no intro, no outro. Press Ctrl+C to stop.

The table can be paginated with:
- `more` — show more results
- `all` — show all results
- `reset` — return to default view

Type `done` to exit the preview phase.

### Phase 5 — Re-detect or Continue

After previewing, the user is asked whether to re-detect loops with different duration constraints. Options:

- **`n`** (or blank) — proceed to export
- **`2,6`** — re-detect with min=2s, max=6s. After re-detection, the loop table resets with fresh indices and the flow returns to Phase 4 (preview).

The prompt shows the current min/max values in brackets, e.g., `[n]`. This iteration cycle can repeat as needed.

### Phase 6 — Export

User enters comma-separated indices to export:

- Single: `0`
- Multiple: `0,1,3`
- Ranges: `1-4`
- Mixed: `0,1-3,5-8,10`

Output is written to `{basename}-samples/` (e.g., `lovesong.wav` → `lovesong-samples/`). Files are named `{basename}-{NN}.wav` with zero-padded sequence numbers. Default format is WAV.

## Technical Details

### BPM Detection

Uses librosa's onset strength envelope and beat tracking to estimate tempo. The detected BPM drives the default loop duration constraints:

- **1 bar** = 4 × (60 / BPM) seconds
- **2 bars** = 8 × (60 / BPM) seconds

### Key Detection

Key detection uses the Krumhansl-Schmuckler algorithm (1985), a widely-used method for tonal profile analysis. The process:

1. Computes a chroma spectrogram from the audio (12 pitch class bins summed over time)
2. Normalizes the chroma histogram to [0, 1]
3. Compares against 24 reference profiles (12 major + 12 natural minor) using Pearson correlation
4. Returns the key with the highest correlation score (e.g., "C major", "A minor")

This is the same algorithm used in the original Krumhansl & Schmuckler study and is implemented with zero new dependencies — it reuses the chroma features already computed during loop analysis.

### Loop Detection

The tool uses librosa for audio analysis and chroma-based cross-correlation to find the best repeating section. Detection considers:

- Chroma (pitch class) similarity between candidate beat pairs
- Perceptually weighted power spectrogram (loudness matching)
- Cosine similarity of note sequences before and after candidate points

Loop duration constraints are set interactively (CLI) or use BPM-derived defaults (web).

### Exported File Format

- **Default**: WAV
- **Naming**: `{basename}-{NN}.wav` where NN is a zero-padded sequence number
- **Content**: Loop section only (loop_start to loop_end samples)
- **Output directory**: `{basename}-samples/` next to the source file (CLI) or ZIP download (web)

## Changes from PyMusicLooper

### Removed Features

The following features from the original PyMusicLooper have been removed:

- `play` — Play audio with looping in the terminal
- `play-tagged` — Play audio using metadata tags for loop points
- `split-audio` — Split audio into intro/loop/outro sections
- `extend` — Create extended versions of audio by looping
- `export-points` — Export loop points to terminal or text file
- `tag` — Add metadata tags to audio files
- Metadata tagging features (taglib integration)
- Batch processing support
- `detect-bpm` standalone command (now integrated into the main workflow)
- `--brute-force` option
- `--disable-pruning` option
- `--approx-loop-position` CLI option
- `--min-duration-multiplier` option
- `--output-dir` / `-o` option (auto-derived from filename)
- `--format` option (defaults to WAV)
- `--min-loop-duration` / `--max-loop-duration` CLI flags (now interactive)

### New Behavior

The tool now has a single command with an iterative interactive workflow:

1. Auto-detect BPM and key, suggest loop lengths
2. Interactive duration window prompt (min,max in seconds) — CLI only
3. Detect loops using user-specified constraints
4. Preview individual loops with `0p`, `3p`, etc.
5. Re-detect loops with new duration constraints if needed
6. Export selected loops as WAV files

### Key Differences

| Original PyMusicLooper | Loopscooper |
|------------------------|-------------|
| Multiple subcommands (`play`, `split-audio`, `extend`, etc.) | Single command (positional file argument) |
| BPM detection as separate `detect-bpm` command | BPM auto-detected and displayed at startup |
| Key detection | New: Krumhansl-Schmuckler key detection |
| Loop duration via `--min-duration-multiplier` or CLI flags | Interactive duration window prompt (min,max in seconds) |
| `--approx-loop-position` as CLI flag | Removed |
| `--output-dir` / `-o` for custom output | Auto-derived: `{basename}-samples/` |
| `--format` for export format | Defaults to WAV |
| `--brute-force`, `--disable-pruning` options | Removed |
| One-time selection flow | Iterative: preview → re-detect → preview → export |
| Space-separated selection (`0 2 3`) | Comma-separated selection (`0,2,3`) |
| Output to `{basename}-loops/` | Output to `{basename}-samples/` |
| `--path` flag required | Positional argument (looks in CWD first) |
| CLI only | CLI + Web interface (port 8282) |

## Code Changes

### Project rename: `pymusiclooper` → `loopscooper`

- Package directory renamed from `pymusiclooper/` to `loopscooper/`
- All imports updated across the codebase
- CLI entry point changed from `pymusiclooper` to `loopscooper`
- `pyproject.toml` project name and scripts updated

### `loopscooper/cli.py`

- Removed all subcommands (`play`, `split-audio`, `extend`, `export-points`, `tag`, `play-tagged`, `detect-bpm`, `export-loops`)
- Single CLI command with positional `<filename>` argument
- File resolution: checks CWD first, then treats as relative/absolute path
- Delegates to `handler.run()` for the full interactive workflow

### `loopscooper/handler.py`

- Added BPM detection in `__init__` (stores bpm, suggestions)
- Added `run()` method orchestrating all 6 workflow phases
- Added `prompt_duration_window()` — interactive duration window input with defaults
- Added `interactive_preview()` — loop-by-loop preview with pagination
- Added `prompt_redetect()` — interactive re-detection with duration input
- Added `interactive_export()` — comma-separated index parsing and export
- Changed `parse_loop_selection()` to split by commas instead of whitespace
- Fixed preview to start from `loop_start` (no pre-roll)

### `loopscooper/core.py`

- `MusicLooper.export_single_loop()` — exports a single loop section to a file (unchanged)

### `loopscooper/utils.py`

- `mk_loop_outputdir()` — creates `{basename}-samples/` subdirectory by default (was `{basename}-loops/`)

### `loopscooper/console.py`

- Removed `detect-bpm` from command groups
- Simplified option groups for single-command interface

### `loopscooper/bpm.py` (new)

- `detect_bpm(filepath)` — loads audio, runs librosa beat tracking, returns `(bpm, beat_times)`
- `get_suggested_loop_durations(bpm)` — calculates 1 bar and 2 bars durations assuming 4/4 time

### `loopscooper/key.py` (new)

- `detect_key(filepath)` — detects musical key using the Krumhansl-Schmuckler algorithm
- Compares chroma histogram against 24 major/minor profiles using Pearson correlation
- Returns key string (e.g., "C major", "A minor")

### Web Interface (`web/`)

- `web/server.py` — Flask backend with `/upload`, `/export`, `/download`, `/health` endpoints
- `web/index.html` — Main page with drag-drop zone, info grid, loop table, actions
- `web/static/style.css` — Dark theme, responsive layout
- `web/static/app.js` — Drag-drop, upload, Web Audio API preview, zip export
- `weblooperscoop.service` — Systemd unit file for port 8282

## Dependencies

No new dependencies were added for the core analysis. All required packages remain the same:

- librosa — Audio analysis and loop detection
- numpy — Numerical operations
- soundfile — Audio file I/O
- sounddevice — Audio playback
- rich-click — Styled CLI help
- yt-dlp — YouTube/stream audio extraction
- lazy-loader — Lazy library loading
- flask — Web server (for web frontend)

## Future Considerations

Potential enhancements that could be added:

- Support for exporting intro/outro sections alongside loop files
- Non-interactive mode with pre-selected loop indices
- Support for different time signatures (e.g., 3/4, 6/8)
- Metadata export (JSON file with loop timing information)
- Automatic best-loop detection without interactive menu
- Web interface re-detection with custom duration constraints
- Support for YouTube URL input in web interface

## Session Notes (2026-07-29)

### Goal

Fix two issues: (1) loop default range is 1–2 bars but hip-hop producers typically want 2–4 bars; (2) BPM-dependent loop length can cause loops to sound ~1/4 bar short when the detector overestimates tempo.

### Changes Made (all reverted)

All changes were reverted at end of session because they broke beat/bar detection further. Listed here for reference when re-investigating.

#### `loopscooper/bpm.py`

- Added `four_bars = beat_duration * 16` to `get_suggested_loop_durations()`
- Added `"four_bars"` to the returned dict
- Updated docstring

#### `loopscooper/handler.py`

- Changed `current_min_duration` from `suggestions["one_bar"]` to `suggestions["two_bars"]`
- Changed `current_max_duration` from `suggestions["two_bars"]` to `suggestions["four_bars"]`
- Updated UI labels from "1 bar (4 beats)" / "2 bars (8 beats)" to "2 bars (8 beats)" / "4 bars (16 beats)"
- Changed default prompt values from `(one_bar, two_bars)` to `(two_bars, four_bars)`

#### `loopscooper/analysis.py`

**Beat spacing alignment** (lines ~133–147): After beat detection in normal mode, recomputed `min_loop_duration` and `max_loop_duration` using the **median detected beat spacing** instead of the theoretical BPM formula. The idea was to decouple loop length from BPM accuracy:
```python
if beats.size > 1:
    median_beat_spacing = np.median(np.diff(beats.astype(np.float64)))
    theoretical_fbp = max(1, mlaudio.seconds_to_frames(60.0 / bpm))
    n_beats_min = max(1, round(min_loop_duration / theoretical_fbp))
    n_beats_max = max(1, round(max_loop_duration / theoretical_fbp))
    min_loop_duration = int(round(n_beats_min * median_beat_spacing))
    max_loop_duration = int(round(n_beats_max * median_beat_spacing))
```
This probably caused the regression — `theoretical_fbp` is `int(60/bpm * sr / hop)`, and the ratio `min_loop_duration / theoretical_fbp` doesn't always produce the intended beat count due to floor effects, especially with jittery/irregular beat spacings.

**Dense grid fallback** (lines ~163–173): When beat-based `_find_candidate_pairs` returned empty, tried a stride-based grid of ~1000 evenly-spaced frames as an intermediate fallback before brute force:
```python
stride = max(1, chroma.shape[-1] // 1000)
dense_beats = np.arange(0, chroma.shape[-1], stride, dtype=int)
unproc_candidate_pairs = _find_candidate_pairs(
    chroma, power_db, dense_beats, min_loop_duration, max_loop_duration
)
```
Likely secondary cause — dense grid produces many candidates that the scoring/pruning pipeline wasn't designed for, especially with the already-misaligned min/max frame thresholds.

#### `web/server.py`

- Clamping variables changed from `one_bar`/`two_bars` to `two_bars`/`four_bars`
- Detection passes changed from 1-bar/2-bar ranges to 2-bar/4-bar ranges
- Fallback passes and brute-force tagging updated accordingly
- Added `"four_bars"` to the API response suggestions dict

#### Web Frontend

- `index.html`: Added "4 Bars" display line with `id="four-bars"`
- `app.js`: Added `document.getElementById('four-bars')` update, badge labels changed to "2 Bars" / "4 Bars"
- `style.css`: Badge style `one_bar` → `two_bars` (blue), new `four_bars` style added (green)

### Hypothesis for the ~1/4 bar short issue

The root cause is BPM overestimation by `librosa.beat.beat_track`. When BPM is detected as 140 on a true 120 BPM track:
- `min_loop_duration = time_to_frames(8 * 60/140) = 3.43s` worth of frames
- Actual 2 bars at 120 BPM = 4.0s
- Loop spans 3.43s = 6.86 actual beats = ~1.71 bars, which is 1.14 beats (~1/4 bar) short

The beat-spacing alignment fix was the right idea but the implementation needs to be more robust — perhaps pinning the beat count directly (e.g., always use `n_beats = 8` for min) rather than computing it from the possibly-wrong BPM-derived frame threshold.

### Next Steps (from user)

User will manually invoke the original `pymusiclooper` program with explicit sample min/max length examples to establish ground truth, then re-approach the detection pipeline.


## Session Notes (2026-07-31)

### Loop candidate length discrepancy fix

**Root cause**: Two compounding problems:

1. **BPM mismatch between display and analysis**: `bpm.py::detect_bpm()` and `analysis.py::_analyze_audio()` each called `librosa.beat.beat_track()` independently, potentially returning different BPM values. The displayed bar lengths (from `bpm.py`) could differ from the beat grid used for loop candidate search (from `analysis.py`).

2. **Loop type tagged by pass, not actual duration**: Loops were tagged `one_bar` or `two_bars` based solely on which detection pass found them, not their actual duration relative to the displayed bar lengths.

**Fixes applied**:

1. **`loopscooper/analysis.py`** and **`loopscooper/core.py`**: Added `target_bpm` parameter throughout the analysis pipeline. When provided, it's passed as `start_bpm` to `librosa.beat.beat_track()`, nudging the beat tracker toward the user-visible BPM so the beat grid matches the displayed bar lengths.

2. **`web/server.py`**: 
   - Detection passes now pass the detected BPM as `target_bpm` into `find_loop_pairs()`
   - Primary detection ranges changed from non-overlapping `[one_bar, one_bar*1.5]` / `[two_bars*0.75, two_bars]` to overlapping `[one_bar*0.75, one_bar*1.4]` / `[two_bars*0.75, two_bars]`
   - After all passes complete, loops are re-tagged by actual duration: within 15% of `one_bar` → `one_bar`, within 15% of `two_bars` → `two_bars`, otherwise `unknown`
   - Loops tagged `unknown` are filtered out unless excluding them would leave zero loops
   - Extracted `_detect_loops()` helper function shared between `/upload` and `/reprocess`

### New web features

#### Editable bar length inputs
- The "1 Bar" and "2 Bars" info items now feature editable text inputs with `+` / `−` step buttons (±0.1s per click)
- Users can also type directly into the input fields
- Values are validated to be positive numbers on change

#### Reprocess button (7th info grid item)
- A new "Process" info item in the grid contains a "Re-process" button and a "↺" reset button
- **Re-process**: Calls new `/reprocess` endpoint with the current `one_bar` and `two_bars` values. Re-runs only loop detection (no BPM/key re-detection). Updates the loop candidates table with fresh results.
- **Reset**: Restores the original post-upload analysis data from cache (no server round-trip). Resets bar length inputs and loop table to initial state.

#### `/reprocess` endpoint (`web/server.py`)
- Accepts `POST` with `{sessionId, one_bar?, two_bars?}`
- Reads cached `analysis.json` for file path, BPM, and key
- Uses provided bar lengths (falls back to originals)
- Calls `_detect_loops()` and returns updated `loops[]` and `suggestions`
- Updates the cached `analysis.json` for subsequent exports
- Same security as `/export`: UUID validation, path traversal prevention

#### Frontend
- `loop_type` values of `unknown` shown with a gold/amber badge style
- Bar step buttons styled as semi-transparent controls within each info item
- Process/Reset buttons styled to match the existing dark theme
- Reset triggers `stopPreview()` to halt any playing audio

### Bar-aligned exact-length search (2026-07-31, continued)

**Root cause of remaining length issues**: The original `_find_candidate_pairs()` JIT searches for pairs of chroma-similar beat frames within a min/max duration range. Found loops are "about" the right length but can be slightly too short or too long because any beat pair within the range qualifies.

**Fix**: Added a new JIT function `_find_bar_aligned_pairs()` (`analysis.py`) that enforces `loop_end = loop_start + exact_bar_length_frames`. Instead of searching pairs of beats, it fixes the interval to exactly the bar length and evaluates chroma + loudness similarity at those exact positions. This guarantees every candidate is exactly the target bar length.

**4-phase detection pipeline** (`web/server.py: _detect_loops`):
1. **Bar-aligned exact-length search** (primary, new) — calls `find_loop_pairs()` with `bar_aligned_duration=one_bar`/`two_bars`. End = start + exact bar length. Chroma similarity at exact interval.
2. **Variable-length search** (fallback) — existing overlapping-range search if Phase 1 finds nothing.
3. **Relaxed variable-length** (fallback) — wider ranges, pruning disabled.
4. **Brute force** (last resort) — all frames, no constraints.

**Phase-shift alignment**: After all phases, any loop still tagged `unknown` (duration deviates >15% from bar length) gets cyclically shifted via `MLAudio.phase_shift_loop()` — trims or extends from both ends symmetrically to snap to the nearest bar length. This ensures exported loops are always exactly bar-length even when the fallback paths find imperfect matches.

**Files changed**:
- `loopscooper/analysis.py`: New `_find_bar_aligned_pairs()` JIT function; `find_best_loop_points()` accepts `bar_aligned_duration` param
- `loopscooper/core.py`: `find_loop_pairs()` threads `bar_aligned_duration` through
- `loopscooper/audio.py`: New `phase_shift_loop()` method on `MLAudio`
- `web/server.py`: 4-phase `_detect_loops()` with bar-aligned primary, phase-shift post-processing for unknowns

