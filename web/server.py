"""Web server for Loopscooper - audio loop detection and export."""
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import atexit
from flask import Flask, jsonify, request, send_file, send_from_directory

# Directory containing server.py, used for static file serving
WEB_DIR = Path(__file__).parent

app = Flask(
    __name__,
    static_folder='static',
    static_url_path='/static',
)

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

SESSION_DIR = Path(tempfile.mkdtemp(prefix='webloopscooper_'))

AUDIO_EXTENSIONS = {
    '.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.aiff', '.ape',
}


@atexit.register
def _cleanup():
    shutil.rmtree(SESSION_DIR, ignore_errors=True)


def _cleanup_session(session_id: str):
    session_path = SESSION_DIR / session_id
    if session_path.exists():
        shutil.rmtree(session_path, ignore_errors=True)


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response


@app.before_request
def validate_origin():
    if request.method == 'POST':
        origin = request.headers.get('Origin', '')
        # Only allow same-origin requests (or no origin for direct requests)
        if origin:
            host = request.headers.get('Host', '')
            if origin not in (f'http://{host}', f'https://{host}'):
                return jsonify({'error': 'Cross-origin requests blocked'}), 403


@app.route('/')
def index():
    return send_from_directory(str(WEB_DIR), 'index.html')


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in AUDIO_EXTENSIONS:
        return jsonify({'error': f'Unsupported file type: {ext}'}), 400

    session_id = str(uuid.uuid4())
    session_dir = SESSION_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    filepath = session_dir / f"audio{ext}"
    file.save(str(filepath))

    # Validate the file is actually valid audio
    try:
        import soundfile
        soundfile.read(str(filepath), frames=100)
    except Exception:
        _cleanup_session(session_id)
        return jsonify({'error': 'Invalid or corrupted audio file'}), 400

    try:
        from loopscooper.bpm import detect_bpm, get_suggested_loop_durations
        from loopscooper.key import detect_key
        from loopscooper.core import MusicLooper

        bpm, _ = detect_bpm(str(filepath))
        suggestions = get_suggested_loop_durations(bpm)
        key = detect_key(str(filepath))

        musiclooper = MusicLooper(filepath=str(filepath))
        audio_duration = musiclooper.mlaudio.total_duration

        # Clamp loop durations to audio length
        one_bar = min(suggestions['one_bar'], audio_duration * 0.35)
        two_bars = min(suggestions['two_bars'], audio_duration * 0.95)
        four_bars = min(suggestions['four_bars'], audio_duration * 0.95)

        all_pairs, loops, loop_pairs = _detect_loops(
            musiclooper, bpm, one_bar, two_bars, four_bars
        )

        if not all_pairs:
            _cleanup_session(session_id)
            return jsonify({
                'error': 'No loops found. Audio may be too short or lack repeating sections.',
                'audioDuration': float(audio_duration),
                'bpm': float(bpm),
            }), 422

        analysis_data = {
            'sessionId': session_id,
            'filename': file.filename,
            'filepath': str(filepath),
            'fileExt': ext,
            'duration': float(musiclooper.mlaudio.total_duration),
            'bpm': float(bpm),
            'key': key,
            'suggestions': {
                'beat_duration': float(suggestions['beat_duration']),
                'one_bar': float(suggestions['one_bar']),
                'two_bars': float(suggestions['two_bars']),
                'four_bars': float(suggestions['four_bars']),
            },
            'loops': loops,
            'loopPairs': loop_pairs,
        }

        with open(session_dir / 'analysis.json', 'w') as f:
            json.dump(analysis_data, f)

        return jsonify(analysis_data)

    except Exception as e:
        _cleanup_session(session_id)
        return jsonify({'error': str(e)}), 500


# 1-bar loops are short enough to sound choppy/incomplete, so only surface them
# when the chroma/loudness match is very strong. 2-bar and 4-bar loops are always
# kept (subject to the normal candidate-quality thresholds inside analysis.py).
_ONE_BAR_SCORE_THRESHOLD = 0.90
_FALLBACK_DURATION_TOLERANCE = 0.15


def _filter_by_type_and_score(pairs):
    """Keep 2-bar/4-bar loops unconditionally; keep 1-bar loops only if they
    score at least _ONE_BAR_SCORE_THRESHOLD; drop anything untagged."""
    kept = []
    for pair in pairs:
        loop_type = getattr(pair, '_loop_type', 'unknown')
        if loop_type in ('two_bars', 'four_bars'):
            kept.append(pair)
        elif loop_type == 'one_bar' and pair.score >= _ONE_BAR_SCORE_THRESHOLD:
            kept.append(pair)
    return kept


def _retag_by_duration(musiclooper, pairs, one_bar, two_bars, four_bars):
    """Tag fallback-search pairs by how close their *actual* duration is to a bar
    length, rather than trusting which search pass produced them (a pass's min/max
    range can still return a pair whose real duration lands closer to a different
    bar length)."""
    for pair in pairs:
        dur = musiclooper.samples_to_seconds(pair.loop_end - pair.loop_start)
        best_label, best_dev = 'unknown', _FALLBACK_DURATION_TOLERANCE
        for label, target in (
            ('four_bars', four_bars), ('two_bars', two_bars), ('one_bar', one_bar)
        ):
            dev = abs(dur - target) / target
            if dev < best_dev:
                best_label, best_dev = label, dev
        pair._loop_type = best_label
    return pairs


def _detect_loops(musiclooper, bpm, one_bar, two_bars, four_bars):
    """Run loop detection anchored to the beat grid, preferring 2-bar and 4-bar loops.

    Args:
        musiclooper: A MusicLooper instance for the audio file.
        bpm: Detected BPM to pass as target_bpm hint.
        one_bar: Target 1-bar duration in seconds (used for fallback tagging only).
        two_bars: Target 2-bar duration in seconds.
        four_bars: Target 4-bar duration in seconds.

    Returns:
        Tuple of (all_pairs, loops, loopPairs) where all_pairs is the raw
        LoopPair list, loops is the API response format, and loopPairs is the
        cached format for export.
    """
    from loopscooper.exceptions import LoopNotFoundError

    all_pairs = []

    # Phase 1: Beat-count-aligned search (primary). Both endpoints of every
    # candidate are real detected beats, exactly N beats apart, so the loop is
    # phase-locked to the track's rhythm instead of merely close to the right
    # duration.
    for label, n_beats in (('four_bars', 16), ('two_bars', 8), ('one_bar', 4)):
        try:
            pairs = musiclooper.find_loop_pairs(target_bpm=bpm, beat_count=n_beats)
            for pair in pairs:
                pair._loop_type = label
            all_pairs.extend(pairs)
        except LoopNotFoundError:
            pass

    all_pairs = _filter_by_type_and_score(all_pairs)

    # Phase 2: Variable-length search (fallback if Phase 1 found nothing usable),
    # tight ranges around 2 and 4 bars.
    if not all_pairs:
        fallback_pairs = []
        for min_dur, max_dur in (
            (four_bars * 0.85, four_bars * 1.1),
            (two_bars * 0.85, two_bars * 1.1),
        ):
            try:
                fallback_pairs.extend(musiclooper.find_loop_pairs(
                    min_duration_multiplier=0.35,
                    min_loop_duration=min_dur,
                    max_loop_duration=max_dur,
                    target_bpm=bpm,
                ))
            except LoopNotFoundError:
                pass
        all_pairs = _filter_by_type_and_score(
            _retag_by_duration(musiclooper, fallback_pairs, one_bar, two_bars, four_bars)
        )

    # Phase 3: Relaxed variable-length fallback, widened to also allow 1-bar loops
    if not all_pairs:
        fallback_pairs = []
        for min_dur, max_dur in (
            (four_bars * 0.7, four_bars * 1.2),
            (two_bars * 0.7, two_bars * 1.2),
            (one_bar * 0.7, one_bar * 1.2),
        ):
            try:
                fallback_pairs.extend(musiclooper.find_loop_pairs(
                    min_duration_multiplier=0.1,
                    min_loop_duration=min_dur,
                    max_loop_duration=max_dur,
                    disable_pruning=True,
                    target_bpm=bpm,
                ))
            except LoopNotFoundError:
                pass
        all_pairs = _filter_by_type_and_score(
            _retag_by_duration(musiclooper, fallback_pairs, one_bar, two_bars, four_bars)
        )

    # Phase 4: Last resort — brute force
    if not all_pairs:
        try:
            fallback_pairs = musiclooper.find_loop_pairs(
                min_duration_multiplier=0.05,
                min_loop_duration=None,
                max_loop_duration=None,
                brute_force=True,
                disable_pruning=True,
            )
        except LoopNotFoundError:
            fallback_pairs = []
        all_pairs = _filter_by_type_and_score(
            _retag_by_duration(musiclooper, fallback_pairs, one_bar, two_bars, four_bars)
        )

    if not all_pairs:
        return [], [], []

    all_pairs.sort(key=lambda pair: pair.score, reverse=True)

    loops = []
    for i, pair in enumerate(all_pairs):
        loops.append({
            'index': i,
            'start_time': musiclooper.samples_to_ftime(pair.loop_start),
            'end_time': musiclooper.samples_to_ftime(pair.loop_end),
            'length': musiclooper.samples_to_ftime(pair.loop_end - pair.loop_start),
            'loop_start': int(pair.loop_start),
            'loop_end': int(pair.loop_end),
            'loop_start_sec': float(musiclooper.samples_to_seconds(pair.loop_start)),
            'loop_end_sec': float(musiclooper.samples_to_seconds(pair.loop_end)),
            'score': float(pair.score),
            'loop_type': getattr(pair, '_loop_type', 'unknown'),
        })

    loop_pairs = [
        {
            'loop_start': int(p.loop_start),
            'loop_end': int(p.loop_end),
            'score': float(p.score),
            'loop_type': getattr(p, '_loop_type', 'unknown'),
        }
        for p in all_pairs
    ]

    return all_pairs, loops, loop_pairs


@app.route('/reprocess', methods=['POST'])
def reprocess():
    """Re-run loop detection with custom bar lengths without re-detecting BPM/key."""
    data = request.json
    session_id = data.get('sessionId')

    if not session_id:
        return jsonify({'error': 'No session ID provided'}), 400

    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid session ID format'}), 400

    session_dir = SESSION_DIR / session_id
    if not session_dir.exists():
        return jsonify({'error': 'Session not found'}), 404

    analysis_path = session_dir / 'analysis.json'
    if not analysis_path.exists():
        return jsonify({'error': 'Analysis data not found for this session'}), 404

    with open(analysis_path) as f:
        analysis = json.load(f)

    filepath = analysis['filepath']
    bpm = analysis['bpm']
    original_suggestions = analysis['suggestions']
    audio_duration = analysis['duration']

    one_bar = data.get('one_bar')
    two_bars = data.get('two_bars')
    four_bars = data.get('four_bars')
    if one_bar is None:
        one_bar = original_suggestions['one_bar']
    if two_bars is None:
        two_bars = original_suggestions['two_bars']
    if four_bars is None:
        four_bars = original_suggestions.get('four_bars', float(two_bars) * 2)

    one_bar = min(float(one_bar), audio_duration * 0.35)
    two_bars = min(float(two_bars), audio_duration * 0.95)
    four_bars = min(float(four_bars), audio_duration * 0.95)

    from loopscooper.core import MusicLooper
    musiclooper = MusicLooper(filepath=filepath)

    all_pairs, loops, loop_pairs = _detect_loops(
        musiclooper, bpm, one_bar, two_bars, four_bars
    )

    if not all_pairs:
        return jsonify({'error': 'No loops found with current parameters.'}), 422

    # Update the cached analysis with new loop data
    analysis['loops'] = loops
    analysis['loopPairs'] = loop_pairs
    analysis['suggestions'] = {
        'beat_duration': 60.0 / bpm,
        'one_bar': float(one_bar),
        'two_bars': float(two_bars),
        'four_bars': float(four_bars),
    }

    with open(analysis_path, 'w') as f:
        json.dump(analysis, f)

    return jsonify({
        'loops': loops,
        'suggestions': analysis['suggestions'],
    })


@app.route('/export', methods=['POST'])
def export():
    data = request.json
    session_id = data.get('sessionId')
    selected_indices = data.get('selectedIndices', [])

    if not session_id:
        return jsonify({'error': 'No session ID provided'}), 400

    # Validate session_id is a valid UUID to prevent path traversal
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid session ID format'}), 400

    session_dir = SESSION_DIR / session_id
    if not session_dir.exists():
        return jsonify({'error': 'Session not found'}), 404

    analysis_path = session_dir / 'analysis.json'
    if not analysis_path.exists():
        return jsonify({'error': 'Analysis data not found for this session'}), 404

    with open(analysis_path) as f:
        analysis = json.load(f)

    filepath = analysis['filepath']
    filename = analysis['filename']
    basename = Path(filename).stem

    # Use cached loop pairs from the analysis data to avoid re-running detection
    loop_pairs = analysis.get('loopPairs', [])
    if not loop_pairs:
        return jsonify({'error': 'No loop data available for this session'}), 400

    try:
        from loopscooper.core import MusicLooper

        musiclooper = MusicLooper(filepath=filepath)

        output_dir = session_dir / 'exports'
        output_dir.mkdir(exist_ok=True)

        zip_path = output_dir / f'{basename}-loops.zip'
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for idx, loop_idx in enumerate(selected_indices, 1):
                if loop_idx < 0 or loop_idx >= len(loop_pairs):
                    continue
                pair = loop_pairs[loop_idx]
                loop_filename = f'{basename}-{idx:02d}.wav'
                loop_path = output_dir / loop_filename

                musiclooper.export_single_loop(
                    pair['loop_start'],
                    pair['loop_end'],
                    str(loop_path),
                    format='WAV',
                )
                zipf.write(loop_path, loop_filename)

        return jsonify({
            'downloadUrl': f'/download/{session_id}/exports/{basename}-loops.zip',
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<session_id>/<path:filename>')
def download(session_id, filename):
    # Validate session_id is a valid UUID to prevent path traversal
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Invalid session ID format'}), 400

    session_dir = SESSION_DIR / session_id
    if not session_dir.exists():
        return jsonify({'error': 'Session not found'}), 404

    # Prevent path traversal: resolve and verify the path is within the session directory
    resolved_session_dir = session_dir.resolve()
    file_path = (resolved_session_dir / filename).resolve()
    if not str(file_path).startswith(str(resolved_session_dir)):
        return jsonify({'error': 'Invalid path'}), 403

    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404

    return send_file(str(file_path), as_attachment=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8282))
    app.run(host='0.0.0.0', port=port, debug=False)
