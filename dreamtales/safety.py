"""Baseline screening only; not a validated child-safety classifier."""
import re
import unicodedata
from pydantic_core import PydanticCustomError

SAFETY_MESSAGE = "This is not safe for kids. Let's try a kind, gentle story instead."


RULES = {
    'alcohol': r'\b(beer|beers|wine|wines|vodka|whisk(?:e)?y|rum|tequila|champagne|alcohol|drunk|booze|cocktails?)\b',
    'substances': r'\b(cigarettes?|tobacco|vapes?|vaping|cocaine|heroin|meth|marijuana|cannabis)\b',
    'sexual': r'\b(sex|sexual|nude|porn\w*)\b',
    'violence': r'\b(kill\w*|murder\w*|gore|blood\w*|stab\w*|torture\w*)\b',
    'self_harm': r'\b(suicid\w*|self[ -]?harm|hurt yourself)\b',
    'hate': r'\b(racial supremacy|inferior race|hate all)\b',
    'danger': r'\b(weapon\w*|bomb\w*|poison\w*|play with fire|drink bleach)\b',
    'bullying': r'\b(bully\w*|humiliat\w*|you are worthless)\b',
    'profanity': r'\b(fuck\w*|shit\w*)\b',
    'illegal': r'\b(steal\w*|shoplift\w*|illegal drugs)\b',
    'privacy': r'[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b(?:\d[ ()+.-]*){7,}\b|\b\d{1,5}\s+\w+\s+(?:street|road|avenue)\b',
    'injection': r'ignore (?:all |previous |system )*instructions|system prompt|<script|javascript:|\b(?:https?://|www\.)',
    'dependency': r'keep (?:this |it |our friendship )?(?:a )?secret|don.t tell (?:your )?(?:parents|guardian)',
}

class UnsafeScene(ValueError):
    pass

def check_scene(scene):
    # Include all model-controlled fields, including choice labels and prompts.
    text = unicodedata.normalize('NFKC', scene.model_dump_json()).casefold()
    for category, pattern in RULES.items():
        if re.search(pattern, text):
            raise UnsafeScene(category)


def sanitize_request(value: str) -> str:
    value = unicodedata.normalize('NFKC', value)
    value = ''.join(ch for ch in value if not unicodedata.category(ch).startswith('C') or ch in '\n\t')
    value = ' '.join(value.split())
    value = re.sub(RULES['privacy'], '[private detail removed]', value, flags=re.I)
    for category, pattern in RULES.items():
        if category != 'privacy' and re.search(pattern, value.casefold()):
            raise PydanticCustomError('child_safety', SAFETY_MESSAGE)
    return value
