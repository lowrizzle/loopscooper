"""BPM detection and loop duration suggestion utilities."""

import logging
from typing import Tuple

import librosa
import numpy as np


def detect_bpm(filepath: str) -> Tuple[float, np.ndarray]:
    """Detect the BPM and beat times for an audio file.

    Args:
        filepath: Path to the audio file.

    Returns:
        A tuple of (bpm, beat_times) where bpm is the estimated tempo
        in beats per minute and beat_times is an array of beat timestamps
        in seconds.
    """
    raw_audio, sampling_rate = librosa.load(filepath, sr=None, mono=True)

    if raw_audio.size == 0:
        raise ValueError(f"No audio data could be loaded from \"{filepath}\".")

    if np.min(raw_audio) == 0 and np.max(raw_audio) == 0:
        raise ValueError(f"\"{filepath}\" only contains silence and cannot be analyzed.")

    mono_signal = raw_audio / np.max(np.abs(raw_audio))

    S = librosa.core.stft(y=mono_signal)
    S_power = np.abs(S) ** 2
    S_weighted = librosa.core.perceptual_weighting(
        S=S_power, frequencies=librosa.fft_frequencies(sr=sampling_rate)
    )
    mel_spectrogram = librosa.feature.melspectrogram(
        S=S_weighted, sr=sampling_rate, n_mels=128, fmax=8000
    )
    onset_env = librosa.onset.onset_strength(S=mel_spectrogram)

    bpm, beats = librosa.beat.beat_track(onset_envelope=onset_env)

    if isinstance(bpm, np.ndarray):
        bpm = float(bpm[0])
    else:
        bpm = float(bpm)

    beat_times = librosa.frames_to_time(beats, sr=sampling_rate)

    return bpm, beat_times


def get_suggested_loop_durations(bpm: float) -> dict:
    """Calculate suggested loop durations based on BPM.

    Assumes 4/4 time signature.

    Args:
        bpm: The beats per minute of the track.

    Returns:
        Dictionary with keys 'beat_duration', 'one_bar', 'two_bars', and 'four_bars'
        representing the duration in seconds.
    """
    beat_duration = 60.0 / bpm
    one_bar = beat_duration * 4  # 4 beats per bar
    two_bars = beat_duration * 8  # 8 beats (2 bars of 4 beats)
    four_bars = beat_duration * 16  # 16 beats (4 bars of 4 beats)

    return {
        "beat_duration": beat_duration,
        "one_bar": one_bar,
        "two_bars": two_bars,
        "four_bars": four_bars,
    }