# Rolling-buffer validation

Live Ollama and Kokoro integration completed all ten scenes. Each scene image and narration URL was fetched successfully. First playback readiness required scenes 1 and 2; it occurred at 44.4 seconds. The test advanced immediately rather than waiting for audio to finish, exercising buffer underruns and recovery. Scene 10 arrived at 302.6 seconds and was marked as the ending. The temporary test session was deleted.

Automated coverage: 61 backend tests and 14 browser playback tests, including ten-scene autoplay with no manual continuation, idempotent playback-start signals, startup gating, extension while generation is busy, direction assignment to unwritten scenes, and startup failure recovery.

Timing is a single development-Mac sample, not a guarantee of gapless playback or Jetson performance.
