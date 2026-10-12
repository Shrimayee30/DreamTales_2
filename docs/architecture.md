# DreamTales 0.4: rolling scene buffer

Prepare scenes 1 and 2 completely before playback. When scene N starts playing, POST /playing extends the buffer through min(5, N+2). Thus scene 3 is prepared while scene 1 plays, scene 4 while scene 2 plays, and so on. Repeated signals and replay are idempotent. Manual page turns also replenish the buffer.

The producer task owns ordered commits and checks the updated target after each scene. Text for the next scene overlaps current scene media work. Narration and illustration run concurrently. Separate text-model and narration locks limit resource contention. There are no two-scene batch checkpoints.

Startup readiness is separate from scene generation: scene 1 cannot play until scene 2 is also complete. If production falls behind playback, the player waits without skipping scenes. A background failure preserves prepared scenes; retry resumes from committed history when playback reaches the missing scene. Cancellation awaits child tasks. Unsafe content blocks the session.

New directions target the next scene whose text generation has not begun. If scene 3 is already in flight while scene 1 plays, a new direction starts in scene 4. The UI confirms the assigned scene. Prepared scenes are not rewritten.

DreamCore emits title, three constrained sentences, cast, location, and artwork. Application code supplies scene IDs, ending flags, and sound cues. Temperature, top-p, and token-budget settings remain bounded and cannot bypass safety checks. DreamTunes reuses a loaded Kokoro worker; DreamVision uses the configured hosted image provider when credentials are available, otherwise scene-specific vectors; browser Web Audio synthesizes ambience.

The buffer hides latency only when production keeps up with playback. Startup intentionally waits for two full scenes. Rule-based moderation, idle model memory, and unmeasured Jetson performance remain limitations.

The model schema constrains the sentence array to three items. Each item is bounded in length; the parser joins the sentences into narration text before content screening. This reduces repeated scene failures caused by uncontrolled paragraph length. The retry adds explicit short-sentence guidance.

## Story progression, lessons, and dialogue

A lightweight five-beat plan supplies a distinct purpose for each scene: named characters and a goal, an obstacle and first attempt, a helpful choice, resolution, and peaceful closure. It is supplied with completed scene history on every model request. Lessons cover kindness, sharing, honesty, patience, and teamwork; prompt keywords select a matching lesson, defaulting to kindness. A single bounded model call at startup expands these beats into five concrete planned events. The outline is kept for the session and reused for retries and background generation; it adds startup latency. Malformed outlines fall back to the five fixed beats so planning errors do not prevent playback.

Before media generation, a token-sequence and phrase-overlap check compares the draft against all previous scenes. Substantially similar drafts are rejected and regenerated with explicit progression feedback, up to three attempts. This catches textual repetition; it does not prove semantic originality. Short attributed dialogue is encouraged at selected beats. The final lesson is appended to both displayed text and narration and shown in an ending card.

The final moral is metadata on scene five, not part of its narration. When scene five finishes, the browser displays a separate The End slide with the moral; this is not a sixth generation request.
