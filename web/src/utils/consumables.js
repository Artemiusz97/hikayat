const NON_CONSUMABLE_TYPES = new Set([
  'weapon',
  'armor',
  'shield',
  'accessory',
  'helmet',
  'head',
  'headwear',
  'boots',
  'shoes',
  'gloves',
  'ring',
  'amulet',
  'cloak',
  'clothing',
  'top',
  'bottom',
  'outerwear',
  'lingerie',
  'bra',
  'underwear',
  'misc',
  'gift',
  'novelty',
  'key item',
  'quest',
  'quest item',
  'narrative artifact',
  'narrative',
  'spellbook',
  'digital media',
]);

const CONSUMABLE_TYPES = new Set([
  'potion',
  'consumable',
  'food',
  'drink',
  'remedy',
  'tonic',
  'scroll',
  'elixir',
  'throwable',
]);

const HOSTILE_KEYWORDS = [
  'sleep',
  'sleeping',
  'sedative',
  'tranquil',
  'poison',
  'toxin',
  'venom',
  'paralyz',
  'chloroform',
  'aphrodisiac',
  'love potion',
  'truth serum',
  'drugged',
  'spiked',
  'smoke bomb',
  'flashbang',
  'grenade',
  'acid flask',
  'firebomb',
  'explosive',
  'corrosive',
];

const NARRATIVE_KEYWORDS = [
  'tea',
  'coffee',
  'latte',
  'boba',
  'wine',
  'ale',
  'beer',
  'sake',
  'cider',
  'whiskey',
  'cocktail',
  'snack',
  'bento',
  'meal',
  'cake',
  'chocolate',
  'candy',
  'perfume',
  'incense',
  'aphrodisiac',
  'draught',
  'sedative',
  'sleeping',
  'love potion',
  'truth serum',
  'pheromone',
];

export const formatCleanDeviceName = (rawName) => {
  const cleaned = String(rawName || 'Smartphone')
    .replace(/^[\p{Extended_Pictographic}\uFE0F\u200D\s]+/u, '')
    .trim();
  return cleaned || 'Smartphone';
};

export const isKeyQuestItem = (item) => {
  if (!item || typeof item !== 'object') return false;
  if (item?.inspect_data?.is_key_item) return true;
  if (item.is_quest_locked || item.is_key_item) return true;
  const type = String(item.type || item.item_type || '').toLowerCase();
  const eff = String(item.effect || '').toLowerCase();
  return (
    type.includes('key') ||
    type.includes('quest') ||
    type.includes('narrative artifact') ||
    eff.includes('important narrative item:') ||
    eff.includes('"is_key_item":true') ||
    eff.includes('"is_key_item": true')
  );
};

export const isHostileConsumable = (item) => {
  if (!item || typeof item !== 'object') return false;
  if (typeof item?.inspect_data?.is_hostile_consumable === 'boolean') {
    return item.inspect_data.is_hostile_consumable;
  }
  const combined = `${item.name || ''} ${item.clean_effect || ''} ${item.effect || ''}`.toLowerCase();
  return HOSTILE_KEYWORDS.some((kw) => combined.includes(kw));
};

export const getConsumableUsageMode = (item) => {
  if (!item || typeof item !== 'object') return 'non_consumable';
  const serverMode = item?.inspect_data?.usage_mode;
  if (serverMode) return serverMode;

  if (isKeyQuestItem(item)) return 'non_consumable';
  const type = String(item.type || item.item_type || '').trim().toLowerCase();
  const name = String(item.name || '').trim().toLowerCase();
  const rawEff = String(item.effect || '').trim();
  const eff = String(item.clean_effect || rawEff).toLowerCase();

  if (
    type === 'spellbook' ||
    rawEff.startsWith('[SPELLBOOK_JSON]') ||
    rawEff.startsWith('[DIGITAL_JSON]') ||
    type.includes('digital')
  ) {
    return 'non_consumable';
  }
  if (
    (rawEff.startsWith('[GEAR_JSON]') || rawEff.startsWith('[ITEM_JSON]')) &&
    !CONSUMABLE_TYPES.has(type)
  ) {
    return 'non_consumable';
  }
  if (
    NON_CONSUMABLE_TYPES.has(type) &&
    !CONSUMABLE_TYPES.has(type) &&
    !['potion', 'elixir', 'tonic', 'draught', 'remedy', 'aphrodisiac', 'sedative'].some((kw) =>
      name.includes(kw)
    )
  ) {
    return 'non_consumable';
  }

  if (
    type === 'throwable' ||
    ['bomb', 'grenade', 'flashbang', 'acid flask', 'firebomb', 'explosive'].some((kw) =>
      `${name} ${eff}`.includes(kw)
    )
  ) {
    return 'throwable';
  }

  const hasMech =
    /(?:heal|restor|cure|\+|hp|mp|atk|def|eva|dt|dr|mikstura|pulih|heilen|治疗|恢复)/i.test(eff) ||
    ['healing', 'mana', 'antidote'].some((kw) => name.includes(kw));

  const hasNarr =
    type === 'food' ||
    type === 'drink' ||
    isHostileConsumable(item) ||
    NARRATIVE_KEYWORDS.some((kw) => `${name} ${eff}`.includes(kw));

  if (!hasMech && !hasNarr) {
    if (
      CONSUMABLE_TYPES.has(type) ||
      ['potion', 'elixir', 'tonic', 'draught', 'remedy', 'snack', 'ration', 'tea'].some((kw) =>
        name.includes(kw)
      )
    ) {
      return 'narrative';
    }
    return 'non_consumable';
  }
  if (hasMech && hasNarr) return 'hybrid';
  if (hasMech) return 'mechanical';
  return 'narrative';
};

export const isUsableConsumable = (item) => {
  const mode = getConsumableUsageMode(item);
  return mode === 'mechanical' || mode === 'narrative' || mode === 'hybrid' || mode === 'throwable';
};

export const getAllowedUseActions = ({ item, targetType = 'self', inCombat = false }) => {
  const mode = getConsumableUsageMode(item);
  if (mode === 'non_consumable') {
    return { canQuickUse: false, canTurnUse: false, mode };
  }
  if (inCombat) {
    return { canQuickUse: false, canTurnUse: true, mode };
  }
  if (targetType === 'npc' || targetType === 'contact' || targetType === 'enemy' || targetType === 'monster') {
    return { canQuickUse: false, canTurnUse: true, mode };
  }
  if (mode === 'mechanical') {
    return { canQuickUse: true, canTurnUse: false, mode };
  }
  if (mode === 'narrative' || mode === 'throwable') {
    return { canQuickUse: false, canTurnUse: true, mode };
  }
  if (mode === 'hybrid') {
    return { canQuickUse: true, canTurnUse: true, mode };
  }
  return { canQuickUse: false, canTurnUse: false, mode };
};
