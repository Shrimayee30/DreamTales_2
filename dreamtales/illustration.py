"""Scene-specific vector art built locally from safe, fixed drawing primitives."""
import hashlib
import random
from html import escape


def draw_scene(scene):
    rng = random.Random(hashlib.sha256(scene.model_dump_json().encode()).digest())
    sky, ground = {'forest': ('#193747', '#336451'), 'space': ('#232443', '#51466e'),
                   'ocean': ('#224660', '#367f91'), 'dragons': ('#343356', '#62648a')}[scene.artwork]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800"><title>{escape(scene.title)}</title>',
             f'<rect width="1200" height="800" fill="{sky}"/>']
    for _ in range(45):
        parts.append(f'<circle cx="{rng.randrange(1200)}" cy="{rng.randrange(450)}" r="{rng.randrange(1,4)}" fill="#ffe9b6" opacity=".6"/>')
    parts.append(f'<circle cx="{rng.randrange(760,1040)}" cy="130" r="48" fill="#ffe8b0"/>')
    parts.append(f'<path d="M0 500 Q300 {rng.randrange(320,480)} 600 500 T1200 470 V800 H0Z" fill="{ground}"/>')
    if scene.artwork in ('forest', 'dragons'):
        for x in [70, 230, 990, 1140]:
            h = rng.randrange(220,380)
            parts.append(f'<path d="M{x} 560 v-{h}" stroke="#264438" stroke-width="20"/><ellipse cx="{x}" cy="{560-h}" rx="95" ry="135" fill="#457a63"/>')
    if scene.artwork == 'ocean' or 'ocean' in scene.ambience:
        for y in (530,580,630):
            parts.append(f'<path d="M0 {y} Q150 {y-45} 300 {y} T600 {y} T900 {y} T1200 {y}" fill="none" stroke="#a8dcdb" stroke-width="9" opacity=".5"/>')
    # Fixed shapes keep all generated markup inert. Character names are escaped text.
    cast = scene.characters[:5]
    for i, name in enumerate(cast):
        x = 600 + (i-(len(cast)-1)/2)*185 + rng.randrange(-20,21)
        y = rng.randrange(470,540)
        rabbit = 'rabbit' in name.lower() or 'bunny' in name.lower()
        fox = 'fox' in name.lower()
        color = '#ecdcca' if rabbit else '#e99d62' if fox else '#b5c9cf'
        parts.append(f'<g transform="translate({x} {y})"><ellipse cy="100" rx="48" ry="67" fill="{color}"/>')
        if rabbit:
            parts.append(f'<ellipse cx="-24" cy="-53" rx="16" ry="59" fill="{color}"/><ellipse cx="24" cy="-53" rx="16" ry="59" fill="{color}"/>')
        elif fox:
            parts.append(f'<path d="M-49 0 L-55 -65 L-8 -20 L10 -20 L55 -65 L49 0Z" fill="{color}"/>')
        else:
            parts.append(f'<circle cx="-38" cy="-32" r="22" fill="{color}"/><circle cx="38" cy="-32" r="22" fill="{color}"/>')
        parts.append(f'<ellipse rx="52" ry="45" fill="{color}"/><ellipse cy="18" rx="32" ry="22" fill="#fff0d7"/><circle cx="-18" cy="-3" r="5" fill="#243741"/><circle cx="18" cy="-3" r="5" fill="#243741"/><path d="M-5 14 Q0 23 5 14" fill="none" stroke="#243741" stroke-width="4"/><text y="192" text-anchor="middle" fill="#fff0d7" font-family="sans-serif" font-size="19">{escape(name)}</text></g>')
    if 'rain' in scene.ambience:
        for _ in range(65):
            x,y=rng.randrange(1200),rng.randrange(680)
            parts.append(f'<path d="M{x} {y} l-5 18" stroke="#b2d8e6" stroke-width="2" opacity=".5"/>')
    if 'wind' in scene.ambience:
        parts.append('<path d="M120 310 Q300 250 430 310 M720 280 Q860 220 1050 280" fill="none" stroke="#c8ded6" stroke-width="4" opacity=".5"/>')
    parts.append(f'<text x="60" y="755" fill="#fff0d7" font-family="sans-serif" font-size="26">{escape(scene.location)} · {scene.scene_id}</text></svg>')
    return ''.join(parts)
