import asyncio,base64,json
import httpx,pytest
from dreamtales.media import DreamVision
from dreamtales.schema import StoryConfig

@pytest.mark.parametrize('failure',[None,'http','invalid'])
def test_hosted_images_and_fallback(monkeypatch,core,failure):
    async def run():
        monkeypatch.setenv('OPENAI_API_KEY','test-only-key')
        monkeypatch.setenv('DREAMTALES_IMAGE_PROVIDER','openai')
        config=StoryConfig(dream='A quiet fox in a forest')
        scene=await core.generate(config,[],[])
        png=b'\x89PNG\r\n\x1a\n'+b'test-image'
        async def handler(request):
            assert request.url==httpx.URL('https://api.openai.com/v1/images/generations')
            body=json.loads(request.content)
            assert scene.story_text in body['prompt']
            assert config.dream not in body['prompt']
            assert body['n']==1 and body['quality']=='medium'
            assert body['model']=='gpt-image-2'
            assert body['size']=='1536x1024'
            if failure=='http':return httpx.Response(429)
            return httpx.Response(200,json={'data':[{'b64_json':'bad!' if failure else base64.b64encode(png).decode()}]})
        real=httpx.AsyncClient
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
        result=await DreamVision().generate(scene,config)
        if failure:
            assert result['fallback'] and result['kind']=='scene-vector'
        else:
            assert result['bytes']==png and result['media_type']=='image/png'
    asyncio.run(run())

def test_missing_key_keeps_local_images(monkeypatch,core):
    async def run():
        monkeypatch.delenv('OPENAI_API_KEY',raising=False)
        cfg=StoryConfig(dream='A quiet fox in a forest')
        result=await DreamVision().generate(await core.generate(cfg,[],[]),cfg)
        assert result['kind']=='scene-vector' and 'svg' in result
    asyncio.run(run())
