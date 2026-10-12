import asyncio
import os
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from .safety import SAFETY_MESSAGE
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .core import create_core
from .media import DreamVision, DreamTunes
from .schema import ContinueRequest, RetryRequest, StoryConfig
from .sync import DreamSync, Session

BASE = Path(__file__).parent
RUNTIME = BASE.parent / 'runtime' / 'audio'
RUNTIME.mkdir(parents=True, exist_ok=True)
mode = 'local-ai'
sync = DreamSync(create_core(), DreamVision(), DreamTunes(RUNTIME))
sessions = {}

@asynccontextmanager
async def lifespan(app):
    yield
    tasks = [s.task for s in sessions.values() if s.task and not s.task.done()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    for sid in list(sessions):
        shutil.rmtree(RUNTIME / sid, ignore_errors=True)
    sessions.clear()
    if hasattr(sync.tunes, 'close'):
        await sync.tunes.close()

app = FastAPI(title='DreamTales', version='0.4.0', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    if any(error['type'] == 'child_safety' for error in exc.errors()):
        sid = request.path_params.get('sid')
        if sid in sessions:
            session = sessions[sid]
            if session.task and not session.task.done():
                session.task.cancel()
                await asyncio.gather(session.task, return_exceptions=True)
            session.phase = 'blocked'
            session.background_phase = 'blocked'
            session.pending_direction = ''
        return JSONResponse({'code': 'child_safety', 'detail': SAFETY_MESSAGE}, status_code=422)
    return JSONResponse({'detail': 'Please check your story idea and try again.'}, status_code=422)

@app.get('/api/sessions/{sid}/images/{scene_id}')
async def scene_image(sid: str, scene_id: int):
    svg = find(sid).images.get(scene_id)
    if not svg:
        raise HTTPException(404)
    if isinstance(svg, tuple):
        return Response(svg[0], media_type=svg[1])
    return Response(svg, media_type='image/svg+xml')

@app.middleware('http')
async def guard(request: Request, call_next):
    if request.method in ('POST', 'DELETE'):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        # Bound actual bytes, including chunked requests, before validation.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return JSONResponse({'detail': 'Request too large'}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/api/health')
async def health():
    return {'status': 'ok', 'mode': mode, 'vision': sync.vision.kind, 'version': '0.4.0',
            'narrator': sync.tunes.kind, 'provider': os.getenv('DREAMTALES_PROVIDER', 'ollama'),
            'story_model': getattr(sync.core, 'model', None),
            'voice': os.getenv('DREAMTALES_VOICE', 'af_heart') if sync.tunes.kind == 'kokoro' else None,
            'image_model': sync.vision.model if sync.vision.kind == 'openai-image' else None,
            'configured_image_model': sync.vision.model,
            'hosted_images_ready': sync.vision.kind == 'openai-image',
            'scenes': 5, 'lookahead': 2}

def find(sid):
    if sid not in sessions:
        raise HTTPException(404, 'Story not found. Start a new adventure.')
    return sessions[sid]

@app.post('/api/sessions', status_code=202)
async def create(config: StoryConfig):
    for sid, s in list(sessions.items()):
        if time.monotonic() - s.created > 3600 and (not s.task or s.task.done()):
            del sessions[sid]
            shutil.rmtree(RUNTIME / sid, ignore_errors=True)
    if len(sessions) >= 32 or sum(bool(s.task and not s.task.done()) for s in sessions.values()) >= 4:
        raise HTTPException(429, 'The story studio is busy. Please try again shortly.')
    s = Session(str(uuid4()), config)
    sessions[s.id] = s
    s.task = asyncio.create_task(sync.run(s))
    return s.public()

@app.get('/api/sessions/{sid}')
async def get_session(sid: str):
    return find(sid).public()

@app.get('/api/sessions/{sid}/metrics')
async def metrics(sid: str):
    return {'scenes': find(sid).metrics}

@app.post('/api/sessions/{sid}/playing')
async def playing(sid: str, request: RetryRequest):
    s = find(sid)
    if s.phase not in ('ready', 'ending') or request.scene_id != s.current_scene_id:
        raise HTTPException(409, 'This scene is not ready to play.')
    sync.refill(s, request.scene_id)
    await asyncio.sleep(0)  # Let the worker reserve its next draft before reporting the input target.
    return s.public()

@app.post('/api/sessions/{sid}/continue', status_code=202)
async def continue_story(sid: str, request: ContinueRequest):
    s = find(sid)
    if s.phase != 'ready' or not s.view or s.current_scene_id != request.scene_id or s.current_scene_id >= s.config.length:
        raise HTTPException(409, 'That page has already turned. Please refresh the story.')
    if request.direction:
        queue_story_direction(s, request.direction)
    next_scene = s.current_scene_id + 1
    s.requested_scene_id = next_scene
    if next_scene in s.views:
        s.current_scene_id = next_scene
        s.phase = 'ending' if s.views[next_scene]['ending'] else 'ready'
    elif s.failed_scene_id == next_scene:
        s.phase = 'error'
    else:
        s.phase = s.background_phase if s.background_phase not in ('idle', 'error') else 'queued'
        if not s.task or s.task.done():
            s.task = asyncio.create_task(sync.run(s))
    sync.refill(s, next_scene)
    return s.public()

@app.post('/api/sessions/{sid}/retry', status_code=202)
async def retry_scene(sid: str, request: RetryRequest):
    s = find(sid)
    completed = s.scenes[-1].scene_id if s.scenes else 0
    if s.phase != 'error' or request.scene_id != completed or (s.task and not s.task.done()):
        raise HTTPException(409, 'This story is not waiting for a retry.')
    s.phase = 'queued'
    s.failed_scene_id = None
    s.task = asyncio.create_task(sync.run(s))
    return s.public()


def queue_story_direction(session, direction):
    target = session.direction_target
    if target is None or target <= len(session.scenes):
        raise HTTPException(409, 'That part of the story has already been written.')
    session.pending_direction = direction
    session.pending_target = target
    return target

@app.post('/api/sessions/{sid}/direction')
async def queue_direction(sid: str, request: ContinueRequest):
    s = find(sid)
    if s.phase != 'ready' or s.current_scene_id != request.scene_id:
        raise HTTPException(409, 'The next page is already being written.')
    target = queue_story_direction(s, request.direction)
    return {'pending_direction': s.pending_direction, 'target_scene': target}

@app.delete('/api/sessions/{sid}', status_code=204)
async def stop(sid: str):
    s = find(sid)
    if s.task and not s.task.done():
        s.task.cancel()
        await asyncio.gather(s.task, return_exceptions=True)
    sessions.pop(sid, None)
    shutil.rmtree(RUNTIME / sid, ignore_errors=True)

@app.get('/audio/{sid}/{name}')
async def audio(sid: str, name: str):
    s = find(sid)
    allowed = {f'{scene.scene_id}.wav' for scene in s.scenes}
    path = RUNTIME / sid / name
    if name not in allowed or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type='audio/wav')

app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')

@app.get('/')
async def home():
    return FileResponse(BASE / 'static' / 'index.html')
