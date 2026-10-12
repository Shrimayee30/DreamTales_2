import asyncio
import xml.etree.ElementTree as ET
import pytest
from pydantic import ValidationError
from dreamtales.schema import StoryConfig, Scene
from dreamtales.media import DreamVision
from dreamtales.safety import check_scene, UnsafeScene
from test_api import client, ready

@pytest.mark.parametrize('idea', ['beer', 'A fox drinking BEER', 'A rabbit with vodka', 'A cat with cigarettes', 'A fox with ｂｅｅｒ', 'A fox with be\u200ber'])
def test_unsafe_initial_input_never_starts_core(client, core, idea):
    response=client.post('/api/sessions',json={'dream':idea})
    assert response.status_code==422
    assert response.json()['code']=='child_safety'
    assert 'not safe for kids' in response.json()['detail']
    assert not core.calls

def test_direction_blocks_session_and_continuation(client):
    sid=client.post('/api/sessions',json={'dream':'A fox in a forest'}).json()['session_id']
    ready(client,sid)
    url=f'/api/sessions/{sid}'
    response=client.post(url+'/direction',json={'scene_id':1,'direction':'Add beer'})
    assert response.json()['code']=='child_safety'
    assert client.get(url).json()['phase']=='blocked'
    assert client.post(url+'/continue',json={'scene_id':1}).status_code==409
    assert client.post(url+'/retry',json={'scene_id':1}).status_code==409

def test_safe_words_do_not_match_substrings():
    StoryConfig(dream='A bear eating berries beside a rumbling stream')

def test_generated_alcohol_blocked(core):
    scene=asyncio.run(core.generate(StoryConfig(dream='A quiet forest'),[],[]))
    scene=scene.model_copy(update={'image_prompt':'A fox holding beer'})
    with pytest.raises(UnsafeScene): check_scene(scene)

def test_images_change_and_are_valid_svg(core):
    async def run():
        config=StoryConfig(dream='A fox in a forest')
        first=await core.generate(config,[],[])
        second=await core.generate(config,[first],[{'scene_id':2,'text':'Add Mr Rabbit'}])
        a=await DreamVision().generate(first,config)
        b=await DreamVision().generate(second,config)
        assert a['svg']!=b['svg']
        ET.fromstring(a['svg']);ET.fromstring(b['svg'])
        assert 'Mr Rabbit' in b['svg'] and 'Mr Rabbit' not in a['svg']
    asyncio.run(run())

def test_image_endpoint_returns_scene_art(client):
    sid=client.post('/api/sessions',json={'dream':'A quiet forest'}).json()['session_id']
    data=ready(client,sid)
    response=client.get(data['scene']['image']['url'])
    assert response.status_code==200
    assert response.headers['content-type'].startswith('image/svg+xml')
    ET.fromstring(response.text)

def test_long_sentences_are_rejected(core):
    scene=asyncio.run(core.generate(StoryConfig(dream='A quiet forest'),[],[]))
    text=' '.join(['soft']*19)+'. Fox sat down. Rabbit smiled.'
    with pytest.raises(ValidationError):
        Scene.model_validate({**scene.model_dump(),'story_text':text,'narration':text})

@pytest.mark.parametrize('settings',[{'temperature':-1},{'temperature':1.3},{'top_p':0},{'max_tokens':50},{'max_tokens':800}])
def test_generation_settings_are_bounded(settings):
    with pytest.raises(ValidationError):
        StoryConfig(dream='A quiet forest', generation=settings)

def test_settings_do_not_bypass_safety():
    with pytest.raises(ValidationError):
        StoryConfig(dream='A fox drinking beer',generation={'temperature':1.2,'top_p':1.0,'max_tokens':700})
