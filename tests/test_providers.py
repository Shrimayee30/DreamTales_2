import asyncio,json
import httpx
from dreamtales.core import OllamaCore,LlamaCore
from dreamtales.schema import StoryConfig


def test_local_generation_contract(monkeypatch,core):
    async def scenario():
        config=StoryConfig(dream='A fox in a forest',generation={'temperature':0.4,'top_p':0.8,'max_tokens':350})
        first=await core.generate(config,[],[])
        directions=[{'scene_id':2,'text':'Please add Mr Rabbit'}]
        expected=await core.generate(config,[first],directions)
        draft=expected.model_dump(include={'title','characters','location','artwork'})
        draft['sentences']=['Fox and Rabbit walked home.', 'The soft rain made a quiet song.', 'They sat down beside a tree.']
        async def handler(request):
            payload=json.loads(request.content)
            state=json.loads(payload['messages'][1]['content'])
            assert state['initial_dream']==config.dream
            assert state['latest_applicable_direction']=='Please add Mr Rabbit'
            assert state['previous_scenes'][0]['characters']==['Fox']
            if request.url.path=='/api/chat':
                assert payload['keep_alive']=='5m' and payload['stream'] is False
                assert payload['options']=={'temperature':0.4,'top_p':0.8,'num_predict':350,'num_ctx':8192}
                assert 'scene_id' not in payload['format']['properties']
                return httpx.Response(200,json={'message':{'content':json.dumps(draft)}})
            assert payload['temperature']==0.4 and payload['top_p']==0.8 and payload['max_tokens']==350
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(draft)}}]})
        real=httpx.AsyncClient
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
        for provider in (OllamaCore(),LlamaCore()):
            actual=await provider.generate(config,[first],directions)
            assert actual.story_text==' '.join(draft['sentences']) and actual.scene_id==2
            assert actual.ending is False
    asyncio.run(scenario())

def test_outline_contract_for_both_local_providers(monkeypatch):
    async def scenario():
        config=StoryConfig(dream='Friends sharing a toy')
        events=['Jack the fox wants to share lunch with Robert.', 'Their picnic blanket is too small for both friends.', 'Robert suggests joining two little blankets to make room.', 'Jack and Robert spread their blankets beside each other.', 'Both friends enjoy lunch together on their roomy picnic spot.']
        async def handler(request):
            payload=json.loads(request.content)
            from dreamtales.storycraft import LESSONS
            assert json.loads(payload['messages'][1]['content'])['lesson']==LESSONS[config._lesson_id]
            if request.url.path=='/api/chat':
                assert payload['format']['properties']['events']['minItems']==5
                return httpx.Response(200,json={'message':{'content':json.dumps({'events':events})}})
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'events':events})}}]})
        real=httpx.AsyncClient
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
        for provider in (OllamaCore(),LlamaCore()):
            assert await provider.plan(config)==events
    asyncio.run(scenario())

def test_outline_rejects_code_fragments(monkeypatch):
    import pytest
    async def scenario():
        events=["{'name': 'Jack', 'action': 'gather leaves'}."]*5
        async def handler(request):
            return httpx.Response(200,json={'message':{'content':json.dumps({'events':events})}})
        real=httpx.AsyncClient
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
        with pytest.raises(ValueError,match='complete plain sentences'):
            await OllamaCore().plan(StoryConfig(dream='A fox building a den'))
    asyncio.run(scenario())
