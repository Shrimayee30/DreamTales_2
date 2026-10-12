# Bedtime build validation

Validated on the development Mac; these results do not measure the Jetson.

- 36 Python regression tests passed.
- 9 Node playback/sound tests passed.
- A real local Mistral story completed three scenes through the browser/API flow.
- Automatic continuation progressed the story without fixed A/B/C choices.
- A new Mr Rabbit direction was submitted while scene two was active and appeared in scene three, alongside the established fox and companion.
- Kokoro produced local 24 kHz narration for all three scenes. A generated sample had a 0.485 maximum absolute sample amplitude, below clipping.
- Scene sound selection retained rain and night ambience for the forest and rejected an unsupported ocean label during a separate model check.
- No browser console errors were observed during the checked flow.

The measured scene preparation times were 68.9, 97.1, and 100.0 seconds, including narration generation. These are substantial pauses; streaming/prefetching and model optimization remain future work. Prefetching will need to discard or regenerate a pending scene whenever the child changes its direction.

See bedtime-live-metrics.json for the metadata-only record. Naturalness, semantic safety, and formal accessibility have not been scored by a listening/user study. Background audio is synthesized ambience rather than a field recording. Illustrations remain decorative.
