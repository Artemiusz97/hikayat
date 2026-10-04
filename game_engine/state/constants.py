import re
_GOLD_GAIN_RE = re.compile(r'\b(?:gain|found?|earn|award|reward|receiv|collect|giv|contain|grant|hand)\w*\s+(?:(?:you|them|us)\s+)?(?:with\s+)?(?:a total of\s+)?(\d+)\s+(?:gold|coins?|credits?|dollars?|bucks?)', re.I)
_GOLD_LOSS_RE = re.compile(r'\b(?:paid?|los[st]|spent?|hand\w*\s+over|drop\w*|steal|stolen|cost\w*|part\w*\s+with)\s+(\d+)\s+(?:gold|coins?|credits?|dollars?|bucks?)', re.I)
_DAMAGE_RE = re.compile(r'\b(?:take|takes?|suffer\w*|sustain\w*|inflict\w*|dealt?|receiv\w*|trigger\w*,?\s*deal\w*|deal\w*)\s+(\d+)\s+(?:points?\s+of\s+)?(?:damage|injury|harm|wound)', re.I)
_ITEM_GRANT_RE = re.compile(r'\b(?:hand\w*\s+(?:you|them)|give\w*\s+(?:you|them)|pick\w*\s+up|found?|receiv\w*|grab\w*|collect\w*|pocket\w*)\s+(?:a|an|the)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)')
_ITEM_BLOCKLIST = frozenset(['moment', 'chance', 'opportunity', 'glance', 'look', 'sense', 'feeling', 'glimpse', 'breath', 'step', 'pause', 'nod', 'smile', 'word', 'message', 'warning', 'signal', 'cue', 'hint', 'idea', 'notion', 'thought', 'grip', 'heartbeat', 'second', 'minute', 'hour', 'day', 'year', 'it', 'this', 'that', 'its', 'him', 'her', 'them', 'they', 'way', 'one', 'two', 'three', 'new', 'old', 'good', 'bad', 'first', 'last'])
_MAX_GOLD_LEAKAGE_PATCH = 5000

ENABLE_DYNAMIC_MULTIPASS = True
__all__ = ['ENABLE_DYNAMIC_MULTIPASS', '_GOLD_GAIN_RE', '_GOLD_LOSS_RE', '_DAMAGE_RE', '_ITEM_GRANT_RE', '_ITEM_BLOCKLIST', '_MAX_GOLD_LEAKAGE_PATCH']
