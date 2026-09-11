---
name: analyze-song-performance
description: Analyze the music and performance in song recordings, especially M4A or MP3 takes of live singing and acoustic guitar. Explain the arrangement and provide grounded rehearsal feedback, including when rough phone audio limits the evidence.
---

# Analyze song performance

Help the musician understand what the song is doing and what to develop in the
performance. The usual input is a rough iPhone M4A or MP3 of singing and acoustic
guitar played together. Prioritize musical effect and execution; recording
quality matters only when it prevents a particular judgment.

## Establish the evidence

Use the supplied take and available musical context. Relevant context includes
the song/version, intended feel, chords, tuning, capo, lyrics, and the particular
passage or skill the musician wants to work on. Recover context from accessible
earlier discussions when the user refers to them, but do not treat earlier
assistant analyses as ground truth. Ask only for missing information that would
materially change the review, and continue with what is available.

Establish whether the environment can actually interpret the audio. Being able
to open, decode, play, transcribe, or plot a file does not by itself establish
listening capability. If actual audio understanding is available, review the
whole take for context and revisit relevant passages. Describe partial coverage
honestly when only an excerpt was reviewed.

Use the local helper for reproducible supporting evidence. Read
[Local audio evidence](references/local-audio-evidence.md) before running it or
interpreting its output. Work on a copy and preserve the original timeline. Use
a fresh task output directory for each recording; keep personal recordings and
generated reviews outside the skill repository.

Default to local processing. Do not add paid API calls or upload recordings as a
fallback. Use existing tools first; if a dependency is unavailable, explain the
specific missing capability instead of embarking on speculative installations.

When listening is unavailable, say so briefly once and provide the useful
analysis the evidence supports. Mark musical interpretation from supplied chords
or lyrics as context-based, and suggested experiments as conditional. Do not
pad missing performance observations with generic coaching disguised as things
heard in this take.

## Explain the music and performance

Default to a detailed review, adjusting emphasis to the material and request:

- Explain the tonal center and harmonic movement where supported, connecting
  chord functions, melody–chord relationships, voicings and rhythmic placement
  to tension, release and the song's character. Explain theory terms through
  their musical effect rather than assuming that naming a chord is sufficient.
- Describe the arrangement's shape: repetition and variation, density, register,
  section contrasts, space and transitions. Do not automatically call fixed
  analysis windows verses or choruses.
- With perceptual evidence, discuss vocal pitch and phrase landings, rhythmic
  placement, articulation, phrasing, dynamics and delivery; guitar pulse,
  changes, articulation and texture; and how voice and guitar support or compete
  with each other. Tie observations to passages actually reviewed.
- Judge a cover primarily as the musician's arrangement. Use the original as
  context when helpful, distinguishing interpretation from mistakes. Do not
  claim to have compared recordings that were not accessible.

Keep sounding chords distinct from capo-relative shapes. Establish which the
user supplied before transposing; do not apply the capo twice. If showing guitar
shapes, label the capo reference and use low E to high E string order. Neither
chroma nor a chord name alone identifies the fingering used.

## Turn observations into useful feedback

Lead with the main musical finding. Include specific strengths worth preserving
and the most consequential opportunities to improve. For an actionable note,
connect the passage or timestamp, what the evidence shows, its musical effect,
and a concrete practice task or arrangement experiment. Prioritize a few useful
next steps over an exhaustive checklist. Explain what to listen for on the next
take so the musician can assess the experiment.

Keep measured facts, hypotheses and artistic preferences distinguishable without
burying the review in caveats. Recorded amplitude is not the singer's dynamics;
periodicity is not proof of rushing; mixture pitch-class energy is not vocal
intonation. Never turn a monophonic pitch estimate or distance to the nearest
semitone in a guitar/vocal mix into a singing accuracy score. Assessing fidelity
to a melody also requires a known target. Expressive scoops and rubato are not
automatically errors, and apparent vocal effort is not a diagnosis of technique.

Use original-file timestamps only when supported by actual coverage; give a
range or passage description when precision is uncertain. Do not invent lyric
quotes or anatomical explanations for an inferred sound. Leave unsupported
dimensions unassessed rather than awarding numerical scores.

Give the review in conversation and save the same substantive review as
`review.md` beside `evidence.json`. Include the recording/version, coverage and
the evidence boundary so the saved review remains understandable on its own.
Link the saved review and offer the prioritized next steps directly, without
requiring the user to read raw measurements.
