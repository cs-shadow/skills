#!/usr/bin/env python3
"""Extract bounded, local signal evidence from a mixed song recording.

Requires NumPy, ffmpeg and ffprobe. Measurements describe the recorded mixture,
not isolated performers or the musical correctness of their performance.
"""

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

try:
    import numpy as np
except ImportError as exc:
    raise SystemExit("error: missing dependency: NumPy; use a Python environment with NumPy installed") from exc


SAMPLE_RATE = 22050
FFT_SIZE = 4096
HOP_SIZE = 512
LEVEL_SECONDS = 0.25
PITCH_WINDOW_SECONDS = 10.0
PULSE_WINDOW_SECONDS = 30.0
MAX_SECONDS = 3600.0
PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
LIMITATIONS = [
    "Signal measurements are not a listening-based performance assessment.",
    "All evidence combines voice, guitar, room sound and other recorded sources.",
    "Recorded levels may reflect phone gain control, mic distance or source balance.",
    "Decoding fills timestamp gaps with silence and trims overlaps to preserve timing; a silent interval does not prove a performed rest.",
    "Pulse candidates are periodicity hypotheses with half/double-time and subdivision ambiguity; they are not a beat grid or timing score.",
    "FFT pitch-class energy includes overtones and noise; it does not identify chords, key, capo shapes, sung notes or vocal intonation.",
    "Mono downmixing can cancel opposing stereo signals. Short excerpts and weak or changing pulses limit measurements.",
]


def _number(value):
    return round(float(value), 9)


def _normalized(values):
    total = float(np.sum(values))
    return [_number(v / total) for v in values] if total > 0 else [0.0] * 12


def _pulse_candidates(flux, magnitude, times, sample_rate, start, end):
    """Rank local maxima of centered flux autocorrelation, without beat tracking."""
    results = []
    frame_seconds = HOP_SIZE / sample_rate
    min_lag = max(1, math.ceil(60 / 240 / frame_seconds))
    max_lag = math.floor(60 / 40 / frame_seconds)
    for window_start in np.arange(start, end, PULSE_WINDOW_SECONDS):
        window_end = min(window_start + PULSE_WINDOW_SECONDS, end)
        mask = (times >= window_start) & (times < window_end)
        envelope = flux[mask]
        if window_end - window_start < 6 or len(envelope) <= max_lag + 2:
            continue
        # Avoid presenting tiny stationary-spectrum fluctuations as a pulse.
        baseline = float(np.mean(magnitude[mask]))
        if baseline <= 0 or float(np.std(envelope)) < 0.01 * baseline:
            continue
        envelope = envelope - np.mean(envelope)
        energy = float(envelope @ envelope)
        if energy <= 0:
            continue
        # Only a bounded lag range is needed; do not correlate an hour-long array.
        correlation = np.array([
            float(envelope[:-lag] @ envelope[lag:]) / energy
            for lag in range(max(1, min_lag - 1), max_lag + 2)
        ])
        offset = max(1, min_lag - 1)
        peaks = [lag for lag in range(min_lag, max_lag + 1)
                 if lag > offset and correlation[lag - offset] > 0.1
                 and correlation[lag - offset] >= correlation[lag - offset - 1]
                 and correlation[lag - offset] > correlation[lag - offset + 1]]
        peaks.sort(key=lambda lag: correlation[lag - offset], reverse=True)
        chosen = []
        for lag in peaks:
            bpm = 60 / (lag * frame_seconds)
            if any(abs(bpm - previous) < 4 for previous in chosen):
                continue
            chosen.append(bpm)
            results.append({
                "bpm": _number(bpm),
                "period_seconds": _number(lag * frame_seconds),
                "autocorrelation": _number(correlation[lag - offset]),
                "window_start_seconds": _number(window_start),
                "window_end_seconds": _number(window_end),
            })
            if len(chosen) == 3:
                break
    return results


def analyze_samples(samples, sample_rate, start_seconds=0.0):
    """Return finite evidence for mono, floating PCM samples and source offsets.

    Samples are full-scale-relative PCM (typically -1..1), with no normalization.
    This function performs no file I/O; the CLI adds provenance and settings.
    """
    samples = np.asarray(samples)
    if samples.ndim != 1 or samples.dtype.kind not in "fiu":
        raise ValueError("samples must be a one-dimensional numeric PCM array")
    if not isinstance(sample_rate, (int, np.integer)) or sample_rate < 1:
        raise ValueError("sample_rate must be a positive integer")
    if not math.isfinite(start_seconds) or start_seconds < 0:
        raise ValueError("start_seconds must be finite and nonnegative")
    if len(samples) == 0:
        raise ValueError("recording or excerpt contains no samples")
    if len(samples) > sample_rate * MAX_SECONDS:
        raise ValueError("excerpt exceeds the one-hour limit; select --start and --duration")
    for first in range(0, len(samples), sample_rate * 60):
        if not np.isfinite(samples[first:first + sample_rate * 60]).all():
            raise ValueError("samples contain nonfinite values")
    duration = len(samples) / sample_rate
    end = start_seconds + duration
    levels = []
    level_size = max(1, round(sample_rate * LEVEL_SECONDS))
    for first in range(0, len(samples), level_size):
        chunk = np.asarray(samples[first:first + level_size], dtype=np.float64)
        levels.append({
            "start_seconds": _number(start_seconds + first / sample_rate),
            "end_seconds": _number(start_seconds + (first + len(chunk)) / sample_rate),
            "rms": _number(np.sqrt(np.mean(chunk * chunk))),
            "peak": _number(np.max(np.abs(chunk))),
        })

    starts = np.arange(0, max(1, len(samples) - FFT_SIZE + 1), HOP_SIZE)
    frame_lengths = np.minimum(FFT_SIZE, len(samples) - starts)
    times = start_seconds + (starts + frame_lengths / 2) / sample_rate
    frequencies = np.fft.rfftfreq(FFT_SIZE, 1 / sample_rate)
    valid = (frequencies >= 65.406) & (frequencies <= 2093.005)
    midi = np.rint(69 + 12 * np.log2(frequencies[valid] / 440)).astype(int)
    pitch_index = midi % 12
    window = np.hanning(FFT_SIZE)
    scale = float(np.sum(window))
    flux = np.zeros(len(starts))
    magnitudes = np.zeros(len(starts))
    pitch_windows = np.zeros((max(1, math.ceil(duration / PITCH_WINDOW_SECONDS)), 12))
    pitch_frame_counts = np.zeros(len(pitch_windows), dtype=int)
    previous = None
    for batch_start in range(0, len(starts), 128):
        batch_starts = starts[batch_start:batch_start + 128]
        frames = np.zeros((len(batch_starts), FFT_SIZE))
        for row, first in enumerate(batch_starts):
            chunk = samples[first:first + FFT_SIZE]
            frames[row, :len(chunk)] = chunk
        spectra = np.abs(np.fft.rfft(frames * window, axis=1)) / scale
        for row, spectrum in enumerate(spectra):
            index = batch_start + row
            magnitudes[index] = np.sum(spectrum)
            if previous is not None:
                flux[index] = np.sum(np.maximum(spectrum - previous, 0))
            previous = spectrum
            pitch_window = min(int((times[index] - start_seconds) / PITCH_WINDOW_SECONDS),
                               len(pitch_windows) - 1)
            pitch_windows[pitch_window] += np.bincount(
                pitch_index, weights=spectrum[valid] ** 2, minlength=12)
            pitch_frame_counts[pitch_window] += 1

    return {
        "coverage": {
            "start_seconds": _number(start_seconds), "end_seconds": _number(end),
            "duration_seconds": _number(duration), "sample_count": len(samples),
            "spectral_frame_count": len(starts),
            "spectral_last_time_seconds": _number(times[-1]),
        },
        "levels": levels,
        "spectral_activity": [{"time_seconds": _number(t), "positive_flux": _number(f)}
                              for t, f in zip(times, flux)],
        "pulse_candidates": _pulse_candidates(flux, magnitudes, times, sample_rate,
                                               start_seconds, end),
        "pitch_class_energy": {
            "pitch_classes": PITCH_CLASSES.copy(),
            "normalized_energy": _normalized(np.sum(pitch_windows, axis=0)),
            "windows": [{
                "start_seconds": _number(start_seconds + index * PITCH_WINDOW_SECONDS),
                "end_seconds": _number(min(end, start_seconds + (index + 1) * PITCH_WINDOW_SECONDS)),
                "frame_count": int(pitch_frame_counts[index]),
                "normalized_energy": _normalized(values),
            } for index, values in enumerate(pitch_windows) if pitch_frame_counts[index] > 0],
        },
    }


def _run(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("audio command exceeded the five-minute limit") from exc
    if result.returncode:
        detail = result.stderr.strip()[-2000:]
        raise ValueError(f"{Path(command[0]).name} failed: {detail}")
    return result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source M4A, MP3 or other FFmpeg-readable audio")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--start", type=float, default=0.0, help="Excerpt start in original-file seconds")
    parser.add_argument("--duration", type=float, help="Excerpt length in seconds, at most 3600")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.start) or args.start < 0:
            raise ValueError("--start must be finite and nonnegative")
        if args.duration is not None and (not math.isfinite(args.duration)
                                         or not 0 < args.duration <= MAX_SECONDS):
            raise ValueError("--duration must be positive, finite and at most 3600 seconds")
        source = args.input.expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"input file does not exist: {source}")
        output_dir = args.output_dir.expanduser().resolve()
        destination = output_dir / "evidence.json"
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"refusing to overwrite existing output: {destination}")
        executables = {}
        for name in ("ffmpeg", "ffprobe"):
            executables[name] = shutil.which(name)
            if not executables[name]:
                raise ValueError(f"missing dependency: {name}; no installation was attempted")
        probe = json.loads(_run([
            executables["ffprobe"], "-v", "error", "-protocol_whitelist", "file,pipe",
            "-select_streams", "a:0",
            "-show_entries", "format=duration,format_name:stream=codec_name,sample_rate,channels,duration,start_time",
            "-of", "json", str(source),
        ]))
        if not probe.get("streams"):
            raise ValueError("input contains no readable audio stream")
        raw_duration = probe.get("format", {}).get("duration")
        source_duration = float(raw_duration) if raw_duration not in (None, "N/A") else None
        if source_duration is not None:
            if args.start >= source_duration:
                raise ValueError("--start is at or beyond the end of the recording")
            if args.duration is None and source_duration - args.start > MAX_SECONDS:
                raise ValueError("recording exceeds the one-hour limit; select --start and --duration")
        with tempfile.TemporaryDirectory(prefix="song-evidence-") as temporary:
            pcm_path = Path(temporary) / "analysis.f32"
            _run([
                executables["ffmpeg"], "-v", "error", "-nostdin", "-xerror",
                "-protocol_whitelist", "file,pipe",
                "-i", str(source), "-ss", str(args.start), "-t",
                str(args.duration if args.duration is not None else MAX_SECONDS + 1),
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                "-af", "aresample=async=1:first_pts=0",
                "-c:a", "pcm_f32le", "-f", "f32le", str(pcm_path),
            ])
            if pcm_path.stat().st_size == 0:
                raise ValueError("recording or excerpt decoded to no samples")
            samples = np.memmap(pcm_path, dtype="<f4", mode="r")
            try:
                result = analyze_samples(samples, SAMPLE_RATE, args.start)
            finally:
                samples._mmap.close()
        result.update({
            "schema_version": "1.0",
            "source": {"path": str(source), "size_bytes": source.stat().st_size,
                       "probe": probe},
            "settings": {
                "sample_rate": SAMPLE_RATE, "channels": 1, "pcm_format": "float32",
                "normalization": False, "denoising": False, "tempo_change": False,
                "timestamp_alignment": "fill gaps and trim overlaps without time stretching",
                "level_window_seconds": LEVEL_SECONDS, "fft_size": FFT_SIZE,
                "hop_size": HOP_SIZE, "fft_window": "Hann",
                "spectral_framing": "complete frames; one zero-padded frame only if shorter than FFT size",
                "pitch_class_frequency_range_hz": [65.406, 2093.005],
                "pitch_class_reference_a4_hz": 440.0,
                "pitch_class_window_seconds": PITCH_WINDOW_SECONDS,
                "pulse_window_seconds": PULSE_WINDOW_SECONDS,
                "pulse_bpm_range": [40, 240], "max_duration_seconds": MAX_SECONDS,
                "requested_start_seconds": args.start, "requested_duration_seconds": args.duration,
            },
            "limitations": LIMITATIONS,
        })
        serialized = json.dumps(result, indent=2, allow_nan=False) + "\n"
        output_dir.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as output:
            output.write(serialized)
        print(destination)
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
