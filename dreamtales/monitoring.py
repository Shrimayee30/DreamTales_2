"""Small, metadata-only observability snapshots; no prompts or story text."""
import os
import resource
import sys
import time
from .storycraft import LESSONS, STAGES

class ProcessSampler:
    def __init__(self):
        self.previous = None
        self.cached = None

    def sample(self):
        now = time.monotonic()
        if self.previous and now - self.previous[0] < 1:
            return self.cached
        usage = resource.getrusage(resource.RUSAGE_SELF)
        cpu = usage.ru_utime + usage.ru_stime
        percent = None
        if self.previous:
            percent = round(max(0, (cpu - self.previous[1]) / (now - self.previous[0]) * 100), 2)
        self.previous = (now, cpu)
        self.cached = {
            'cpu_percent': percent,
            'peak_memory_mb': round(usage.ru_maxrss / (1024 ** 2 if sys.platform == 'darwin' else 1024), 1),
            'cpu_count': os.cpu_count(),
            'scope': 'FastAPI process only. Excludes Ollama, the live Kokoro worker, browser, and hosted services.',
        }
        return self.cached

sampler = ProcessSampler()

def snapshot(session):
    now = time.monotonic()
    return {
        'id': session.id, 'phase': session.phase, 'background_phase': session.background_phase,
        'age_s': round(now - session.created, 2), 'planning_s': session.planning_s,
        'startup_s': session.startup_s, 'all_ready_s': session.all_ready_s,
        'current_scene': session.current_scene_id, 'prepared': len(session.scenes),
        'buffer_ahead': sum(n > session.current_scene_id for n in session.views),
        'target': session.fill_to, 'generating_scene': session.in_flight,
        'failed_scene': session.failed_scene_id,
        'moral': LESSONS[session.config._lesson_id],
        'model_confidence': None,
        'confidence_note': 'Unavailable: the story API does not expose calibrated confidence. Repeat similarity is not confidence.',
        'metrics': session.metrics, 'attempts': session.attempts,
        'stages': STAGES,
    }
