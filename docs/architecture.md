# DreamTales 0.4: rolling scene buffer

Prepare scenes 1 and 2 completely before playback. When scene N starts playing, POST /playing extends the buffer through min(5, N+2). Thus scene 3 is prepared while scene 1 plays, scene 4 while scene 2 plays, and so on. Repeated signals and replay are idempotent. Manual page turns also replenish the buffer.

The producer task owns ordered commits and checks the updated target after each scene. Text for the next scene overlaps current scene media work. Narration and illustration run concurrently. Separate text-model and narration locks limit resource contention. There are no two-scene batch checkpoints.

Startup readiness is separate from scene generation: scene 1 cannot play until scene 2 is also complete. If production falls behind playback, the player waits without skipping scenes. A background failure preserves prepared scenes; retry resumes from committed history when playback reaches the missing scene. Cancellation awaits child tasks. Unsafe content blocks the session.

New directions target the next scene whose text generation has not begun. If scene 3 is already in flight while scene 1 plays, a new direction starts in scene 4. The UI confirms the assigned scene. Prepared scenes are not rewritten.

DreamCore emits title, three constrained sentences, cast, location, and artwork. Application code supplies scene IDs, ending flags, and sound cues. Temperature, top-p, and token-budget settings remain bounded and cannot bypass safety checks. DreamTunes reuses a loaded Kokoro worker; DreamVision uses the configured hosted image provider when credentials are available, otherwise scene-specific vectors; browser Web Audio synthesizes ambience.

The buffer hides latency only when production keeps up with playback. Startup intentionally waits for two full scenes. Rule-based moderation, idle model memory, and unmeasured Jetson performance remain limitations.

The model schema constrains the sentence array to three items. Each item is bounded in length; the parser joins the sentences into narration text before content screening. This reduces repeated scene failures caused by uncontrolled paragraph length. The retry adds explicit short-sentence guidance.

## Story progression, lessons, and dialogue

A five-beat plan assigns introduction, problem, proposed solution, trying the solution, and success to scenes 1–5 respectively. Each request includes its stage, completed stages, the last scene, the original goal, and full completed scene history. One moral is randomly selected from the 20 original entries in dreamtales/data/morals.json when the story configuration is created. The same moral is reused for planning, retries, prefetch, and the final slide; it is private server state, not a client setting or a training dataset. Independent stories may randomly select the same moral.

A bounded model call expands the beats into concrete events once per story. Near-duplicate outline events are rejected; malformed or repetitive outlines use the five fixed beats as fallback. Planning still adds startup latency.

Before media generation, token-sequence and phrase-overlap checks compare each draft against previous scenes. A sentence-level check also catches even one recycled sentence, even when rearranged or drawn from different scenes. Rejected drafts receive explicit progression feedback, with at most three attempts. These checks catch textual repetition; they do not prove semantic originality or perfect chronological compliance. Short attributed dialogue is encouraged. The moral appears separately on The End slide after scene 5, outside the scene narration.

The final moral is metadata on scene five, not part of its narration. When scene five finishes, the browser displays a separate The End slide with the moral; this is not a sixth generation request.

Scene 1 must start with “Once upon a time,” and is instructed to introduce only named characters and the setting. The goal and obstacle begin in scene 2. Later scenes cannot restart with the opening phrase. Exact repeated sentences (including short dialogue) and closely reworded longer sentences are rejected before media generation. These textual checks do not guarantee semantic progression for every generated story.
