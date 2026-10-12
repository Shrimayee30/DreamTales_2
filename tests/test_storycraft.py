import asyncio,json
import pytest
from dreamtales.core import parse_scene, messages, REPAIR_HINT
from dreamtales.schema import StoryConfig
from dreamtales.storycraft import check_progress, RepeatedScene, story_plan, LESSONS
from dreamtales.sync import DreamSync, Session
from dreamtales.media import DreamVision

def test_moral_is_randomly_selected_once_and_private(monkeypatch):
    import dreamtales.storycraft as craft
    picks=iter(['sharing','patience'])
    monkeypatch.setattr(craft.secrets,'choice',lambda choices:next(picks))
    first=StoryConfig(dream='A fox under the stars')
    second=StoryConfig(dream=first.dream)
    assert first._lesson_id=='sharing' and second._lesson_id=='patience'
    assert story_plan(first,[])['lesson']==LESSONS['sharing']
    assert first.model_copy()._lesson_id=='sharing'
    assert '_lesson_id' not in first.model_dump()

def test_moral_collection_is_safe_and_varied():
    from dreamtales.safety import sanitize_request
    assert len(LESSONS)>=20 and len(set(LESSONS.values()))==len(LESSONS)
    for lesson in LESSONS.values():
        assert sanitize_request(lesson)==lesson

def test_reordered_sentences_from_different_scenes_are_rejected(core):
    async def run():
        config=StoryConfig(dream='A fox in a forest')
        first=await core.generate(config,[],[])
        second=await core.generate(config,[first],[])
        text='Fox looked for dry ground. He wanted to find its owner. A butterfly rested on a flower.'
        candidate=second.model_copy(update={'scene_id':3,'story_text':text,'narration':text})
        with pytest.raises(RepeatedScene):
            check_progress(candidate,[first,second])
    asyncio.run(run())

def test_repeated_outline_is_rejected():
    from dreamtales.storycraft import check_outline
    with pytest.raises(ValueError,match='repeats'):
        check_outline(['Jack carried the little basket across the garden.']*5)

def test_dialogue_keeps_punctuation_and_narration():
    raw={'title':'Take turns','sentences':['Rabbit said, "Let us take turns.",','Fox gave Rabbit the small cup.','They both had a drink of water.'],'characters':['Fox','Rabbit'],'location':'Garden','artwork':'forest'}
    scene=parse_scene(json.dumps(raw),StoryConfig(dream='Two friends sharing a cup'),[None])
    assert '\".' not in scene.story_text
    assert ',.' not in scene.story_text
    assert scene.story_text==scene.narration

def test_duplicate_and_lightly_reworded_scene_are_rejected(core):
    async def run():
        scene=await core.generate(StoryConfig(dream='A fox in a forest'),[],[])
        for text in (scene.story_text,scene.story_text.replace('picked','lifted')):
            repeated=scene.model_copy(update={'scene_id':2,'story_text':text,'narration':text})
            with pytest.raises(RepeatedScene):check_progress(repeated,[scene])
        different=await core.generate(StoryConfig(dream='A fox in a forest'),[scene],[])
        check_progress(different,[scene])
    asyncio.run(run())

def test_repetition_retry_gets_specific_feedback(core,tunes):
    async def run():
        config=StoryConfig(dream='A fox in a forest')
        class RepeatsOnce:
            mode='local-ai'
            repeated=False
            async def generate(self,config,history,decisions):
                if history and not self.repeated:
                    self.repeated=True
                    return history[0].model_copy(update={'scene_id':2})
                if history:assert 'NEW action' in REPAIR_HINT.get()
                return await core.generate(config,history,decisions)
        s=Session('test',config)
        await DreamSync(RepeatsOnce(),DreamVision(),tunes).run(s)
        assert len(s.scenes)==2
        assert s.scenes[0].story_text!=s.scenes[1].story_text
        assert s.metrics[1]['rejections']==1
    asyncio.run(run())

def test_arc_has_five_distinct_steps_and_fixed_lesson():
    config=StoryConfig(dream='Two friends learning to share')
    class Previous:
        story_text='The friends want to build a small den.'
    plans=[story_plan(config,[Previous()]*n) for n in range(5)]
    assert len({p['scene_purpose'] for p in plans})==5
    assert {p['lesson'] for p in plans}=={LESSONS[config._lesson_id]}
    assert [p['stage'] for p in plans]==['introduction','problem','proposed_solution','trying_solution','success']
    assert 'conversation' in plans[1]['scene_purpose']

def test_final_lesson_is_separate_from_scene_narration(core,tunes):
    async def run():
        s=Session('test',StoryConfig(dream='Friends learn to share'))
        s.fill_to=5
        await DreamSync(core,DreamVision(),tunes).run(s)
        assert len(s.scenes)==5
        final=s.views[5]
        assert final['moral']==LESSONS[s.config._lesson_id]
        assert final['moral'] not in final['narration']
        assert final['narration']==final['story_text']
        assert all(not s.views[n]['moral'] for n in range(1,5))
    asyncio.run(run())

def test_outline_is_generated_once_and_reused_during_prefetch(core,tunes):
    async def run():
        class PlannedCore:
            mode='local-ai'
            plans=0
            async def plan(self,config):
                self.plans+=1
                return [f'Planned event number {n} makes new progress.' for n in range(1,6)]
            async def generate(self,config,history,decisions):
                assert f'Planned event number {len(history)+1}' in REPAIR_HINT.get()
                return await core.generate(config,history,decisions)
        provider=PlannedCore();sync=DreamSync(provider,DreamVision(),tunes)
        s=Session('test',StoryConfig(dream='Friends sharing a toy'))
        await sync.run(s)
        sync.refill(s,1);await s.task
        assert provider.plans==1 and len(s.scenes)==3
    asyncio.run(run())

@pytest.mark.parametrize('ending',['with.', 'with', 'for.', 'through.'])
def test_fragmented_sentence_is_rejected(ending):
    raw={'title':'A warm den','sentences':['Fox and Rabbit built a den '+ending, 'They found some soft moss.', 'The pair went home to rest.'],'characters':['Fox','Rabbit'],'location':'Forest','artwork':'forest'}
    with pytest.raises(ValueError,match='thought was complete'):parse_scene(json.dumps(raw),StoryConfig(dream='A cozy forest den'),[None])

def test_opening_phrase_required_only_for_first_scene():
    cfg=StoryConfig(dream='Jack the fox in a forest')
    raw={'title':'A quiet forest','sentences':['Once upon a time, Jack the fox lived in a forest.', 'His friend Robert the rabbit lived near the tall trees.', 'Soft green moss covered the ground beside their little homes.'],
         'characters':['Jack the fox','Robert the rabbit'],'location':'Forest','artwork':'forest'}
    scene=parse_scene(json.dumps(raw),cfg,[])
    assert scene.narration.startswith('Once upon a time,')
    with pytest.raises(ValueError,match='restarting'):
        parse_scene(json.dumps(raw),cfg,[scene])
    raw['sentences'][0]='Jack the fox lived in a quiet forest.'
    with pytest.raises(ValueError,match='must begin'):
        parse_scene(json.dumps(raw),cfg,[])

@pytest.mark.parametrize('copied',[
    'Jack looked up.',
    'JACK LOOKED UP!',
    'Jack the fox picked up the small red basket.',
    'Jack the fox lifted up the small red basket.',
    'Mr. Rabbit nodded.',
])
def test_single_repeated_sentence_rejected_even_with_new_surrounding_text(copied):
    from types import SimpleNamespace
    previous=SimpleNamespace(scene_id=1,story_text='Jack looked up. Jack the fox picked up the small red basket. Mr. Rabbit nodded.')
    draft=SimpleNamespace(story_text=copied+' A butterfly landed on a flower. The gate swung open in the breeze.')
    with pytest.raises(RepeatedScene):check_progress(draft,[previous])

def test_introduction_has_no_goal_and_goal_moves_to_scene_two():
    from types import SimpleNamespace
    cfg=StoryConfig(dream='Jack the fox in a forest')
    intro=story_plan(cfg,[])
    assert 'ONLY' in intro['scene_purpose'] and 'No goal' in intro['scene_purpose']
    first=SimpleNamespace(story_text='Jack lives in a quiet forest.')
    second=SimpleNamespace(story_text='Jack wants a picnic but the basket is missing.')
    assert story_plan(cfg,[first,second])['goal_established_in']==second.story_text
    assert 'Once upon a time,' in messages(cfg,[],[])[0]['content']

def test_invalid_outline_uses_five_beat_fallback(core,tunes):
    async def run():
        class InvalidPlan:
            mode='local-ai'
            async def plan(self,config):
                raise ValueError('Malformed outline')
            async def generate(self,*args):
                return await core.generate(*args)
        s=Session('fallback',StoryConfig(dream='Friends sharing a toy'))
        s.fill_to=5
        await DreamSync(InvalidPlan(),DreamVision(),tunes).run(s)
        assert len(s.scenes)==5
        assert s.views[5]['moral']==LESSONS[s.config._lesson_id]
    asyncio.run(run())
