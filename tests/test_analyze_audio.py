"""Signal and file-boundary tests for the portable audio evidence helper."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

try:
    import numpy as np
except ImportError:
    np = None


SCRIPT = (Path(__file__).resolve().parents[1] / "skills" /
          "analyze-song-performance" / "scripts" / "analyze_audio.py")


def load_helper():
    spec = importlib.util.spec_from_file_location("song_audio_helper", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(np is None, "NumPy is required for signal analysis tests")
class SignalAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_helper()

    def tone(self, frequency, seconds=3, sample_rate=22050):
        times = np.arange(int(seconds * sample_rate)) / sample_rate
        return 0.3 * np.sin(2 * np.pi * frequency * times)

    def test_silence_has_no_invented_pitch_or_pulse_and_serializes(self):
        result = self.helper.analyze_samples(np.zeros(22050 * 10), 22050)
        json.dumps(result, allow_nan=False)
        self.assertEqual(result["pulse_candidates"], [])
        self.assertEqual(result["pitch_class_energy"]["normalized_energy"], [0] * 12)
        self.assertTrue(result["levels"])
        for level in result["levels"]:
            self.assertEqual(level["rms"], 0)
            self.assertEqual(level["peak"], 0)
        self.assertTrue(all(item["positive_flux"] == 0
                            for item in result["spectral_activity"]))

    def test_level_evidence_tracks_a_known_amplitude_change(self):
        samples = np.concatenate([np.full(22050, 0.1), np.full(22050, 0.5)])
        result = self.helper.analyze_samples(samples, 22050)
        before = [item for item in result["levels"] if item["end_seconds"] <= 0.99]
        after = [item for item in result["levels"] if item["start_seconds"] >= 1.01]
        self.assertTrue(before)
        self.assertTrue(after)
        for items, expected in ((before, 0.1), (after, 0.5)):
            for item in items:
                self.assertAlmostEqual(item["rms"], expected, places=5)
                self.assertAlmostEqual(item["peak"], expected, places=5)

    def test_pitch_windows_omit_unmeasured_tails(self):
        for seconds in (10.01, 10.05, 10.1):
            with self.subTest(seconds=seconds):
                result = self.helper.analyze_samples(self.tone(440, seconds), 22050)
                windows = result["pitch_class_energy"]["windows"]
                self.assertEqual(len(windows), 1)
                self.assertGreater(max(windows[0]["normalized_energy"]), 0)
                self.assertEqual(windows[0]["frame_count"],
                                 result["coverage"]["spectral_frame_count"])

    def test_measured_silent_pitch_windows_are_retained(self):
        result = self.helper.analyze_samples(np.zeros(22050 * 11), 22050)
        windows = result["pitch_class_energy"]["windows"]
        self.assertEqual(len(windows), 2)
        for window in windows:
            self.assertGreater(window["frame_count"], 0)
            self.assertEqual(window["normalized_energy"], [0] * 12)

    def test_isolated_tones_map_to_the_expected_pitch_classes(self):
        for frequency, expected in ((440.0, "A"), (523.251, "C")):
            with self.subTest(frequency=frequency):
                result = self.helper.analyze_samples(self.tone(frequency), 22050)
                pitch = result["pitch_class_energy"]
                energies = pitch["normalized_energy"]
                strongest = pitch["pitch_classes"][int(np.argmax(energies))]
                self.assertEqual(strongest, expected)
                self.assertTrue(np.all(np.isfinite(energies)))
                self.assertTrue(np.all(np.asarray(energies) >= 0))
                self.assertGreater(max(energies), 0)

    def test_click_train_reports_a_compatible_pulse_candidate(self):
        sample_rate = 22050
        samples = np.zeros(sample_rate * 12)
        rng = np.random.default_rng(1234)
        burst = rng.uniform(-1, 1, 330) * np.exp(-np.arange(330) / 55)
        for onset in np.arange(0.5, 11.8, 0.5):
            start = round(onset * sample_rate)
            samples[start:start + len(burst)] += burst
        result = self.helper.analyze_samples(samples, sample_rate)
        candidates = result["pulse_candidates"]
        self.assertTrue(candidates)
        self.assertTrue(any(abs(item["bpm"] - related_bpm) < 3
                            for item in candidates for related_bpm in (60, 120, 240)))
        for item in candidates:
            self.assertGreater(item["autocorrelation"], 0)
            self.assertAlmostEqual(item["bpm"] * item["period_seconds"], 60, places=2)
            self.assertGreaterEqual(item["window_start_seconds"], 0)
            self.assertLessEqual(item["window_end_seconds"], 12)

    def test_excerpt_timestamps_remain_in_original_file_coordinates(self):
        samples = self.tone(440, seconds=2.3)
        result = self.helper.analyze_samples(samples, 22050, start_seconds=17.25)
        end = 17.25 + len(samples) / 22050
        coverage = result["coverage"]
        self.assertEqual(coverage["sample_count"], len(samples))
        self.assertAlmostEqual(coverage["start_seconds"], 17.25)
        self.assertAlmostEqual(coverage["end_seconds"], end)
        self.assertAlmostEqual(coverage["duration_seconds"], len(samples) / 22050)
        self.assertAlmostEqual(result["levels"][0]["start_seconds"], 17.25)
        self.assertAlmostEqual(result["levels"][-1]["end_seconds"], end)
        windows = result["levels"] + result["pitch_class_energy"]["windows"]
        for item in windows:
            self.assertGreaterEqual(item["start_seconds"], 17.25)
            self.assertLessEqual(item["end_seconds"], end + 1e-6)
        for item in result["spectral_activity"]:
            self.assertGreaterEqual(item["time_seconds"], 17.25)
            self.assertLessEqual(item["time_seconds"], end + 1e-6)

    def test_short_clip_does_not_extend_coverage_with_fft_padding(self):
        samples = self.tone(440, seconds=0.02)
        result = self.helper.analyze_samples(samples, 22050, start_seconds=2)
        self.assertAlmostEqual(result["coverage"]["end_seconds"], 2.02)
        self.assertEqual(result["pulse_candidates"], [])
        self.assertTrue(result["levels"])
        self.assertAlmostEqual(result["spectral_activity"][0]["time_seconds"], 2.01)
        for item in result["spectral_activity"]:
            self.assertLessEqual(item["time_seconds"], 2.02)
        json.dumps(result, allow_nan=False)

    def test_invalid_samples_or_timebase_are_rejected(self):
        cases = [
            (np.zeros((2, 100)), 22050, 0),
            (np.array([0, np.nan]), 22050, 0),
            (np.array([0, np.inf]), 22050, 0),
            (np.zeros(100), 0, 0),
            (np.zeros(100), -1, 0),
            (np.zeros(100), 22050, -1),
            (np.zeros(100), 22050, float("nan")),
        ]
        for samples, sample_rate, start in cases:
            with self.subTest(shape=samples.shape, sample_rate=sample_rate, start=start):
                with self.assertRaises(ValueError):
                    self.helper.analyze_samples(samples, sample_rate, start_seconds=start)


@unittest.skipIf(np is None, "NumPy is required for audio helper tests")
class AudioFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_helper()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def make_wav(self, name="recording.wav", seconds=3):
        target = self.root / name
        sample_rate = 22050
        times = np.arange(round(sample_rate * seconds)) / sample_rate
        samples = (10000 * np.sin(2 * np.pi * 440 * times)).astype("<i2")
        with wave.open(str(target), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(samples.tobytes())
        return target

    def run_main(self, source, *extra):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            try:
                status = self.helper.main([
                    str(source), "--output-dir", str(self.root / "results"), *extra,
                ])
            except SystemExit as error:
                status = error.code
        return status, output.getvalue(), errors.getvalue()

    def assert_failed_without_evidence(self, result):
        status, _, errors = result
        self.assertNotEqual(status, 0)
        self.assertTrue(errors)
        self.assertFalse((self.root / "results" / "evidence.json").exists())

    def test_missing_file_fails_without_evidence(self):
        self.assert_failed_without_evidence(self.run_main(self.root / "missing.m4a"))

    def test_missing_external_dependencies_fail_without_evidence(self):
        source = self.make_wav()
        original_which = shutil.which
        for missing in ("ffmpeg", "ffprobe"):
            with self.subTest(dependency=missing):
                def available(command, *args, **kwargs):
                    return None if command == missing else original_which(command, *args, **kwargs)
                with patch.object(shutil, "which", side_effect=available):
                    self.assert_failed_without_evidence(self.run_main(source))

    def test_missing_numpy_is_reported_as_cli_failure(self):
        source = self.make_wav()
        result = subprocess.run(
            [sys.executable, "-S", str(SCRIPT), str(source), "--output-dir",
             str(self.root / "results")], cwd=self.root,
            capture_output=True, text=True, check=False,
        )
        self.assert_failed_without_evidence((result.returncode, result.stdout, result.stderr))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe are required for decoding tests")
    def test_corrupt_audio_fails_without_evidence(self):
        source = self.root / "broken.m4a"
        source.write_bytes(b"This is not an audio file.\x00\xff")
        original = source.read_bytes()
        self.assert_failed_without_evidence(self.run_main(source))
        self.assertEqual(source.read_bytes(), original)

    def test_invalid_excerpt_parameters_fail_without_evidence(self):
        source = self.make_wav()
        for option, value in (("--start", "-1"), ("--duration", "0"),
                              ("--start", "nan"), ("--duration", "inf")):
            with self.subTest(option=option, value=value):
                self.assert_failed_without_evidence(self.run_main(source, option, value))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe are required for decoding tests")
    def test_encoded_m4a_and_mp3_excerpt_and_literal_paths(self):
        wav = self.make_wav(seconds=4)
        for extension, codec in (("m4a", "aac"), ("mp3", "libmp3lame")):
            with self.subTest(extension=extension):
                source = self.root / ("take $(touch INJECTION_MARKER) 'mix'." + extension)
                encoded = subprocess.run(
                    [shutil.which("ffmpeg"), "-v", "error", "-i", str(wav),
                     "-c:a", codec, str(source)], capture_output=True, text=True, check=False,
                )
                self.assertEqual(encoded.returncode, 0, encoded.stderr)
                original = source.read_bytes()
                output = self.root / ("results " + extension)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(source), "--output-dir", str(output),
                     "--start", "1.25", "--duration", "1.5"], cwd=self.root,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                evidence = json.loads((output / "evidence.json").read_text())
                json.dumps(evidence, allow_nan=False)
                self.assertEqual(evidence["schema_version"], "1.0")
                coverage = evidence["coverage"]
                self.assertAlmostEqual(coverage["start_seconds"], 1.25)
                self.assertAlmostEqual(coverage["duration_seconds"], 1.5, delta=0.05)
                self.assertAlmostEqual(coverage["end_seconds"], 2.75, delta=0.05)
                self.assertTrue(evidence["settings"])
                self.assertTrue(evidence["source"])
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse((self.root / "INJECTION_MARKER").exists())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe are required for decoding tests")
    def test_excerpt_beyond_end_fails_without_evidence(self):
        source = self.make_wav(seconds=1)
        self.assert_failed_without_evidence(self.run_main(source, "--start", "5"))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe are required for decoding tests")
    def test_timestamp_gap_preserves_full_recording_and_excerpt_positions(self):
        source = self.root / "timestamp-gap.m4a"
        encoded = subprocess.run(
            [shutil.which("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
             "sine=frequency=440:sample_rate=44100:duration=7", "-af",
             "aselect='lt(t,2)+gte(t,5)'", "-c:a", "aac", str(source)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(encoded.returncode, 0, encoded.stderr)
        # Whole take, inside the gap, across the re-entry, and after the gap.
        for index, (start, duration) in enumerate(((0, 7), (3, 1), (4, 2), (5.5, 1))):
            with self.subTest(start=start, duration=duration):
                output = self.root / f"gap-results-{index}"
                status, _, errors = self.run_main(
                    source, "--output-dir", str(output), "--start", str(start),
                    "--duration", str(duration),
                )
                self.assertEqual(status, 0, errors)
                evidence = json.loads((output / "evidence.json").read_text())
                self.assertAlmostEqual(evidence["coverage"]["end_seconds"],
                                       start + duration, delta=0.05)
                levels = [level for level in evidence["levels"]
                          if level["end_seconds"] - level["start_seconds"] > 0.2]
                silent = [level for level in levels
                          if level["start_seconds"] >= 2.25
                          and level["end_seconds"] <= 4.75]
                sounding = [level for level in levels
                            if level["end_seconds"] <= 1.75
                            or level["start_seconds"] >= 5.25]
                self.assertTrue(silent or sounding)
                for level in silent:
                    self.assertLess(level["rms"], 0.0001)
                for level in sounding:
                    self.assertGreater(level["rms"], 0.05)

    def test_existing_evidence_is_preserved(self):
        source = self.make_wav()
        output = self.root / "results"
        output.mkdir()
        evidence = output / "evidence.json"
        evidence.write_text("previous analysis", encoding="utf-8")
        status, _, errors = self.run_main(source)
        self.assertNotEqual(status, 0)
        self.assertTrue(errors)
        self.assertEqual(evidence.read_text(), "previous analysis")


if __name__ == "__main__":
    unittest.main()
