"""Use audible scene evidence; do not trust a model's sound labels alone."""
import re

def scene_sounds(scene):
    text = scene.story_text.casefold()
    sounds = []
    rain = bool(re.search(r'\b(rain\w*|drizzl\w*|patter\w*)\b',text))
    if re.search(r'\b(no rain|without rain|rain (?:had |has )?(?:stopped|ended)|rain was gone)\b',text):rain=False
    if rain:sounds.append('rain')
    if re.search(r'\b(wind|windy|breeze|breezes|rustling)\b',text) and not re.search(r'\b(no wind|without wind|windless)\b',text):sounds.append('wind')
    if re.search(r'\b(ocean|waves|seashore|surf|sea)\b',text):sounds.append('ocean')
    outside = re.search(r'\b(forest|woods|garden|meadow|field)\b',text+' '+scene.location.casefold())
    if re.search(r'\bcrickets?\b',text) or outside and re.search(r'\b(night|moonlit|moonlight|dusk)\b',text):sounds.append('night')
    if rain and re.search(r'\bthunder\b',text) and not re.search(r'\b(no thunder|without thunder)\b',text):
        sounds = ['rain','thunder'] + [s for s in sounds if s not in ('rain','thunder')]
    return sounds[:3]
