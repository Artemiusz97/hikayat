import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Shield, Heart, Zap, User, Coins, Sparkles, Plus, AlertCircle, BookOpen, X } from 'lucide-react';
import { apiCall } from '../../api/client';

const StatBar = ({ label, current, max, color, icon: Icon, extraText }) => {
  const safeCurrent = Math.max(0, current || 0);
  const safeMax = Math.max(1, max || 1);
  const pct = Math.min(100, Math.round((safeCurrent / safeMax) * 100));

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center text-xs">
        <div className="flex items-center gap-1.5 font-bold text-gray-200 uppercase tracking-wider">
          <Icon size={13} className={color.text} />
          <span>{label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {extraText && <span className="text-[10px] text-gray-400 font-medium">{extraText}</span>}
          <span className="font-mono text-gray-100 font-bold text-xs">{safeCurrent} / {safeMax}</span>
          <span className="text-[10px] font-mono text-gray-400 font-medium">({pct}%)</span>
        </div>
      </div>
      <div className="h-2 sm:h-2.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/70 p-0.5">
        <div 
          className={`h-full ${color.bg} rounded-full transition-all duration-500 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};

export const parseAndTranslateStatus = (effect, t) => {
  let effName = typeof effect === 'string' ? effect : (effect?.name || 'Effect');
  let duration = typeof effect === 'object' && effect?.duration !== undefined ? effect.duration : null;
  let durationUnit = 't';

  // Support bracketed duration strings like "Refractory Recovery [28 min]" or "Aroused [3 turns]"
  const match = typeof effName === 'string' ? effName.match(/^(.*?)\s*\[(\d+)\s*(min|m|turns?|t)\]$/i) : null;
  if (match) {
    effName = match[1].trim();
    duration = match[2];
    durationUnit = match[3].toLowerCase().startsWith('m') ? 'm' : 't';
  }

  const displayLabel = effName.includes(' & ')
    ? effName
        .split(' & ')
        .map(part => {
          const pk = part.trim().toLowerCase().replace(/[\s\-]+/g, '_');
          return t(`conditions.${pk}`, part.trim());
        })
        .join(' & ')
    : t(`conditions.${effName.toLowerCase().replace(/[\s\-]+/g, '_')}`, effName);

  const formattedText = duration !== null ? `${displayLabel} [${duration}${durationUnit}]` : displayLabel;

  return { effName, displayLabel, duration, durationUnit, formattedText };
};

const formatTitle = (str) => {
  if (!str) return '';
  return String(str).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

const formatFusedAsset = (sizeStr, texStr, isMale = false, t = null) => {
  const s = String(sizeStr || (isMale ? 'Average' : 'Modest B-Cup')).replace(/^[()]+|[()]+$/g, '').trim();
  const tStr = String(texStr || '').replace(/^[()]+|[()]+$/g, '').trim();
  
  const bKey = s.toLowerCase().replace(/[\s\-]+/g, '_');
  const bTranslated = t ? t(`anatomy.${bKey}`, s) : s;
  
  if (!tStr) return formatTitle(bTranslated);

  // If s already contains the texture (e.g. LLM flared or pre-fused)
  const tClean = tStr.toLowerCase().replace(/&/g, '').trim();
  const sClean = s.toLowerCase().replace(/&/g, '').trim();
  if (s.toLowerCase().includes(tStr.toLowerCase()) || (tClean.length > 3 && sClean.includes(tClean))) {
    return formatTitle(bTranslated);
  }

  const texKey = tStr.toLowerCase().replace(/[\s\-&]+/g, '_');
  const texTranslated = t ? t(`anatomy.${texKey}`, tStr) : tStr;

  if (!isMale) {
    const cupMatch = s.match(/\b([A-Ha-h]+(?:\+)?-Cup)\b/i);
    if (cupMatch) {
      const cupPart = cupMatch[1].toUpperCase().replace(/-CUP$/, '-Cup');
      return `${formatTitle(texTranslated)} ${cupPart}`;
    }
    const redundant = ['generous', 'voluptuous', 'modest', 'petite', 'heavy', 'bountiful', 'shapely', 'toned', 'firm', 'soft', 'full', 'small', 'large', 'average'];
    const filtered = s.split(/\s+/).filter(w => !redundant.includes(w.toLowerCase())).join(' ').trim();
    if (filtered) return `${formatTitle(texTranslated)} ${formatTitle(filtered)}`;
    return `${formatTitle(texTranslated)} ${formatTitle(bTranslated)}`;
  } else {
    const inchMatch = s.match(/(\d+(?:\.\d+)?\s*(?:\"|inch(?:es)?))/i);
    if (inchMatch) {
      let inchPart = inchMatch[1].trim();
      if (/inch/i.test(inchPart)) {
        const num = (inchPart.match(/\d+(?:\.\d+)?/) || [])[0];
        inchPart = `${num}"`;
      }
      return `${formatTitle(texTranslated)} ${inchPart}`;
    }
    const redundant = ['thick', 'long', 'massive', 'compact', 'slender', 'sturdy', 'dense', 'toned', 'formidable', 'large', 'huge', 'small'];
    const filtered = s.split(/\s+/).filter(w => !redundant.includes(w.toLowerCase())).join(' ').trim();
    if (filtered) return `${formatTitle(texTranslated)} ${formatTitle(filtered)}`;
    return `${formatTitle(texTranslated)} ${formatTitle(bTranslated)}`;
  }
};

const FEMALE_TEXTURE_OPTIONS = [
  { value: 'Perky & High-Set', label: 'Perky & High-Set' },
  { value: 'Pillowy Soft & Yielding', label: 'Pillowy Soft & Yielding' },
  { value: 'Firm & Toned', label: 'Firm & Toned' },
  { value: 'Smooth & Supple', label: 'Smooth & Supple' },
  { value: 'Heavy & Plush', label: 'Heavy & Plush' },
  { value: 'Bouncy & Sensitive', label: 'Bouncy & Sensitive' },
  { value: 'Tender & Delicate', label: 'Tender & Delicate' },
  { value: 'Shapely Teardrop', label: 'Shapely Teardrop' },
  { value: 'Compact & Dense', label: 'Compact & Dense' },
  { value: 'Sensitive & Responsive', label: 'Sensitive & Responsive' },
  { value: 'Warm & Supple', label: 'Warm & Supple' },
  { value: 'Soft & Downy Chest Fur', label: 'Soft & Downy Chest Fur (Beastfolk)' },
  { value: 'Silky Fur-Rimmed', label: 'Silky Fur-Rimmed (Beastfolk)' },
  { value: 'Velvety Underbelly Down', label: 'Velvety Underbelly Down (Beastfolk)' },
  { value: 'Fluffy Plush-Accented', label: 'Fluffy Plush-Accented (Beastfolk)' },
  { value: 'Silky Warm with Smooth Micro-Scales', label: 'Silky Warm with Smooth Micro-Scales (Scaly/Draconic)' },
  { value: 'Supple with Shimmering Scale Borders', label: 'Supple with Shimmering Scale Borders (Scaly/Draconic)' },
  { value: 'Sleek & Supple Drake-Contour', label: 'Sleek & Supple Drake-Contour (Scaly/Draconic)' },
  { value: 'Downy Feather-Lined', label: 'Downy Feather-Lined (Avian/Winged)' },
  { value: 'Light & Buoyant', label: 'Light & Buoyant (Avian/Winged)' },
  { value: 'Velvety Plumage Accents', label: 'Velvety Plumage Accents (Avian/Winged)' },
  { value: 'Glistening & Ultra-Smooth', label: 'Glistening & Ultra-Smooth (Aquatic)' },
];

const MALE_TEXTURE_OPTIONS = [
  { value: 'Veined & Firm', label: 'Veined & Firm' },
  { value: 'Smooth & Heavy', label: 'Smooth & Heavy' },
  { value: 'Toned & Athletic', label: 'Toned & Athletic' },
  { value: 'Warm & Pulsing', label: 'Warm & Pulsing' },
  { value: 'Slender & Ultra-Sensitive', label: 'Slender & Ultra-Sensitive' },
  { value: 'Dense & Formidable', label: 'Dense & Formidable' },
  { value: 'Balanced & Firm', label: 'Balanced & Firm' },
  { value: 'Soft Fur-Ringed Base', label: 'Soft Fur-Ringed Base (Beastfolk)' },
  { value: 'Silky Fur-Dusted & Resilient', label: 'Silky Fur-Dusted & Resilient (Beastfolk)' },
  { value: 'Sleek Scaled Base & Firm', label: 'Sleek Scaled Base & Firm (Scaly/Draconic)' },
  { value: 'Sturdy Draconic Build', label: 'Sturdy Draconic Build (Scaly/Draconic)' },
];

export const StatusEffectBadge = ({ effect }) => {
  const { t } = useTranslation();
  const { effName, displayLabel, duration, durationUnit } = parseAndTranslateStatus(effect, t);
  
  const lower = effName.toLowerCase();
  const isNegative = ['bleed', 'poison', 'burn', 'stun', 'prone', 'weaken', 'wound', 'curse', 'drain', 'freeze'].some(k => lower.includes(k));
  const isPositive = ['shield', 'buff', 'bless', 'haste', 'regen', 'focus', 'inspire', 'guard', 'satisfied'].some(k => lower.includes(k));

  const badgeColor = isNegative 
    ? 'bg-red-950/70 text-red-300 border-red-700/70' 
    : isPositive 
      ? 'bg-emerald-950/70 text-emerald-300 border-emerald-700/70' 
      : 'bg-amber-950/70 text-amber-300 border-amber-700/70';

  const tooltip = duration !== null 
    ? `${displayLabel} (${duration}${durationUnit === 'm' ? ' min' : ' turns'} remaining)` 
    : displayLabel;

  return (
    <span 
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold border ${badgeColor}`}
      title={tooltip}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse shrink-0"></span>
      <span>{displayLabel}</span>
      {duration !== null && <span className="opacity-75 text-[9px] font-mono font-bold">({duration}{durationUnit})</span>}
    </span>
  );
};

const CharacterSheet = ({ character, onAllocateStat, onCastSpell, processingTurn }) => {
  const { t } = useTranslation();
  const [allocating, setAllocating] = useState(null);
  const [showAppearanceModal, setShowAppearanceModal] = useState(false);
  const [editBSize, setEditBSize] = useState(character?.appearance?.breast_size || character?.breast_size || 'average');
  const [editPSize, setEditPSize] = useState(character?.appearance?.penis_size || character?.penis_size || 'average');
  const [editTexture, setEditTexture] = useState(character?.appearance?.asset_texture || character?.asset_texture || '');
  const [savingApp, setSavingApp] = useState(false);

  useEffect(() => {
    if (character) {
      setEditBSize(character.appearance?.breast_size || character.breast_size || 'average');
      setEditPSize(character.appearance?.penis_size || character.penis_size || 'average');
      setEditTexture(character.appearance?.asset_texture || character.asset_texture || '');
    }
  }, [character?.id, showAppearanceModal]);

  const charGender = (character?.gender || '').toLowerCase();
  const isMale = ['male', 'man', 'boy', 'lord', 'he', 'him', 'his'].some(kw => charGender.includes(kw)) && !['female', 'woman', 'girl', 'lady', 'she', 'her'].some(kw => charGender.includes(kw));
  const isNsfw = String(character?.scenario || '').includes('nsfw') || Boolean(character?.appearance?.breast_size || character?.appearance?.penis_size);

  const handleSaveAppearance = async () => {
    setSavingApp(true);
    try {
      const finalBSize = isMale ? undefined : editBSize;
      const finalPSize = isMale ? editPSize : undefined;
      const res = await apiCall('/api/character/appearance', {
        method: 'POST',
        body: JSON.stringify({
          user_id: character.user_id,
          character_id: character.id,
          breast_size: finalBSize,
          penis_size: finalPSize,
          asset_texture: editTexture,
        }),
      });
      if (res?.character) {
        if (!character.appearance) character.appearance = {};
        if (isMale) {
          delete character.appearance.breast_size;
          character.appearance.penis_size = editPSize;
        } else {
          character.appearance.breast_size = editBSize;
          delete character.appearance.penis_size;
        }
        character.appearance.asset_texture = editTexture;
      }
      setShowAppearanceModal(false);
    } catch (err) {
      console.error('Failed to update appearance:', err);
    } finally {
      setSavingApp(false);
    }
  };

  if (!character) return null;

  const pendingPoints = character.pending_stat_points || 0;
  const tempHp = Number(character.temp_hp || character.combat_attributes?.temp_hp || 0);
  const isNonCombat = Boolean(character.is_non_combat || character.combat_attributes?.is_non_combat);
  const ca = character.combat_attributes || {};

  const handleAllocate = async (stat) => {
    if (!onAllocateStat || allocating) return;
    setAllocating(stat);
    try {
      await onAllocateStat(stat);
    } catch (err) {
      console.error("Allocation failed:", err);
    } finally {
      setAllocating(null);
    }
  };

  // Status effects parsing
  let statusList = [];
  if (Array.isArray(character.status_effects)) {
    statusList = character.status_effects;
  } else if (typeof character.status_effects === 'string' && character.status_effects.trim()) {
    try {
      statusList = JSON.parse(character.status_effects);
    } catch {
      statusList = character.status_effects.split(',').map(s => s.trim()).filter(Boolean);
    }
  }
  if (Array.isArray(statusList)) {
    statusList = statusList.filter(s => {
      const str = typeof s === 'string' ? s.trim() : (s?.name || '').trim();
      return str && !['[]', '{}', '""', "''", 'none', 'null'].includes(str.toLowerCase());
    });
  } else {
    statusList = [];
  }

  // Core 7 attributes
  const coreStats = [
    { key: 'str_', label: 'STR', name: 'STR', val: character.str_ ?? 1, fullLabel: t('stats.str', 'Strength'), desc: t('stats.str_desc', 'Melee damage & carrying capacity'), icon: '💪' },
    { key: 'agi', label: 'AGI', name: 'AGI', val: character.agi ?? 1, fullLabel: t('stats.agi', 'Agility'), desc: t('stats.agi_desc', 'Turn initiative & evasion chance'), icon: '🏹' },
    { key: 'int_', label: 'INT', name: 'INT', val: character.int_ ?? 1, fullLabel: t('stats.int', 'Intelligence'), desc: t('stats.int_desc', 'Spell power & EXP multiplier'), icon: '🧠' },
    { key: 'end_', label: 'END', name: 'END', val: character.end_ ?? 1, fullLabel: t('stats.end', 'Endurance'), desc: t('stats.end_desc', 'Maximum HP, Mana & stamina pool'), icon: '🛡️' },
    { key: 'per_', label: 'PER', name: 'PER', val: character.per_ ?? 1, fullLabel: t('stats.per', 'Perception'), desc: t('stats.per_desc', 'Noticing clues & ranged accuracy'), icon: '👁️' },
    { key: 'cha', label: 'CHA', name: 'CHA', val: character.cha ?? 1, fullLabel: t('stats.cha', 'Charisma'), desc: t('stats.cha_desc', 'Social persuasion & charm'), icon: '🗣️' },
    { key: 'luk', label: 'LUK', name: 'LUK', val: character.luk ?? 1, fullLabel: t('stats.luk', 'Luck'), desc: t('stats.luk_desc', 'Critical chance & serendipitous rolls'), icon: '🍀' },
  ];

  const combatGrid = [
    { label: 'ATK', val: ca.attack_power ?? ca.atk ?? 0 },
    { label: 'MATK', val: ca.magic_attack ?? ca.matk ?? ca.spell_power ?? 0 },
    { label: 'DEF', val: ca.defense ?? ca.def ?? 0 },
    { label: 'MDEF', val: ca.magic_defense ?? ca.mdef ?? ca.magic_resist ?? 0 },
    { label: 'Crit%', val: `${ca.crit_chance ?? ca.crit_pct ?? ca.crit ?? 0}%` },
    { label: 'EVA%', val: `${ca.evasion_chance ?? ca.evasion_pct ?? ca.evasion ?? ca.eva ?? 0}%` },
    { label: 'Block%', val: `${ca.block_chance ?? ca.block_pct ?? ca.block ?? 0}%` },
  ];

  const nextLevelXp = Math.max(100, (character.level || 1) * 100);
  const xpPct = Math.min(100, Math.round(((character.xp || 0) / nextLevelXp) * 100));

  return (
    <div className="bg-black/35 rounded-xl border border-fantasy-border p-3 sm:p-3.5 space-y-2.5 sm:space-y-3 select-none">
      
      {/* Hero Header */}
      <div className="flex items-start justify-between border-b border-fantasy-border/70 pb-3 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-[52px] h-[52px] bg-gradient-to-br from-fantasy-dark via-neutral-900 to-black border-2 border-fantasy-accent/60 rounded-xl flex items-center justify-center shadow-md shadow-black/80 shrink-0">
            <User size={26} className="text-fantasy-accent" />
          </div>
          <div className="min-w-0">
            <h2 className="font-rpg font-bold text-xl sm:text-2xl text-gray-100 leading-tight tracking-wide truncate">{character.name}</h2>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className="text-sm text-fantasy-accent font-bold uppercase tracking-wider">
                Lv.{character.level || 1} {character.char_class || character.class_name || 'Adventurer'}
              </span>
              {character.scenario && (
                <span className="text-[11px] px-2 py-0.5 bg-fantasy-border/80 text-gray-200 rounded-md font-semibold">
                  {character.scenario_display_name || character.scenario}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap text-xs text-gray-300">
              {character.race && (
                <span className="px-2 py-0.5 rounded-md bg-black/60 border border-fantasy-border/80 font-medium text-xs">{character.race}</span>
              )}
              {character.gender && (
                <span className="px-2 py-0.5 rounded-md bg-black/60 border border-fantasy-border/80 font-medium text-xs">{character.gender}</span>
              )}
              <span className="px-2 py-0.5 rounded-md bg-black/60 border border-fantasy-border/80 font-mono text-xs">
                📅 {character.days_adventured ?? 1}d
              </span>
              {isNsfw && !isMale && (
                <button
                  type="button"
                  onClick={() => setShowAppearanceModal(true)}
                  className="px-2.5 py-0.5 rounded-md bg-pink-950/70 hover:bg-pink-900/90 border border-pink-700/70 text-pink-300 font-semibold text-xs flex items-center gap-1 transition-colors"
                  title="Click to customize breast size & tactile flavor"
                >
                  {(() => {
                    const rawBSize = character.appearance?.breast_size || character.breast_size || 'Modest B-Cup';
                    const rawTex = character.appearance?.asset_texture || character.asset_texture || '';
                    const fused = formatFusedAsset(rawBSize, rawTex, false, t);
                    return (
                      <span>🔞 {t('anatomy.breast_size', 'Breast Size')}: {fused}</span>
                    );
                  })()}
                </button>
              )}
              {isNsfw && isMale && (
                <button
                  type="button"
                  onClick={() => setShowAppearanceModal(true)}
                  className="px-2.5 py-0.5 rounded-md bg-purple-950/70 hover:bg-purple-900/90 border border-purple-700/70 text-purple-300 font-semibold text-xs flex items-center gap-1 transition-colors"
                  title="Click to customize penis size & tactile flavor"
                >
                  {(() => {
                    const rawPSize = character.appearance?.penis_size || character.penis_size || 'Average';
                    const rawTex = character.appearance?.asset_texture || character.asset_texture || '';
                    const fused = formatFusedAsset(rawPSize, rawTex, true, t);
                    return (
                      <span>🔞 {t('anatomy.penis_size', 'Penis Size')}: {fused}</span>
                    );
                  })()}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Currency Display */}
        <div className="flex items-center gap-1.5 bg-black/60 border border-amber-800/60 px-3 py-1.5 rounded-lg text-amber-300 font-mono text-sm sm:text-base font-bold shadow-sm shrink-0">
          <Coins size={16} className="text-amber-400" />
          <span>{character.gold !== undefined ? character.gold : 0}</span>
          <span className="text-xs text-amber-500 font-extrabold">G</span>
        </div>
      </div>

      {/* Roleplay Mode Notice */}
      {isNonCombat && (
        <div className="bg-cyan-950/40 border border-cyan-800/60 px-3 py-1.5 rounded-lg text-xs text-cyan-200 flex items-center gap-2 shadow-sm">
          <Sparkles size={14} className="text-cyan-400 shrink-0" />
          <span className="leading-tight">{t('stats.social_scenario_notice', 'Social / Roleplay Scenario: Attributes scale social influence and stamina.')}</span>
        </div>
      )}

      {/* Vitals (HP, Temp Shield & MP) */}
      <div className="space-y-2 bg-black/45 p-3 rounded-lg border border-fantasy-border/60 shadow-sm">
        {tempHp > 0 && (
          <div className="flex justify-end mb-0.5">
            <span className="text-[10px] font-mono font-bold px-2 py-0.2 rounded bg-cyan-950/90 text-cyan-300 border border-cyan-600/70 flex items-center gap-1">
              <Shield size={10} /> +{tempHp} {t('inventory.shield', 'Shield')}
            </span>
          </div>
        )}
        <StatBar 
          label={t('stats.hp')} current={character.hp} max={character.max_hp} 
          icon={Heart} color={{ text: 'text-health', bg: 'bg-health' }} 
          extraText={tempHp > 0 ? `+${tempHp} Shield` : null}
        />
        <StatBar 
          label={t('stats.mp')} current={character.mp} max={character.max_mp} 
          icon={Zap} color={{ text: 'text-mana', bg: 'bg-mana' }} 
        />
        {/* XP Bar */}
        <div className="pt-1.5 border-t border-fantasy-border/30 space-y-1">
          <div className="flex justify-between items-center text-xs text-gray-200">
            <span className="uppercase font-semibold tracking-wider text-gray-400 text-[11px] flex items-center gap-1">
              <Sparkles size={11} className="text-purple-400" />
              <span>{t('stats.xp')}</span>
            </span>
            <span className="font-mono text-xs font-semibold text-purple-200">{character.xp || 0} / {nextLevelXp} XP ({xpPct}%)</span>
          </div>
          <div className="h-2 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/50 p-0.5">
            <div 
              className="h-full bg-purple-500 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${xpPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* Dynamic Clothing Status */}
      {character.clothing_status && (
        <div className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-black/45 border border-fantasy-border/50 text-xs">
          <span className="text-gray-300 font-medium flex items-center gap-1.5">
            <span className="text-sm">👔</span>
            <span>{t('stats.clothing_status', 'Clothing Status')}:</span>
          </span>
          <span className="font-semibold text-gray-100 bg-neutral-900/90 px-2.5 py-0.5 rounded border border-neutral-700 text-xs">
            {character.clothing_status}
          </span>
        </div>
      )}

      {/* Active Status Effects */}
      {statusList && statusList.length > 0 && (
        <div className="bg-black/45 p-2.5 rounded-lg border border-fantasy-border/50 shadow-sm space-y-1.5">
          <div className="text-[11px] uppercase font-bold text-gray-300 flex items-center gap-1">
            <AlertCircle size={13} className="text-amber-400" />
            <span>{t('stats.active_conditions', 'Active Conditions')}</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {statusList.map((eff, idx) => (
              <StatusEffectBadge key={idx} effect={eff} />
            ))}
          </div>
        </div>
      )}

      {/* Pending Stat Points Alert */}
      {pendingPoints > 0 && (
        <div className="bg-amber-950/45 border border-amber-500/60 p-2.5 rounded-lg flex items-center justify-between text-xs text-amber-200 shadow-sm animate-pulse">
          <div className="flex items-center gap-1.5">
            <Sparkles size={14} className="text-amber-400" />
            <span className="font-bold">
              {pendingPoints === 1
                ? t('stats.unspent_points_one', { count: 1, defaultValue: '1 unspent point!' })
                : t('stats.unspent_points_other', { count: pendingPoints, defaultValue: `${pendingPoints} unspent points!` })}
            </span>
          </div>
          <span className="text-[11px] uppercase font-extrabold text-amber-300 tracking-wider bg-amber-900/50 px-2 py-0.5 rounded border border-amber-600/50">
            {t('stats.allocate_below', 'Allocate Below')}
          </span>
        </div>
      )}

      {/* Core S.P.E.C.I.A.L. Attributes Grid */}
      <div className="space-y-1.5">
        <div className="text-xs uppercase font-bold text-gray-200 tracking-wider flex justify-between items-center">
          <span className="flex items-center gap-1">
            <span>✨</span>
            <span>{t('stats.special_attributes', 'S.P.E.C.I.A.L. Attributes')}</span>
          </span>
          <span className="text-[11px] text-gray-400 font-mono bg-black/60 px-1.5 py-0.2 rounded border border-fantasy-border/60">
            {t('stats.slots_label', 'Slots')}: {character.used_inventory_slots ?? 0} / {character.inventory_capacity ?? 10}
          </span>
        </div>
        <div className="grid grid-cols-4 gap-1.5 sm:gap-2">
          {coreStats.map(st => (
            <div 
              key={st.key}
              className="bg-gradient-to-b from-black/55 to-black/80 p-2 rounded-lg border border-fantasy-border/70 hover:border-fantasy-accent/60 transition-all flex flex-col justify-between min-h-[70px] sm:min-h-[74px] shadow-sm relative group"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-gray-200 uppercase tracking-wider">{st.label}</span>
                  <span className="text-[11px] opacity-75">{st.icon}</span>
                </div>
                <div className="text-[9.5px] text-gray-400 font-medium truncate max-w-full" title={st.desc}>
                  {st.fullLabel}
                </div>
              </div>
              
              <div className="font-mono text-lg sm:text-xl font-bold text-amber-300 my-0.5 text-center">{st.val}</div>
              
              {/* Stat Allocation Plus Button */}
              {pendingPoints > 0 && (
                <button
                  onClick={() => handleAllocate(st.name)}
                  disabled={allocating !== null}
                  className="mt-0.5 flex items-center justify-center gap-0.5 w-full py-0.5 bg-amber-500/25 hover:bg-amber-500/40 text-amber-300 border border-amber-500/50 rounded text-[10px] font-bold transition-all disabled:opacity-50"
                  title={`Add +1 to ${st.fullLabel}`}
                >
                  <Plus size={10} />
                  <span>{t('stats.add', 'Add')}</span>
                </button>
              )}
            </div>
          ))}

          {/* Capacity stat tile */}
          <div className="bg-gradient-to-b from-black/55 to-black/80 p-2 rounded-lg border border-fantasy-border/70 flex flex-col justify-between min-h-[70px] sm:min-h-[74px] shadow-sm text-center">
            <div>
              <div className="text-xs font-bold text-gray-300 uppercase tracking-wider">{t('stats.slots_label', 'Slots')}</div>
              <div className="text-[9.5px] text-gray-400 font-medium">Capacity</div>
            </div>
            <div className="font-mono text-xs sm:text-sm font-bold text-gray-200 my-auto">
              {character.used_inventory_slots ?? 0} / {character.inventory_capacity ?? 10}
            </div>
          </div>
        </div>
      </div>

      {/* Derived Combat Attributes Grid */}
      <div className="pt-1.5 border-t border-fantasy-border/40 space-y-1.5">
        <div className="text-xs uppercase font-bold text-gray-300 tracking-wider">
          <span>{t('stats.combat_tactical_stats', 'Combat & Tactical Stats')}</span>
        </div>
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-1 text-center">
          {combatGrid.map((cg) => (
            <div key={cg.label} className="bg-black/45 border border-fantasy-border/60 hover:border-fantasy-border/90 rounded-lg p-1.5 shadow-sm transition-colors">
              <div className="text-[9.5px] font-bold text-gray-400 uppercase tracking-wider">{cg.label}</div>
              <div className="text-xs font-mono font-bold text-gray-100 mt-0.5">{cg.val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Learned Spells / Grimoire (Only shown if character has learned spells) */}
      {Array.isArray(character.learned_spells) && character.learned_spells.length > 0 && (
        <div className="pt-1.5 border-t border-fantasy-border/40 space-y-1.5">
          <div className="text-xs uppercase font-bold text-indigo-300 tracking-wider flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <BookOpen size={14} className="text-indigo-400" />
              <span>{t('character.grimoire', 'Grimoire')} ({character.learned_spells.length})</span>
            </span>
            <span className="text-[11px] text-gray-400 font-mono">{t('character.learned_spells', 'Learned Spells')}</span>
          </div>
          <div className="space-y-1.5 max-h-48 overflow-y-auto custom-scrollbar pr-1">
            {character.learned_spells.map((sp, idx) => {
              const mpCost = Number(sp.mp_cost || 0);
              const canAffordMp = (character.mp ?? 0) >= mpCost;
              return (
                <div
                  key={sp.id || idx}
                  className="bg-black/60 border border-indigo-900/60 rounded-lg p-2 flex flex-col gap-1 shadow-sm"
                >
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="text-xs font-bold text-indigo-200 truncate">{sp.name}</span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {sp.tier_name && (
                        <span className="text-[9px] uppercase px-1.5 py-0.2 rounded bg-indigo-950/90 text-indigo-300 border border-indigo-800/60 font-semibold">
                          {sp.tier_name}
                        </span>
                      )}
                      {onCastSpell ? (
                        <button
                          type="button"
                          disabled={!canAffordMp || processingTurn}
                          onClick={() => onCastSpell(sp)}
                          title={canAffordMp ? `Cast ${sp.name} (${mpCost} MP)` : `Requires ${mpCost} MP`}
                          className="px-2 py-0.5 rounded bg-indigo-600/30 hover:bg-indigo-500/50 text-indigo-200 border border-indigo-500/60 text-[11px] font-mono font-bold flex items-center gap-1 disabled:opacity-40 transition-colors"
                        >
                          <Zap size={10} className="text-blue-300" />
                          <span>{t('character.cast', 'Cast')} ({mpCost} MP)</span>
                        </button>
                      ) : (
                        <span className="text-[11px] font-mono text-blue-400 flex items-center gap-0.5 font-semibold">
                          <Zap size={10} /> {mpCost} MP
                        </span>
                      )}
                    </div>
                  </div>
                  {sp.description && (
                    <p className="text-[11px] text-gray-300 leading-relaxed">{sp.description}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Intimate Physical Anatomy Live Customization Modal */}
      {showAppearanceModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="relative w-full max-w-md bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl overflow-hidden p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-fantasy-border/60 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-lg">🔞</span>
                <div>
                  <h3 className="font-rpg font-bold text-sm text-fantasy-accent">
                    {t('character.customize_anatomy', 'Customize Physical Anatomy')}
                  </h3>
                  <p className="text-[10px] text-gray-400">
                    {t('character.anatomy_desc', "Live update your character's assets & tactile textures")}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowAppearanceModal(false)}
                className="text-gray-400 hover:text-white p-1"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3.5 text-xs">
              {isMale ? (
                <div>
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-purple-300 mb-1">
                    {t('character.penis_size_tier', 'Penis Size Tier')}
                  </label>
                  <select
                    value={editPSize}
                    onChange={(e) => setEditPSize(e.target.value)}
                    className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                  >
                    <option value="small">Petite / Modest (Compact)</option>
                    <option value="average">Proportional (Average)</option>
                    <option value="large">Well-Endowed / Formidable (Large)</option>
                    <option value="huge">Massive / Heavy (Huge)</option>
                  </select>
                </div>
              ) : (
                <div>
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-pink-300 mb-1">
                    {t('character.breast_size_tier', 'Breast Size Tier')}
                  </label>
                  <select
                    value={editBSize}
                    onChange={(e) => setEditBSize(e.target.value)}
                    className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                  >
                    <option value="flat">Flat (AA-Cup / Barely There)</option>
                    <option value="small">Petite / Modest (A-B Cup)</option>
                    <option value="average">Proportional (C-Cup)</option>
                    <option value="large">Voluptuous / Full (D-DD Cup)</option>
                    <option value="huge">Bountiful / Massive (E+ Cup)</option>
                  </select>
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-300">
                    {t('character.tactile_texture', 'Tactile Texture / Feature')} ({isMale ? 'Phallus' : 'Breasts'})
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      const pool = isMale ? MALE_TEXTURE_OPTIONS : FEMALE_TEXTURE_OPTIONS;
                      setEditTexture(pool[Math.floor(Math.random() * pool.length)].value);
                    }}
                    className="text-[10px] text-pink-400 hover:text-pink-300 flex items-center gap-1 font-semibold"
                  >
                    <Sparkles size={11} /> {t('character.roll_feature', 'Roll Feature')}
                  </button>
                </div>
                <select
                  value={editTexture}
                  onChange={(e) => setEditTexture(e.target.value)}
                  className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                >
                  <option value="">Auto-Assign from Race &amp; Build (Dynamic Roll)</option>
                  {(isMale ? MALE_TEXTURE_OPTIONS : FEMALE_TEXTURE_OPTIONS).map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-fantasy-border/60">
              <button
                type="button"
                onClick={() => setShowAppearanceModal(false)}
                className="px-3 py-1.5 rounded border border-fantasy-border text-xs text-gray-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveAppearance}
                disabled={savingApp}
                className="px-4 py-1.5 rounded bg-fantasy-accent hover:bg-amber-400 text-black font-bold text-xs uppercase disabled:opacity-50 transition-colors"
              >
                {savingApp ? t('common.saving', 'Saving...') : t('common.save_changes', 'Save Changes')}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default CharacterSheet;
