"""Story progression and lightweight repetition checks, without extra model calls."""
import re
from difflib import SequenceMatcher

LESSONS = {
    'kindness': 'Small acts of kindness can make a big difference.',
    'sharing': 'Sharing and taking turns makes play more fun for everyone.',
    'honesty': 'Telling the truth helps us fix mistakes together.',
    'patience': 'Taking a breath and trying again helps us learn.',
    'teamwork': 'Listening and working together helps us solve problems.',
}
BEATS = [
    'Introduce named characters and ONE small, concrete goal they want to achieve.',
    'Show a small obstacle and a first attempt. Include a short conversation about what to try.',
    'Make a helpful choice that demonstrates the lesson and brings a NEW result.',
    'Resolve the original obstacle and show how the helpful choice benefits someone else.',
    'Close the adventure peacefully with the goal achieved. Settle down to rest; the moral follows.',
]


def lesson_for(dream):
    text=dream.casefold()
    for lesson, pattern in [('sharing',r'\b(shar\w*|turns)\b'),('honesty',r'\b(honest\w*|truth|lying)\b'),('patience',r'\b(patien\w*|learn\w*|try again)\b'),('teamwork',r'\b(team\w*|together|cooperat\w*)\b')]:
        if re.search(pattern,text):return lesson
    return 'kindness'

def story_plan(config, history):
    lesson=lesson_for(config.dream)
    return {'lesson':LESSONS[lesson], 'scene_purpose':BEATS[len(history)],
            'goal_established_in':history[0].story_text if history else 'Establish it in this scene.'}

def words(text):
    return re.findall(r'[a-z]+',text.casefold())

class RepeatedScene(ValueError):
    pass

def check_progress(scene, history):
    current=words(scene.story_text)
    grams=lambda tokens: set(zip(tokens,tokens[1:],tokens[2:]))
    current_grams=grams(current)
    for previous in history:
        old=words(previous.story_text)
        old_grams=grams(old)
        union=current_grams | old_grams
        overlap=len(current_grams & old_grams)/max(1,len(union))
        similarity=SequenceMatcher(None,current,old,autojunk=False).ratio()
        if similarity >= .78 or overlap >= .5:
            raise RepeatedScene(f'Too similar to scene {previous.scene_id}; advance the current story beat.')
