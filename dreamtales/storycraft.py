"""Story progression and lightweight repetition checks, without extra model calls."""
import re
from difflib import SequenceMatcher

import json
import secrets
from pathlib import Path

# Original, curated moral collection; runtime guidance, not training data.
LESSONS = json.loads((Path(__file__).parent / 'data' / 'morals.json').read_text())
STAGES = ['introduction', 'problem', 'proposed_solution', 'trying_solution', 'success']
BEATS = [
    'INTRODUCTION: Begin with "Once upon a time,". Introduce ONLY the named characters and their peaceful setting. No goal, problem, solution, adventure summary, or ending yet.',
    'PROBLEM: Establish ONE small concrete goal and the specific obstacle blocking it. Include a short conversation. Do not propose, try, or solve it yet.',
    'PROPOSED SOLUTION: The friends suggest ONE concrete plan for the existing obstacle. Explain how it could help. Do not carry it out yet.',
    'TRYING THE SOLUTION: Carry out the plan from scene 3. Show a new action and visible progress. Do not restart the problem or invent a new quest.',
    'SUCCESS: The plan worked! Show the original goal achieved and who benefits. Close calmly. No new obstacle or repeated attempt; the moral follows separately.',
]

def choose_lesson():
    return secrets.choice(tuple(LESSONS))

def story_plan(config, history):
    n = len(history)
    return {'lesson': LESSONS[config._lesson_id], 'stage': STAGES[n],
            'scene_purpose': BEATS[n], 'chronological_order': STAGES,
            'goal_established_in': history[1].story_text if len(history) >= 2 else 'Establish the goal and obstacle in scene 2, not the introduction.',
            'continue_from': history[-1].story_text if history else 'Begin the story.',
            'completed_stages': STAGES[:n],
            'continuity_rule': 'Earlier events already happened. Start AFTER the last scene. Preserve the goal, objects, cast, and progress; never replay completed stages.'}

def words(text):
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)*",text.casefold())

class RepeatedScene(ValueError):
    pass

def sentences(text):
    # Titles are not sentence boundaries; keep short dialogue in the comparison.
    text = re.sub(r'\b(Mr|Mrs|Ms|Dr|St)\.', r'\1', text, flags=re.I)
    return [words(s) for s in re.split(r'[.!?]+', text) if words(s)]

def check_outline(events):
    for i, event in enumerate(events):
        for earlier in events[:i]:
            if SequenceMatcher(None, words(event), words(earlier), autojunk=False).ratio() >= .85:
                raise ValueError('Outline repeats an earlier event')

def check_progress(scene, history):
    current=words(scene.story_text)
    grams=lambda tokens: set(zip(tokens,tokens[1:],tokens[2:]))
    current_grams=grams(current)
    # Catch recycling of individual sentences even when they are reordered or
    # scattered across multiple earlier scenes and whole-scene overlap is low.
    old_sentences = [s for previous in history for s in sentences(previous.story_text)]
    for sentence in sentences(scene.story_text):
        for old in old_sentences:
            if sentence == old or (min(len(sentence), len(old)) >= 6 and
                    SequenceMatcher(None, sentence, old, autojunk=False).ratio() >= .86):
                raise RepeatedScene('An earlier sentence was recycled; continue after it rather than repeating it.')
    for previous in history:
        old=words(previous.story_text)
        old_grams=grams(old)
        union=current_grams | old_grams
        overlap=len(current_grams & old_grams)/max(1,len(union))
        similarity=SequenceMatcher(None,current,old,autojunk=False).ratio()
        if similarity >= .78 or overlap >= .5:
            raise RepeatedScene(f'Too similar to scene {previous.scene_id}; advance the current story beat.')
