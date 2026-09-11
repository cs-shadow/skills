# Local audio evidence

The helper measures the combined recorded signal. It is not an audio-listening
model, source separator, chord recognizer, melody transcriber or singing grader.
Use it to locate and inspect musical questions, together with the user's context.

## Run the helper

Find an existing Python 3.12+ interpreter with NumPy and confirm that `ffmpeg` and
`ffprobe` are on PATH. In Codex desktop, the workspace-dependencies tool can locate
the bundled Python; do not assume another machine has the same absolute path.
An ordinary Python environment with NumPy works equally well. No API key or
network connection is required.

From the skill directory, with the selected interpreter named `python`:

```sh
python scripts/analyze_audio.py "/path/to/My song.m4a" --output-dir "/path/to/new-review"
```

For an excerpt, add `--start 90 --duration 30`. Times are seconds from the
beginning of the original file. Preserve the returned coverage when discussing
or comparing excerpts; a cropped excerpt starts at its original offset, not 0:00.
The input can be M4A or MP3. Use a fresh output directory and inspect the error
if decoding fails; changing an extension does not convert audio.

The helper writes `evidence.json`. Read its metadata, coverage, settings and
limitations before interpreting the time-indexed arrays. It leaves the source
unchanged and uses temporary PCM for analysis, without denoising, normalizing,
pitch correction or time stretching. Its mono analysis signal may lose some
information present in stereo, particularly when channels cancel.
Decoding fills timestamp gaps with silence and trims overlaps to keep evidence
aligned with playback, including excerpts. Inserted silence is not evidence of
a performed rest or hesitation.

Summarize the arrays locally and inspect relevant intervals rather than loading
the entire JSON into conversation. RMS and peak values are linear amplitudes of
the mono analysis signal, not LUFS or isolated source levels. Spectral features
use windowed frames; `spectral_last_time_seconds` is the last frame's timestamp,
not the recording's end. The helper accepts at most one hour per run; select an
explicit excerpt for a longer recording rather than silently truncating it.
Pitch windows report their contributing `frame_count`; windows with no frame
centers are omitted, including very short tails. A measured silent window still
appears with zero energy, so missing coverage is distinct from measured silence.

## What the measurements support

| Evidence | Useful interpretation | Boundary |
| --- | --- | --- |
| Duration and coverage | Locate a passage and distinguish whole-take from excerpt analysis. | Metadata or a successful decode does not establish perceptual access. |
| RMS and peak envelope | Locate recorded level changes, gaps and contrasts worth investigating. | Phone gain control, mic movement, guitar/vocal balance and room sound affect levels. They do not prove expressive dynamics, breath support or which performer changed loudness. |
| Positive spectral flux | Locate changes in spectral activity and possible attacks. | Consonants, noise and guitar attacks can all contribute; it is not a verified strum count. |
| Autocorrelation pulse candidates | Suggest recurring time scales and compare passages cautiously. | A candidate may represent subdivisions, half/double time or a changing strumming pattern. It does not establish meter, groove quality, rushing or intended tempo. |
| Pitch-class energy | Inspect coarse tonal evidence and compare it with supplied harmony. | Both sources and their harmonics contribute; low-frequency FFT resolution is limited. Energy ranking is not a chord progression, key verdict, capo position or sung-note sequence. |

Pulse estimates are bounded hypotheses from analysis windows, not a beat grid or
confidence-calibrated probabilities. Silence and flat evidence should produce no
pulse candidates. Different candidates across windows can reflect ambiguity,
not tempo drift. Fixed windows are summaries, not detected musical sections.
Report tempos as approximate rounded values or ranges; the JSON's numerical
precision does not imply equally precise musical tempo estimates.

Pitch-class energy folds spectral information into twelve classes and loses
octave/register information. Harmonics of a single tone can occupy several
classes. Do not infer an inversion, a specific voicing, or singer accuracy from
these summaries. With supplied chords, discuss what those chords do musically
and describe any agreement with the signal as tentative corroboration.

When listening is unavailable, an appropriate observation is: “The recorded
level drops in this interval; this is a useful place to check whether your
intended section contrast comes across.” It is not: “You lose vocal support
here.” Similarly, propose a counted re-entry as an experiment only when the
musical context makes it relevant, not because a gap proves hesitation.

## Method sources

The helper uses small NumPy calculations, not librosa's implementations. These
references explain the underlying concepts and their intended outputs:

- [FFprobe](https://ffmpeg.org/ffprobe.html): inspect stream/container metadata.
- [RMS](https://librosa.org/doc/0.11.0/generated/librosa.feature.rms.html): frame-level signal amplitude.
- [Onset strength](https://librosa.org/doc/0.11.0/generated/librosa.onset.onset_strength.html): positive spectral change.
- [Chroma filters](https://librosa.org/doc/0.11.0/generated/librosa.filters.chroma.html): pitch-class energy mapping.

These concepts do not validate the helper as a performance assessor. Test its
arithmetic with synthetic signals and judge its musical usefulness separately.
