from __future__ import annotations

_ITEM_BLOCKLIST = frozenset([
    'moment', 'chance', 'opportunity', 'glance', 'look', 'sense', 'feeling',
    'glimpse', 'breath', 'step', 'pause', 'nod', 'smile', 'word', 'message',
    'warning', 'signal', 'cue', 'hint', 'idea', 'notion', 'thought', 'grip',
    'heartbeat', 'second', 'minute', 'hour', 'day', 'year', 'it', 'this',
    'that', 'its', 'him', 'her', 'them', 'they', 'way', 'one', 'two', 'three',
    'new', 'old', 'good', 'bad', 'first', 'last',
])

ENABLE_DYNAMIC_MULTIPASS = True
__all__ = ['ENABLE_DYNAMIC_MULTIPASS', '_ITEM_BLOCKLIST']
