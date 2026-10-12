# DreamTales bedtime studio

DreamTales 0.4 turns a child's imaginary idea into a locally generated five-scene bedtime story. The home screen asks **“What do you want to dream about tonight?”** DreamCore writes each scene in three or four sentences. A child can type a new direction—such as “Please add Mr Rabbit”—while listening, and it begins in the next scene whose generation has not started.

## Start on this computer

```bash
./run.sh
```

Open http://127.0.0.1:8765. The current setup uses the already-installed Ollama model `mistral:7b-instruct` and the installed Kokoro ONNX narrator. There are no preset stories, no cloud story API, and no hidden fallback to a sample story. Model failures produce a recovery message.

## Bedtime controls

- **Keep telling the story** is enabled initially. Scenes continue automatically through scene 5. The first two scenes are prepared before playback. While scene N plays, scene N+2 is prepared in the background.
- **Pause / Resume** pauses the current narrator and holds the next scene. Replay starts that scene's narration again.
- Typing an idea holds automatic continuation. **Add your idea** queues it; **Continue now** also includes any unsubmitted text. The confirmation names the target scene; prepared or in-flight scenes are not rewritten.
- **Voice** and **Background** have separate volume controls. Background sound becomes quieter while the narrator speaks.
- Rain, wind, crickets and ocean waves follow evidence in the actual scene text. **Soft distant thunder** is off by default and plays only when rain and thunder occur in the scene.
- Soundscapes fade between scenes. The final narration fades the background out and stops the story.
- If a browser blocks automatic narration, tap **Listen**. If audio is unavailable, read and advance manually; the application never skips a scene because playback failed.
- Leaving the tab pauses playback. Resume explicitly when you return.
- **Try this scene again** recovers failed generation without losing earlier scenes or the queued story direction.

Background sounds are original procedural audio synthesized through Web Audio on the device; they are not field recordings. DreamVision composes a distinct local SVG for each scene, using its cast, theme, and weather. These are procedural vector illustrations, not diffusion-model images.

## Install on another machine

The web server requires Python 3.9+. The Kokoro worker requires Python 3.10–3.12 and its own environment.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
python3.12 -m venv .venv-voice
.venv-voice/bin/pip install -r requirements-voice.txt
```

Install Ollama and an appropriate local instruction model, or use a local llama.cpp server. Model choice for the Jetson is still open: the installed 7B development model is not a claim that it fits the final 8GB multimodal deployment.

```bash
export DREAMTALES_PROVIDER=ollama
export DREAMTALES_MODEL=mistral:7b-instruct
export DREAMTALES_OLLAMA_URL=http://127.0.0.1:11434
./run.sh
```

For llama.cpp:

```bash
export DREAMTALES_PROVIDER=llama
export DREAMTALES_LLAMA_URL=http://127.0.0.1:8080
./run.sh
```

The [Ollama chat API](https://docs.ollama.com/api/chat) accepts JSON schemas and an explicit model lifetime. DreamTales assigns scene numbers and ending flags in application code and validates the story independently. It keeps the model warm for five minutes by default so the next short scene can start without a reload; set `DREAMTALES_KEEP_ALIVE=0` on a memory-constrained device. Cancellation closes the local request, but immediate server-side inference cancellation is not guaranteed.

## Kokoro narration

This computer already has the voice environment and model files. For a fresh installation, download the two assets from the [official Kokoro ONNX example](https://github.com/thewh1teagle/kokoro-onnx/blob/main/examples/save.py):

```bash
mkdir -p models/kokoro
curl --fail --location https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx -o models/kokoro/kokoro-v1.0.onnx
curl --fail --location https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin -o models/kokoro/voices-v1.0.bin
```

The default voice is `af_heart`, at 0.88 speed, with paragraph pauses and bounded audio peaks. The worker uses ONNX CPU inference, two threads, and disabled ONNX telemetry, and stays loaded for later scenes. The worker exits on cancellation, failure, or server shutdown. It runs without downloading models during storytelling. Optional environment variables:

```bash
export DREAMTALES_VOICE=af_heart
export DREAMTALES_VOICE_PYTHON=/absolute/path/to/voice-environment/bin/python
export DREAMTALES_KOKORO_MODEL=/absolute/path/to/kokoro-v1.0.onnx
export DREAMTALES_KOKORO_VOICES=/absolute/path/to/voices-v1.0.bin
```

If Kokoro is unavailable, a configured Piper executable is used, followed by a local browser voice if available. The UI reports the actual narrator. The existing `DREAMTALES_PIPER_BIN` and `DREAMTALES_PIPER_MODEL` configuration remains supported. Narration is generated from exactly the displayed scene text.

## Test and measure

```bash
.venv/bin/python -m pytest -q
node --test tests/playback.test.cjs
.venv/bin/python -m dreamtales.benchmark --stories 1 --length 5 --output runtime/benchmark.json
```

Node is only needed for frontend tests, not for running the application. The benchmark now requires a real local story model. It records timings and failures without story content. The previous demo benchmark is historical and is not evidence for this version.

## Architecture and data

- `core.py`: local model adapters and bedtime prompt/context.
- `schema.py`: bounded dreams, directions, structured scenes, and allowed sound cues.
- `sync.py`: authoritative history, two-scene lookahead, playback-start replenishment, screening, concurrent media work, and atomic presentation.
- `voice_worker.py`: persistent Kokoro synthesis.
- `soundscape.py`: aligns ambient cues to story text rather than blindly trusting model labels.
- `static/app.js`: playback, automatic continuation, direction queue, and cancel/pause behavior.
- `static/ambience.js`: local procedural sounds, fades, mixing, and narration ducking.

Dreams and directions are normalized and obvious contact details are redacted before model calls or session storage. Unsafe/injection phrases are rejected by a baseline rule screen; generated content is also screened. These limited rules are not a validated child-safety system. Supervised evaluation and stronger semantic moderation remain necessary.

Sessions live in memory only, with no accounts or external analytics. Generated WAVs live in `runtime/audio`; resetting a story or shutting down cleanly removes its audio. After a crash, leftover generated audio can be cleared while the app is stopped. Use one server worker on localhost.

## Current limits

Startup waits for two complete scenes, then a rolling buffer prepares scenes ahead of playback. If generation falls behind, the player waits for the next scene. Directions apply to the next unwritten scene. Voice naturalness is subjective; Kokoro synthesis has been exercised locally, but Jetson latency, memory, and listening quality still need evaluation. Room/projector checks, semantic moderation, generated imagery, and a broader story-coherence study are outstanding.

## Child-friendly scenes and screening

Stories use a 4–8-year-old listening level: three or four sentences, at most 18 words per sentence. A local rule layer screens initial prompts, directions, and all generated scene fields. Alcohol (including beer), tobacco, drugs, and the existing unsafe categories block generation with a clear child-facing message. Unsafe directions cancel the session; start a new story to recover. This rule layer is not a comprehensive semantic moderation model.

## Faster generation and advanced controls

DreamCore now returns only five fields: title, short story, cast, location, and artwork. The app assigns scene numbering, ending flags, and ambience, removing unnecessary model output. DreamTunes reuses a single loaded Kokoro worker across scenes, while retaining two-scene lookahead and parallel image preparation. Warm narration trades higher idle memory for fewer repeated model loads.

Open **Story settings · advanced** before starting a story. Temperature (0–1.2) controls randomness, top-p (0.1–1) controls sampling diversity, and the output budget (300–700 tokens) caps generation. Defaults are 0.65, 0.9, and 400. Settings apply to that new story, are validated on the server, and never disable safety checks. A low token cap may cause truncation and retries; it is not a guaranteed speed setting.

## Stories with a purpose

Each story randomly selects one of 20 original morals from `dreamtales/data/morals.json` and keeps it throughout the session. This is a runtime guidance dataset, not fine-tuning data. The five chronological stages are introduction → problem → proposed solution → trying the solution → success. Short dialogue is encouraged throughout. A separate The End slide displays the selected moral after scene five finishes. Repetitive outline events, similar scene drafts, and individual recycled sentences are checked before playback. Invalid drafts are retried up to three times; these textual checks do not guarantee semantic coherence.

The story outline is planned once before the initial two scenes. This adds a little startup time but gives later scenes specific new events to follow, rather than repeatedly expanding the same moment.

Stories now finish after five scenes. Characters receive personal names and retain them across the story; names supplied in the dream take precedence. The moral appears on its own The End slide after the closing scene. A sleeping cloud marks the header, footer, and browser icon.

 
## Hosted illustrations

DreamVision defaults to OpenAI GPT Image 2 (`gpt-image-2`), using one 1536×1024 medium-quality landscape PNG per scene. Its prompt requests textured picture-book artwork, a clear scene action, and layered scenery. Set OPENAI_API_KEY in the server environment, then restart ./run.sh. Do not put the key in browser code or paste it into chat. For example, in zsh:

```sh
read -s "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY
./run.sh
```

DREAMTALES_IMAGE_MODEL overrides the model; DREAMTALES_IMAGE_PROVIDER=local disables hosted requests. With a configured key, screened scene text, fictional character names and location are sent to OpenAI. Raw child prompts are not sent directly. API usage is billed to that key's account; a new five-scene story requests up to five images. Images are held in session memory and served through local URLs. Images use a common art style, but exact character appearance across independent generations is not guaranteed.

Missing credentials, API errors, invalid image responses, or a 60-second total image deadline use the local vector illustration instead. The caption identifies fallback artwork. No automatic paid-request retries are made. Hosted image integration is covered with mocked API tests; live image quality and latency require a configured API key.

Official API: https://developers.openai.com/api/docs/guides/image-generation

## Listening controls

The player has a 0.60×–1.50× narration speed slider. Recorded Kokoro/Piper audio changes speed immediately with pitch preserved by supporting browsers. Device speech applies the selected speed on replay or the next scene. The setting carries across scenes in the open page.

Read-along highlighting uses approximate word-length-weighted positions against recorded audio time, so changing speed and pausing do not advance the highlight independently of playback. Device voices use browser word-boundary events when available. This is not forced alignment; individual word timing may drift. Highlighting can be switched off.

Advanced generation settings sit below the story button. Rejected prompts and directions open an accessible safety dialog with a clear recovery action; the underlying rule-based safety coverage is unchanged.

Scene 1 must start with “Once upon a time,” and is instructed to introduce only named characters and the setting. The goal and obstacle begin in scene 2. Later scenes cannot restart with the opening phrase. Exact repeated sentences (including short dialogue) and closely reworded longer sentences are rejected before media generation. These textual checks do not guarantee semantic progression for every generated story.
