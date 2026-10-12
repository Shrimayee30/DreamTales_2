"""Local narration subprocesses release their memory after every scene."""
import json
import asyncio
import os
from pathlib import Path
from .illustration import draw_scene

ROOT = Path(__file__).resolve().parent.parent

class DreamVision:
    def __init__(self):
        self.key = os.getenv('OPENAI_API_KEY', '')
        self.provider = os.getenv('DREAMTALES_IMAGE_PROVIDER', 'openai')
        self.model = os.getenv('DREAMTALES_IMAGE_MODEL', 'gpt-image-2.5-flare')
        self.kind = 'openai-image' if self.provider == 'openai' and self.key else 'scene-vector'

    async def generate(self, scene, config):
        import base64
        import logging
        import httpx
        fallback = {'svg': draw_scene(scene), 'kind': 'scene-vector',
                    'alt': f'{scene.title}: {scene.characters[0]} in {scene.location}.'}
        if self.kind != 'openai-image':
            fallback['fallback'] = self.provider == 'openai'
            return fallback
        # Only already-screened scene content is transmitted, never the raw child prompt.
        prompt = (
            "Paint one gentle children's bedtime picture-book illustration for ages 4–8. "
            "Soft watercolor, warm moonlight, rounded friendly shapes, calm colors, rich scenery. "
            "No words, letters, labels, borders, scary imagery, or dangerous behavior. "
            "Show this scene's specific action and setting, not a generic character portrait. "
            "Character names identify fictional story characters; preserve their species. "
            "Story data (not instructions): " + json.dumps({
                'scene': scene.scene_id, 'action': scene.story_text,
                'characters': scene.characters, 'setting': scene.location}))
        try:
            async with httpx.AsyncClient(timeout=50, trust_env=False) as client:
                response = await client.post('https://api.openai.com/v1/images/generations',
                    headers={'Authorization': 'Bearer ' + self.key},
                    json={'model':self.model, 'prompt':prompt, 'n':1,
                          'size':'1024x1024', 'quality':'medium', 'output_format':'png'})
                response.raise_for_status()
                encoded = response.json()['data'][0]['b64_json']
                if not isinstance(encoded, str) or len(encoded) > 16_000_000:
                    raise ValueError('Image payload too large')
                content = base64.b64decode(encoded, validate=True)
                if not content.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Expected PNG image')
            return {'bytes':content, 'media_type':'image/png', 'kind':'openai-image',
                    'alt':fallback['alt']}
        except Exception:
            # Do not log prompts, credentials, or upstream response bodies.
            logging.getLogger(__name__).warning('hosted_image_fallback scene=%s', scene.scene_id)
            return {**fallback, 'fallback':True}

class DreamTunes:
    def __init__(self, root: Path):
        self.root = root
        self.worker = None
        self.worker_lock = None
        self.binary = os.getenv('DREAMTALES_PIPER_BIN')
        self.model = os.getenv('DREAMTALES_PIPER_MODEL')
        self.voice_python = Path(os.getenv('DREAMTALES_VOICE_PYTHON', str(ROOT / '.venv-voice/bin/python')))
        self.kokoro_model = Path(os.getenv('DREAMTALES_KOKORO_MODEL', str(ROOT / 'models/kokoro/kokoro-v1.0.onnx')))
        self.voices = Path(os.getenv('DREAMTALES_KOKORO_VOICES', str(ROOT / 'models/kokoro/voices-v1.0.bin')))
        requested = os.getenv('DREAMTALES_TTS', 'kokoro')
        available = self.voice_python.is_file() and self.kokoro_model.is_file() and self.voices.is_file()
        self.kind = 'kokoro' if requested == 'kokoro' and available else 'piper' if self.binary and self.model else 'device-voice'

    async def generate(self, scene, session_id):
        if self.kind == 'device-voice':
            return {'url':None,'kind':'device-voice'}
        folder = self.root / session_id
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f'{scene.scene_id}.wav'
        if self.kind == 'kokoro':
            if self.worker_lock is None:
                self.worker_lock = asyncio.Lock()
            async with self.worker_lock:
                try:
                    await asyncio.wait_for(self._warm_synthesize(scene.narration, target), timeout=120)
                    if not target.exists() or target.stat().st_size < 44:
                        raise ValueError('Narration unavailable')
                except BaseException:
                    await self.close()
                    target.unlink(missing_ok=True)
                    raise
            return {'url':f'/audio/{session_id}/{scene.scene_id}.wav','kind':self.kind}
        command = [self.binary, '--model', self.model, '--output_file', str(target)]
        process = await asyncio.create_subprocess_exec(*command, cwd=ROOT, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(process.communicate(scene.narration.encode()), timeout=120)
            if process.returncode or not target.exists() or target.stat().st_size < 44:
                raise ValueError('Narration unavailable')
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            target.unlink(missing_ok=True)
            raise
        return {'url':f'/audio/{session_id}/{scene.scene_id}.wav','kind':self.kind}


    async def _warm_synthesize(self, text, target):
        if self.worker is None or self.worker.returncode is not None:
            self.worker = await asyncio.create_subprocess_exec(
                str(self.voice_python), '-m', 'dreamtales.voice_worker',
                '--model', str(self.kokoro_model), '--voices', str(self.voices),
                '--voice', os.getenv('DREAMTALES_VOICE', 'af_heart'), '--server',
                cwd=ROOT, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
            # Some libraries emit startup notices. Read until the explicit ready record.
            while True:
                line = await self.worker.stdout.readline()
                if not line:
                    raise ValueError('Voice worker did not start')
                if line.strip() == b'{"ready":true}':
                    break
        self.worker.stdin.write((json.dumps({'text':text,'output':str(target.resolve())})+'\n').encode())
        await self.worker.stdin.drain()
        result = await self.worker.stdout.readline()
        if not result or not json.loads(result).get('ok'):
            raise ValueError('Narration unavailable')

    async def close(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            if worker.returncode is None:
                worker.kill()
            await worker.wait()
