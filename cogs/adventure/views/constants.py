import re
XP_REWARDS = {'crit_success': 25, 'success': 18, 'fail': 10, 'crit_fail': 15}
STATS = ['STR', 'PER', 'END', 'CHA', 'INT', 'AGI', 'LUK']
STAT_NAMES = {'STR': 'Strength', 'PER': 'Perception', 'END': 'Endurance', 'CHA': 'Charisma', 'INT': 'Intelligence', 'AGI': 'Agility', 'LUK': 'Luck'}
STAT_EMOJI = {'STR': '💪', 'PER': '👁️', 'END': '🛡️', 'CHA': '🗣️', 'INT': '🧠', 'AGI': '🏹', 'LUK': '🍀', 'ITEM': '🎒'}
MAX_LEVEL = 50
MAX_STAT_VALUE = 10
STAT_COLUMN = {'STR': 'str_', 'PER': 'per_', 'END': 'end_', 'CHA': 'cha', 'INT': 'int_', 'AGI': 'agi', 'LUK': 'luk'}
DEFAULT_SCENARIO = 'fantasy'
QUEST_TYPE_ICONS = {'monster hunting': '👹', 'extermination': '👹', 'bounty hunting': '🎯', 'gathering': '💎', 'relic': '💎', 'resource run': '🧪', 'alchemy': '🧪', 'crafting': '🧪', 'rescue': '🛡️', 'escort': '🛡️', 'find person': '🛡️', 'investigation': '🔍', 'mystery': '🔍', 'espionage': '📜', 'blackmail': '📜', 'infiltration': '🕵️', 'heist': '🕵️', 'theft': '🕵️', 'diplomacy': '🤝', 'faction': '🤝', 'tribunal': '⚖️', 'arbitration': '⚖️', 'survival': '🏰', 'defense': '🏰', 'siege': '🏰', 'ritual': '🔮', 'sealing': '🔮', 'cleansing': '🔮', 'exorcism': '🛡️', 'override': '⚡', 'sabotage': '💥', 'disruption': '💥', 'assassination': '🗡️', 'duel': '🗡️', 'gossip': '💬', 'rumor': '💬', 'campaigning': '🗳️', 'election': '🗳️', 'matchmaking': '💌', 'secret admirer': '💌', 'romance': '💌', 'club': '🏆', 'showdown': '🏆', 'curfew': '🌙', 'campus infiltration': '🌙', 'exam': '📚', 'academic': '📚', 'off-campus': '🏙️', 'errand': '📦', 'urban legend': '👻', 'dare': '⚡', 'arcade': '🕹️', 'beast taming': '🐉', 'familiar': '🐉', 'archaeology': '🏛️', 'dungeon': '🏛️', 'netrunning': '💻', 'cyberware': '🔧', 'tech extraction': '🔧', 'rogue ai': '🤖', 'derelict': '🛸', 'salvage': '🛸', 'signal': '📻', 'radio': '📻', 'toxic': '☣️', 'radiation': '☣️', 'convoy': '🏎️', 'seduction': '💋', 'allure': '💋', 'domination': '⛓️', 'subjugation': '⛓️', 'brothel': '🈲', 'courtesan': '🈲', 'aphrodisiac': '🧪', 'lust': '🧪', 'courtship': '💘', 'paramour': '💘', 'harem': '💘', 'bondage': '⛓️\u200d💥', 'revelry': '🎭', 'masquerade': '🎭'}

__all__ = ['XP_REWARDS', 'STATS', 'STAT_NAMES', 'STAT_EMOJI', 'MAX_LEVEL', 'MAX_STAT_VALUE', 'STAT_COLUMN', 'DEFAULT_SCENARIO', 'QUEST_TYPE_ICONS']
