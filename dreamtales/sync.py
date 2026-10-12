import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .schema import Scene, StoryConfig
from .core import REPAIR_HINT
from .storycraft import check_progress, RepeatedScene, LESSONS
from .safety import check_scene, UnsafeScene, SAFETY_MESSAGE
from .soundscape import scene_sounds

log = logging.getLogger('dreamtales')


@dataclass
class Session:
    id: str
    config: StoryConfig
    phase: str = 'queued'
    background_phase: str = 'idle'
    scenes: list = field(default_factory=list)
    views: dict = field(default_factory=dict)
    images: dict = field(default_factory=dict)
    decisions: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    task: object = None
    pending_direction: str = ''
    pending_target: Optional[int] = None
    current_scene_id: int = 0
    requested_scene_id: int = 1
    failed_scene_id: Optional[int] = None
    outline: list = field(default_factory=list)
    fill_to: int = 2
    in_flight: int = 0
    startup_ready: bool = False
    created: float = field(default_factory=time.monotonic)

    @property
    def view(self):
        return self.views.get(self.current_scene_id, {})

    @property
    def direction_target(self):
        if not self.current_scene_id:
            return None
        target = max(len(self.scenes), self.in_flight) + 1
        return target if target <= self.config.length else None

    def public(self):
        return {
            'session_id': self.id,
            'phase': self.phase,
            'message': SAFETY_MESSAGE if self.phase == 'blocked' else None,
            'background_phase': self.background_phase,
            'total_scenes': self.config.length,
            'pending_direction': self.pending_direction,
            'direction_target': self.direction_target,
            'checkpoint': False,
            'completed_scene_id': len(self.scenes),
            'buffer_target': self.fill_to,
            'prepared_scenes': sorted(self.views),
            'scene': self.view or None,
        }


class DreamSync:
    """Maintain a rolling buffer with ordered commits and parallel text/media work."""

    def __init__(self, core, vision, tunes):
        self.core, self.vision, self.tunes = core, vision, tunes
        self.core_lock = None
        self.tunes_lock = None

    def _locks(self):
        if self.core_lock is None:
            self.core_lock = asyncio.Lock()
        if self.tunes_lock is None:
            self.tunes_lock = asyncio.Lock()

    def _stage(self, session, phase):
        session.background_phase = phase
        if not session.startup_ready or session.requested_scene_id not in session.views:
            session.phase = phase

    async def _draft(self, session, history, decisions):
        self._locks()
        n = len(history) + 1
        started = time.monotonic()
        rejected = 0
        self._stage(session, 'writing')
        async with self.core_lock:
            repair = ''
            for attempt in range(3):
                planned = (' Planned event for this scene: ' + session.outline[n-1] + ' Advance through this event; do not borrow a later event. Adapt it if the latest child direction changes the goal or cast.') if session.outline else ''
                hint = REPAIR_HINT.set(planned + repair)
                try:
                    candidate = await asyncio.wait_for(
                        self.core.generate(session.config, history, decisions), timeout=185
                    )
                    candidate = Scene.model_validate(candidate.model_dump())
                    if candidate.scene_id != n or candidate.ending != (n == session.config.length):
                        raise ValueError('Invalid story transition')
                    check_scene(candidate)
                    check_progress(candidate, history)
                    if candidate.ending:
                        moral = LESSONS[session.config._lesson_id]
                        candidate = Scene.model_validate({**candidate.model_dump(), 'moral':moral})
                        check_scene(candidate)
                    candidate.ambience = scene_sounds(candidate)
                    return candidate, time.monotonic() - started, rejected
                except UnsafeScene:
                    raise
                except Exception as exc:
                    rejected += 1
                    repair = (' The last draft repeated an earlier scene. Follow this scene purpose with a NEW action and result. Rejected draft: ' + candidate.story_text + ' . Do not paraphrase previous events.' if isinstance(exc, RepeatedScene) else ' The last draft could not be validated. Write exactly three short sentences, at most 12 words each. Return all five required JSON fields.')
                    if n == 1:
                        repair += ' Start with Once upon a time, and describe ONLY named characters and the setting. Save the goal and problem for scene 2.'
                    fields = [(e['loc'], e['type']) for e in exc.errors()] if hasattr(exc, 'errors') else []
                    log.warning('core_rejected type=%s scene=%s attempt=%s fields=%s', type(exc).__name__, n, attempt + 1, fields)
                finally:
                    REPAIR_HINT.reset(hint)
        raise RuntimeError(f'DreamCore could not produce scene {n}')

    async def _narrate(self, scene, session_id):
        self._locks()
        async with self.tunes_lock:
            try:
                return await asyncio.wait_for(self.tunes.generate(scene, session_id), timeout=125)
            except Exception:
                log.warning('narration_fallback scene=%s', scene.scene_id)
                return {'url': None, 'kind': 'device-voice'}

    async def _illustrate(self, scene, config):
        try:
            return await asyncio.wait_for(self.vision.generate(scene, config), timeout=60)
        except asyncio.TimeoutError:
            from .illustration import draw_scene
            return {'svg':draw_scene(scene), 'kind':'scene-vector', 'fallback':True,
                    'alt':f'{scene.title}: {scene.characters[0]} in {scene.location}.'}

    async def _media(self, session, scene):
        started = time.monotonic()
        self._stage(session, 'painting')
        image_task = asyncio.create_task(
            self._illustrate(scene, session.config)
        )
        audio_task = asyncio.create_task(self._narrate(scene, session.id))
        try:
            image, audio = await asyncio.gather(image_task, audio_task)
        except BaseException:
            image_task.cancel()
            audio_task.cancel()
            await asyncio.gather(image_task, audio_task, return_exceptions=True)
            raise
        return image, audio, time.monotonic() - started

    def _commit(self, session, scene, image, audio, core_s, media_s, rejected):
        image = dict(image)
        if 'svg' in image:
            session.images[scene.scene_id] = image.pop('svg')
            image['url'] = f'/api/sessions/{session.id}/images/{scene.scene_id}'
        if 'bytes' in image:
            session.images[scene.scene_id] = (image.pop('bytes'), image.pop('media_type'))
            image['url'] = f'/api/sessions/{session.id}/images/{scene.scene_id}'
        view = {
            **scene.model_dump(),
            'image': image,
            'audio': audio,
            'source': self.core.mode,
            'safety_metadata': {'schema_valid': True, 'screening': 'baseline-rules-v1'},
        }
        session.scenes.append(scene)
        session.views[scene.scene_id] = view
        if len(session.scenes) >= 2:
            session.startup_ready = True
        if session.startup_ready and session.requested_scene_id in session.views:
            session.current_scene_id = session.requested_scene_id
            session.phase = 'ending' if session.view['ending'] else 'ready'
        metric = {
            'scene_id': scene.scene_id,
            'core_s': round(core_s, 3),
            'media_s': round(media_s, 3),
            'total_s': round(core_s + media_s, 3),
            'rejections': rejected,
            'source': self.core.mode,
        }
        session.metrics.append(metric)
        log.info('scene_complete %s', metric)

    def refill(self, session, playing_scene):
        """Called when playback starts, or a reader explicitly advances."""
        session.fill_to = min(session.config.length, max(session.fill_to, playing_scene + 2))
        if session.phase not in ('blocked', 'stopped') and not session.failed_scene_id:
            if session.task is None or session.task.done():
                session.task = asyncio.create_task(self.run(session))

    def _launch(self, session, history, decisions):
        n = len(history) + 1
        decisions = list(decisions)
        if session.pending_direction and session.pending_target == n:
            entry = {'scene_id': n, 'text': session.pending_direction}
            if entry not in decisions:
                decisions.append(entry)
        session.in_flight = n
        return asyncio.create_task(self._draft(session, history, decisions)), decisions

    async def run(self, session):
        """Initially prepare 1–2; playback N extends the buffer through N+2."""
        draft_task = None
        try:
            if not session.outline and hasattr(self.core, 'plan'):
                self._locks()
                self._stage(session, 'planning')
                async with self.core_lock:
                    try:
                        session.outline = await asyncio.wait_for(self.core.plan(session.config), timeout=185)
                    except ValueError:
                        from .storycraft import BEATS
                        session.outline = list(BEATS)
            if len(session.scenes) >= session.fill_to:
                return
            draft_task, decisions = self._launch(session, list(session.scenes), session.decisions)
            while draft_task:
                scene, core_s, rejected = await draft_task
                draft_task = None
                next_decisions = decisions
                if scene.scene_id < session.fill_to:
                    draft_task, next_decisions = self._launch(
                        session, [*session.scenes, scene], decisions)
                image, audio, media_s = await self._media(session, scene)
                self._commit(session, scene, image, audio, core_s, media_s, rejected)
                session.decisions = decisions
                if any(d['scene_id'] == session.pending_target and
                       d['text'] == session.pending_direction for d in decisions):
                    session.pending_direction = ''
                    session.pending_target = None
                decisions = next_decisions
                # Playback may have extended fill_to while media was running.
                if draft_task is None and len(session.scenes) < session.fill_to:
                    draft_task, decisions = self._launch(
                        session, list(session.scenes), session.decisions)
            session.in_flight = 0
            session.failed_scene_id = None
            session.background_phase = 'idle'
        except asyncio.CancelledError:
            session.phase = 'stopped'
            session.background_phase = 'idle'
            raise
        except Exception as exc:
            if isinstance(exc, UnsafeScene):
                session.phase = 'blocked'
                session.background_phase = 'blocked'
            else:
                session.failed_scene_id = len(session.scenes) + 1
                session.background_phase = 'error'
                if not session.startup_ready or session.requested_scene_id not in session.views:
                    session.phase = 'error'
                log.error('pipeline_failure type=%s scene=%s', type(exc).__name__, session.failed_scene_id)
        finally:
            if draft_task:
                if not draft_task.done():
                    draft_task.cancel()
                await asyncio.gather(draft_task, return_exceptions=True)
            session.in_flight = 0
