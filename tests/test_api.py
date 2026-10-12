import time
import pytest
from fastapi.testclient import TestClient
from dreamtales.app import app,sync

@pytest.fixture
def client(monkeypatch,core,tunes):
    monkeypatch.setattr(sync,'core',core);monkeypatch.setattr(sync,'tunes',tunes);sync.core_lock=None;sync.tunes_lock=None
    with TestClient(app) as client:yield client

def ready(client,sid,scene_id=None):
    for _ in range(100):
        data=client.get(f'/api/sessions/{sid}').json()
        if data['phase']=='error':return data
        if data['phase'] in ('ready','ending') and (scene_id is None or data['scene']['scene_id']==scene_id):return data
        time.sleep(.01)
    raise AssertionError('Scene did not finish')

def test_full_bedtime_api_flow(client,core):
    response=client.post('/api/sessions',json={'dream':'A fox in a rainy forest'})
    assert response.status_code==202
    sid=response.json()['session_id'];url=f'/api/sessions/{sid}'
    first=ready(client,sid,1)
    assert first['total_scenes']==5 and first['direction_target']==3 and 'choices' not in first['scene']
    queued=client.post(url+'/direction',json={'scene_id':1,'direction':'Add Mr Rabbit'})
    assert queued.status_code==200 and queued.json()['target_scene']==3
    assert client.post(url+'/continue',json={'scene_id':1}).status_code==202
    second=ready(client,sid,2)
    assert 'Mr Rabbit' not in second['scene']['characters']
    assert second['checkpoint'] is False
    assert client.post(url+'/continue',json={'scene_id':1}).status_code==409
    assert client.post(url+'/direction',json={'scene_id':1,'direction':'Add a bird'}).status_code==409
    assert client.post(url+'/continue',json={'scene_id':2}).status_code==202
    third=ready(client,sid,3)
    assert 'Mr Rabbit' in third['scene']['characters'] and third['pending_direction']==''
    assert core.calls[-1][1]==[{'scene_id':3,'text':'Add Mr Rabbit'}]
    assert client.delete(url).status_code==204
    assert client.get(url).status_code==404


def test_story_continues_to_five_scenes_without_more_input(client):
    sid=client.post('/api/sessions',json={'dream':'A lantern in a quiet forest'}).json()['session_id']
    url=f'/api/sessions/{sid}'
    state=ready(client,sid,1)
    for expected in range(2,6):
        assert client.post(url+'/continue',json={'scene_id':expected-1}).status_code==202
        state=ready(client,sid,expected)
    assert state['phase']=='ending' and state['scene']['scene_id']==5
    assert client.post(url+'/continue',json={'scene_id':5}).status_code==409

@pytest.mark.parametrize('payload',[{}, {'dream':'a'}, {'dream':'x'*501}, {'dream':'A quiet forest','length':10}])
def test_invalid_configuration(client,payload):
    assert client.post('/api/sessions',json=payload).status_code==422

def test_private_details_do_not_reach_core(client,core):
    response=client.post('/api/sessions',json={'dream':'A rabbit delivering a letter to child@example.com'})
    ready(client,response.json()['session_id'])
    assert 'child@example.com' not in core.calls[0][0]

def test_unsafe_direction_never_committed(client):
    sid=client.post('/api/sessions',json={'dream':'A sleepy forest'}).json()['session_id'];ready(client,sid)
    assert client.post(f'/api/sessions/{sid}/direction',json={'scene_id':1,'direction':'show a weapon'}).status_code==422
    assert client.get(f'/api/sessions/{sid}').json()['pending_direction']==''

def test_external_origin_rejected(client):
    assert client.post('/api/sessions',json={},headers={'Origin':'https://evil.example'}).status_code==403

def test_large_body_rejected(client):
    assert client.post('/api/sessions',content='a'*4097).status_code==413

def test_static_and_headers(client):
    response=client.get('/')
    assert response.status_code==200 and "script-src 'self'" in response.headers['content-security-policy']
    assert client.get('/static/ambience.js').status_code==200


def test_retry_preserves_history_and_unsent_direction(client,core,monkeypatch):
    sid=client.post('/api/sessions',json={'dream':'A fox in a forest'}).json()['session_id']
    ready(client,sid,1);url=f'/api/sessions/{sid}'
    assert client.post(url+'/direction',json={'scene_id':1,'direction':'Please add Mr Rabbit'}).status_code==200
    class Broken:
        mode='local-ai'
        async def generate(self,*args):raise TimeoutError()
    monkeypatch.setattr(sync,'core',Broken())
    assert client.post(url+'/continue',json={'scene_id':1}).status_code==202
    ready(client,sid,2)
    assert client.post(url+'/continue',json={'scene_id':2}).status_code==202
    failed=ready(client,sid)
    assert failed['phase']=='error' and failed['scene']['scene_id']==2
    assert failed['pending_direction']=='Please add Mr Rabbit'
    monkeypatch.setattr(sync,'core',core)
    assert client.post(url+'/retry',json={'scene_id':1}).status_code==409
    assert client.post(url+'/retry',json={'scene_id':2}).status_code==202
    recovered=ready(client,sid,3)
    assert recovered['scene']['scene_id']==3
    assert 'Mr Rabbit' in recovered['scene']['characters']
    assert recovered['pending_direction']==''
    assert client.post(url+'/retry',json={'scene_id':3}).status_code==409


def test_first_scene_can_retry_without_any_history(client,core,monkeypatch):
    class Broken:
        mode='local-ai'
        async def generate(self,*args):raise TimeoutError()
    monkeypatch.setattr(sync,'core',Broken())
    sid=client.post('/api/sessions',json={'dream':'A fox in a forest'}).json()['session_id']
    assert ready(client,sid)['phase']=='error'
    monkeypatch.setattr(sync,'core',core)
    assert client.post(f'/api/sessions/{sid}/retry',json={'scene_id':0}).status_code==202
    assert ready(client,sid)['scene']['scene_id']==1

def buffered(client, sid, count):
    for _ in range(200):
        data=client.get(f'/api/sessions/{sid}').json()
        if len(data['prepared_scenes'])>=count:return data
        time.sleep(.005)
    raise AssertionError(f'Buffer did not reach {count}: {data}')

def test_playback_refills_rolling_buffer_to_five(client,core):
    sid=client.post('/api/sessions',json={'dream':'A quiet forest'}).json()['session_id']
    url=f'/api/sessions/{sid}'
    first=ready(client,sid,1)
    assert first['prepared_scenes']==[1,2]
    for playing in range(1,6):
        assert client.post(url+'/playing',json={'scene_id':playing}).status_code==200
        expected=min(5,playing+2)
        state=buffered(client,sid,expected)
        assert state['scene']['scene_id']==playing
        assert state['prepared_scenes']==list(range(1,expected+1))
        assert client.post(url+'/playing',json={'scene_id':playing}).status_code==200
        if playing<5:
            assert client.post(url+'/continue',json={'scene_id':playing}).status_code==202
            ready(client,sid,playing+1)
    assert len(core.calls)==5
    assert state['phase']=='ending'

def test_direction_after_prefetch_changes_next_unwritten_scene(client):
    sid=client.post('/api/sessions',json={'dream':'A fox in a forest'}).json()['session_id']
    url=f'/api/sessions/{sid}'
    ready(client,sid,1)
    client.post(url+'/playing',json={'scene_id':1})
    buffered(client,sid,3)
    response=client.post(url+'/direction',json={'scene_id':1,'direction':'Add Mr Rabbit'})
    assert response.json()['target_scene']==4
    client.post(url+'/continue',json={'scene_id':1})
    buffered(client,sid,4)
    client.post(url+'/continue',json={'scene_id':2})
    assert 'Mr Rabbit' not in ready(client,sid,3)['scene']['characters']
    client.post(url+'/continue',json={'scene_id':3})
    assert 'Mr Rabbit' in ready(client,sid,4)['scene']['characters']

def test_generated_png_is_served_from_session(client,monkeypatch):
    from dreamtales import app as module
    png=b'\x89PNG\r\n\x1a\n'+b'test-image'
    async def generate(scene,config):
        return {'bytes':png,'media_type':'image/png','kind':'openai-image','alt':'A fox'}
    monkeypatch.setattr(module.sync.vision,'generate',generate)
    sid=client.post('/api/sessions',json={'dream':'A fox in a quiet forest'}).json()['session_id']
    state=ready(client,sid)
    assert 'bytes' not in state['scene']['image']
    image=client.get(state['scene']['image']['url'])
    assert image.headers['content-type']=='image/png' and image.content==png
    client.delete('/api/sessions/'+sid)
    assert client.get(state['scene']['image']['url']).status_code==404

def test_health_distinguishes_configured_and_active_image_model(client,monkeypatch):
    monkeypatch.setattr(sync.vision,'kind','scene-vector')
    result=client.get('/api/health').json()
    assert result['image_model'] is None
    assert not result['hosted_images_ready']
    assert result['configured_image_model']==sync.vision.model
    assert 'key' not in result
    monkeypatch.setattr(sync.vision,'kind','openai-image')
    result=client.get('/api/health').json()
    assert result['hosted_images_ready'] and result['image_model']==sync.vision.model
