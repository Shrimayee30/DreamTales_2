import pytest
from dreamtales.schema import Scene

class FakeCore:
    mode = 'local-ai'
    def __init__(self): self.calls = []
    async def generate(self, config, history, directions):
        self.calls.append((config.dream, list(directions)))
        n = len(history) + 1
        characters = ['Fox']
        if any('rabbit' in d['text'].lower() and d['scene_id'] <= n for d in directions): characters.append('Mr Rabbit')
        texts = [
            'Fox found a lost basket in the forest. Soft rain tapped on the leaves. He wanted to find its owner. He picked it up.',
            'A wide puddle covered the path. The basket was too big to carry across. Fox looked for dry ground.',
            'He tried a small stepping stone. His paws slipped into the mud. He stepped back onto the grass.',
            'A friend brought a flat board. They put it over the water. Now they could cross safely.',
            'The pair carried the basket over their bridge. A blue ribbon hung from its handle. They followed matching ribbons up a hill.',
            'At the top, a gate was stuck. One friend held the basket. The other pushed the gate open.',
            'A little mouse needed help with her bag. Fox stopped to carry it. She showed him her house.',
            'The mouse saw her missing basket. She thanked the helpers with a smile. Everyone sat at her table.',
            'They shared some fresh bread. Each friend waited for a turn. Nobody was left out of the meal.',
            'The friends went home under the stars. Their feet were tired after the walk. They curled up in soft beds.',
        ]
        text = texts[n-1]
        return Scene(scene_id=n,title='A gentle dream',story_text=text,narration=text,characters=characters,
            location='Willow Woods',emotional_tone='calm',image_prompt='A gentle rainy forest with warm lanterns.',
            artwork='forest',ambience=['rain'],ending=n==config.length)

class QuietTunes:
    kind = 'device-voice'
    async def generate(self, scene, sid): return {'url':None,'kind':self.kind}

@pytest.fixture
def core(): return FakeCore()

@pytest.fixture
def tunes(): return QuietTunes()
