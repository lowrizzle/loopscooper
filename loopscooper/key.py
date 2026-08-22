"""Key detection using the Krumhansl-Schmuckler algorithm.

Compares the chroma histogram of an audio file against 24
major/minor key profiles to determine the most likely musical key.
"""

import numpy as np
import librosa


# Krumhansl-Schmuckler (1985) key profiles
MAJOR_PROFILE = np.array([
    6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
    2.52, 5.19, 2.22, 3.83, 3.38, 2.54
])

MINOR_PROFILE = np.array([
    6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
    2.54, 4.75, 3.98, 2.69, 3.36, 2.27
])

KEY_NAMES_MAJOR = [
    'C', 'C#', 'D', 'D#', 'E', 'F',
    'F#', 'G', 'G#', 'A', 'A#', 'B'
]

KEY_NAMES_MINOR = [
    'A', 'A#', 'B', 'C', 'C#', 'D',
    'D#', 'E', 'F', 'F#', 'G', 'G#'
]


def detect_key(filepath: str) -> str:
    """Detect the musical key of an audio file using the Krumhansl-Schmuckler algorithm.

    Args:
        filepath: Path to the audio file.

    Returns:
        A string representing the detected key (e.g., "C major", "A minor").
    """
    audio, sr = librosa.load(filepath, sr=None, mono=True)

    if audio.size == 0:
        raise ValueError(f"No audio data could be loaded from \"{filepath}\".")

    # Compute chroma spectrogram
    S = librosa.stft(audio)
    S_power = np.abs(S) ** 2
    chroma = librosa.feature.chroma_stft(S=S_power, sr=sr)

    # Sum across time to get chroma histogram
    chroma_hist = chroma.sum(axis=1)

    # Normalize to [0, 1]
    max_val = np.max(chroma_hist)
    if max_val > 0:
        chroma_hist = chroma_hist / max_val

    # Compare against all 24 profiles
    best_score = -np.inf
    best_key = "C major"

    for i in range(12):
        major = np.roll(MAJOR_PROFILE, -i)
        minor = np.roll(MINOR_PROFILE, -i)

        corr_major = _pearson_correlation(chroma_hist, major)
        corr_minor = _pearson_correlation(chroma_hist, minor)

        if corr_major > best_score:
            best_score = corr_major
            best_key = f"{KEY_NAMES_MAJOR[i]} major"

        if corr_minor > best_score:
            best_score = corr_minor
            best_key = f"{KEY_NAMES_MINOR[i]} minor"

    return best_key


def _pearson_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Calculate Pearson correlation coefficient, handling constant vectors."""
    x_mean = np.mean(x)
    y_mean = np.mean(y)

    if np.all(x == x_mean) or np.all(y == y_mean):
        return 0.0

    numerator = np.sum((x - x_mean) * (y - y_mean))
    denominator = np.sqrt(
        np.sum((x - x_mean) ** 2) * np.sum((y - y_mean) ** 2)
    )

    if denominator == 0:
        return 0.0

    return float(numerator / denominator)
