"""Declared craft layers and the catalog record roles consulted for each."""
from __future__ import annotations

LAYERS = {
    'scene': (('scenes', ('scene',)), ('recipes', ('recipe',))),
    'detail': (('modules', ('module',)),),
    'finish': (('families', ('style-family',)), ('profiles', ('profile',)),
               ('aesthetic', ('aesthetic-core',)), ('realizations', ('domain-realization',))),
    'repair': (('corrections', ('correction',)),),
    'identity': (('archetypes', ('archetype',)),),
}
