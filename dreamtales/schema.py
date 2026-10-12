import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .safety import sanitize_request

Theme = Literal['forest', 'space', 'ocean', 'dragons']
Ambience = Literal['rain', 'wind', 'night', 'ocean', 'thunder']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class GenerationSettings(StrictModel):
    temperature: float = Field(default=0.65, ge=0, le=1.2)
    top_p: float = Field(default=0.9, ge=0.1, le=1)
    max_tokens: int = Field(default=400, ge=300, le=700)

class StoryConfig(StrictModel):
    dream: str = Field(min_length=5, max_length=500)
    length: Literal[5] = 5
    generation: GenerationSettings = Field(default_factory=GenerationSettings)

    @field_validator('dream', mode='before')
    @classmethod
    def clean_dream(cls, value):
        if not isinstance(value, str):
            raise ValueError('Please enter a story idea.')
        value = sanitize_request(value)
        if len(value) < 5:
            raise ValueError('Tell us a little more about your dream.')
        return value

class SceneDraft(StrictModel):
    scene_id: int = Field(ge=1, le=5)
    title: str = Field(min_length=3, max_length=80)
    story_text: str = Field(min_length=40, max_length=1200)
    characters: list[str] = Field(min_length=1, max_length=8)
    location: str = Field(min_length=2, max_length=100)
    emotional_tone: Literal['wonder', 'curiosity', 'hope', 'joy', 'calm']
    image_prompt: str = Field(min_length=10, max_length=600)
    artwork: Theme = 'forest'
    ambience: list[Ambience] = Field(default_factory=list, max_length=3)
    ending: bool

    @field_validator('story_text')
    @classmethod
    def short_scene(cls, value):
        prose = re.sub(r'\b(Mr|Mrs|Ms|Dr|St)\.', r'\1', value)
        count = len(re.findall(r'[.!?](?=[\"\u201d\u2019\']?(?:\s|$))', prose))
        if count not in (3, 4):
            raise ValueError('A scene must contain exactly 3 or 4 sentences.')
        sentences = re.split(r'[.!?]+', prose)
        if any(len(re.findall(r"\b[\w’\'-]+\b", sentence)) > 18 for sentence in sentences):
            raise ValueError('Use short sentences with at most 18 words each.')
        return value

    @model_validator(mode='after')
    def coherent(self):
        if any(not 1 <= len(c) <= 60 for c in self.characters):
            raise ValueError('Character names must be bounded.')
        self.ambience = list(dict.fromkeys(self.ambience))
        if 'thunder' in self.ambience and 'rain' not in self.ambience:
            self.ambience.remove('thunder')
        return self

class Scene(SceneDraft):
    moral: str = Field(default='', max_length=150)
    narration: str = Field(min_length=40, max_length=1200)

    @model_validator(mode='after')
    def same_narration(self):
        if self.narration != self.story_text:
            raise ValueError('Narration must match the displayed story.')
        return self

class ContinueRequest(StrictModel):
    scene_id: int = Field(ge=1, le=5)
    direction: str = Field(default='', max_length=300)

    @field_validator('direction', mode='before')
    @classmethod
    def clean_direction(cls, value):
        if not isinstance(value, str):
            raise ValueError('Please enter a story idea.')
        return sanitize_request(value)


class RetryRequest(StrictModel):
    scene_id: int = Field(ge=0, le=5)
