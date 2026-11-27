import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  BookOpen,
  ChevronDown,
  Cpu,
  Heart,
  Plus,
  Shield,
  Shirt,
  Sparkles,
  Swords,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import { apiCall } from '../../api/client';
import { AcrylicModal, CollapsibleSection, MotionButton } from '../Common/MotionPrimitives';
import CurrencyBadge from '../Common/CurrencyBadge';
import { formatGender, formatRace, formatStature, formatPhysique, normalizeStatureClient, normalizePhysiqueClient } from '../../utils/npcDemographics';
import {
  REAR_SIZE_OPTIONS,
  STATURE_OPTIONS,
  classifyAssetSizeTierClient,
  classifyRearSizeTierClient,
  formatAssetTexture,
  formatFusedRear,
  getAllowedPhysiqueOptions,
  getAllowedRearTextureOptions,
  getAllowedTextureOptions,
  getSpeciesSurfaceClient,
  healPhysiqueForSelection,
  healRearTextureForSelection,
  healTextureForSelection,
  isFemaleGender,
  isFeralRearExcluded,
  isMaleGender,
  normalizeAssetTextureClient,
  rollClientAssetTexture,
  rollClientBuild,
  rollClientRearTexture,
  stripRearTextureFromSizeClient,
  stripTextureFromSizeClient,
} from '../../utils/anatomyOptions';

const getScenarioSkillsMeta = (scenarioKey) => {
  const key = String(scenarioKey || 'fantasy').trim().toLowerCase();
  if (key.includes('anomalous')) {
    return {
      labelKey: 'character.skills_abilities',
      defaultLabel: 'Abilities',
      icon: Zap,
    };
  }
  if (key.includes('cyberpunk')) {
    return {
      labelKey: 'character.skills_cyberware',
      defaultLabel: 'Cyberware & Skills',
      icon: Cpu,
    };
  }
  if (key.includes('sci_fi') || key.includes('scifi')) {
    return {
      labelKey: 'character.skills_tech',
      defaultLabel: 'Tech & Skills',
      icon: Cpu,
    };
  }
  if (key.includes('steampunk')) {
    return {
      labelKey: 'character.skills_gadgets',
      defaultLabel: 'Gadgets & Skills',
      icon: Wrench,
    };
  }
  if (key.includes('post_apocalypse') || key.includes('postapoc')) {
    return {
      labelKey: 'character.skills_perks',
      defaultLabel: 'Survival Skills',
      icon: Zap,
    };
  }
  if (key.includes('high_school') || key.includes('highschool') || key.includes('slice_of_life')) {
    return {
      labelKey: 'character.skills_generic',
      defaultLabel: 'Skills',
      icon: Zap,
    };
  }
  return {
    labelKey: 'character.grimoire',
    defaultLabel: 'Grimoire',
    icon: BookOpen,
  };
};

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
          <span className="font-mono tabular-nums text-gray-100 font-bold text-xs">{safeCurrent} / {safeMax}</span>
          <span className="text-[10px] font-mono tabular-nums text-gray-400 font-medium">({pct}%)</span>
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
  const rawRem = typeof effect === 'object' && effect !== null
    ? (effect.remaining_duration ?? effect.duration ?? null)
    : null;
  let duration = rawRem !== null && rawRem !== undefined && Number(rawRem) > 0 ? Number(rawRem) : null;
  let durationUnit = typeof effect === 'object' && effect?.duration_type === 'minutes' ? 'm' : 't';
  const stacks = typeof effect === 'object' && effect !== null
    ? Math.max(1, Number(effect.intensity_stacks || effect.stacks || 1))
    : 1;

  // Support bracketed duration strings like "Refractory Recovery [28 min]" or "Aroused [3 turns]"
  const match = typeof effName === 'string' ? effName.match(/^(.*?)\s*\[(\d+)\s*(min|m|turns?|t)\]$/i) : null;
  if (match) {
    effName = match[1].trim();
    duration = Number(match[2]);
    durationUnit = match[3].toLowerCase().startsWith('m') ? 'm' : 't';
  }

  const displayLabel = effName.includes(' & ')
    ? effName
        .split(' & ')
        .map(part => {
          const pk = part.trim().toLowerCase().replace(/[\s-]+/g, '_');
          return t(`conditions.${pk}`, part.trim());
        })
        .join(' & ')
    : t(`conditions.${effName.toLowerCase().replace(/[\s-]+/g, '_')}`, effName);

  const stackSuffix = stacks > 1 ? ` x${stacks}` : '';
  const formattedText = duration !== null && duration > 0
    ? `${displayLabel}${stackSuffix} [${duration}${durationUnit}]`
    : `${displayLabel}${stackSuffix}`;

  return { effName, displayLabel, duration, durationUnit, stacks, formattedText };
};

const formatTitle = (str) => {
  if (!str) return '';
  return String(str).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

const formatFusedAsset = (sizeStr, texStr, isMale = false, t = null) => {
  const s = String(sizeStr || (isMale ? 'Average' : 'Modest B-Cup')).replace(/^[()]+|[()]+$/g, '').trim();
  const normTex = normalizeAssetTextureClient(texStr, isMale);
  const texTranslated = normTex ? formatAssetTexture(normTex, isMale, t) : '';
  const baseSize = stripTextureFromSizeClient(s, isMale) || s;

  const bareFemale = { flat: 'AA-Cup', small: 'B-Cup', average: 'C-Cup', large: 'D-Cup', huge: 'E-Cup' };
  const bareMale = { flat: 'Tiny', small: 'Compact', average: 'Average', large: 'Large', huge: 'Huge' };
  const sLow = baseSize.toLowerCase().trim();
  const normalizedBase = !isMale && bareFemale[sLow]
    ? bareFemale[sLow]
    : isMale && bareMale[sLow]
      ? bareMale[sLow]
      : baseSize;

  const bKey = normalizedBase.toLowerCase().replace(/[\s-]+/g, '_');
  const bTranslated = t ? t(`anatomy.${bKey}`, normalizedBase) : normalizedBase;

  if (!texTranslated) return formatTitle(bTranslated);

  if (!isMale) {
    const cupMatch = normalizedBase.match(/\b([A-Ha-h]+(?:\+)?-Cup)\b/i);
    if (cupMatch) {
      const cupPart = cupMatch[1].toUpperCase().replace(/-CUP$/, '-Cup');
      return `${formatTitle(texTranslated)} ${cupPart}`;
    }
    const redundant = ['generous', 'voluptuous', 'modest', 'petite', 'heavy', 'bountiful', 'shapely', 'toned', 'firm', 'soft', 'full', 'small', 'large', 'average'];
    const filtered = normalizedBase.split(/\s+/).filter(w => !redundant.includes(w.toLowerCase())).join(' ').trim();
    if (filtered) return `${formatTitle(texTranslated)} ${formatTitle(filtered)}`;
    return `${formatTitle(texTranslated)} ${formatTitle(bTranslated)}`;
  } else {
    const inchMatch = normalizedBase.match(/(\d+(?:\.\d+)?\s*(?:"|inch(?:es)?))/i);
    if (inchMatch) {
      let inchPart = inchMatch[1].trim();
      if (/inch/i.test(inchPart)) {
        const num = (inchPart.match(/\d+(?:\.\d+)?/) || [])[0];
        inchPart = `${num}"`;
      }
      return `${formatTitle(texTranslated)} ${inchPart}`;
    }
    const redundant = ['thick', 'long', 'massive', 'compact', 'slender', 'sturdy', 'dense', 'toned', 'formidable', 'large', 'huge', 'small'];
    const filtered = normalizedBase.split(/\s+/).filter(w => !redundant.includes(w.toLowerCase())).join(' ').trim();
    if (filtered) return `${formatTitle(texTranslated)} ${formatTitle(filtered)}`;
    return `${formatTitle(texTranslated)} ${formatTitle(bTranslated)}`;
  }
};

export const StatusEffectBadge = ({ effect }) => {
  const { t } = useTranslation();
  const { effName, displayLabel, duration, durationUnit, stacks } = parseAndTranslateStatus(effect, t);
  
  const lower = effName.toLowerCase();
  const isNegative = ['bleed', 'poison', 'burn', 'stun', 'prone', 'weaken', 'wound', 'curse', 'drain', 'freeze'].some(k => lower.includes(k));
  const isPositive = ['shield', 'buff', 'bless', 'haste', 'regen', 'focus', 'inspire', 'guard', 'satisfied'].some(k => lower.includes(k));

  const badgeColor = isNegative 
    ? 'bg-red-950/70 text-red-300 border-red-700/70' 
    : isPositive 
      ? 'bg-emerald-950/70 text-emerald-300 border-emerald-700/70' 
      : 'bg-amber-950/70 text-amber-300 border-amber-700/70';

  const stackLabel = stacks > 1 ? ` x${stacks}` : '';
  const tooltip = duration !== null && duration > 0
    ? `${displayLabel}${stackLabel} (${duration}${durationUnit === 'm' ? ' min' : ' turns'} remaining)` 
    : `${displayLabel}${stackLabel}`;

  return (
    <span 
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold border ${badgeColor}`}
      title={tooltip}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current motion-safe:animate-pulse shrink-0"></span>
      <span>{displayLabel}{stackLabel}</span>
      {duration !== null && duration > 0 && <span className="opacity-75 text-[9px] font-mono font-bold">({duration}{durationUnit})</span>}
    </span>
  );
};

const CharacterSheet = ({
  character,
  scenario = null,
  playerProfile = null,
  onAllocateStat,
  onCastSpell,
  onRefreshCharacter = null,
  processingTurn,
}) => {
  const { t } = useTranslation();
  const [allocating, setAllocating] = useState(null);
  const [showAppearanceModal, setShowAppearanceModal] = useState(false);
  const [editBSize, setEditBSize] = useState(character?.appearance?.breast_size || character?.breast_size || 'average');
  const [editPSize, setEditPSize] = useState(character?.appearance?.penis_size || character?.penis_size || 'average');
  const [editTexture, setEditTexture] = useState(character?.appearance?.asset_texture || character?.asset_texture || '');
  const [editRSize, setEditRSize] = useState(character?.appearance?.rear_size || character?.rear_size || 'average');
  const [editRTexture, setEditRTexture] = useState(character?.appearance?.rear_texture || character?.rear_texture || '');
  const [savingApp, setSavingApp] = useState(false);
  const [specialOpen, setSpecialOpen] = useState(true);
  const [combatStatsOpen, setCombatStatsOpen] = useState(true);
  const [skillsOpen, setSkillsOpen] = useState(true);

  const isMale = isMaleGender(character?.gender);
  const isFemale = isFemaleGender(character?.gender);
  const feralRearExcluded = isFeralRearExcluded(character?.race);
  const charPresent = Boolean(character);
  const charStature = normalizeStatureClient(character?.appearance?.stature || character?.stature) || 'average';
  const charPhysique = healPhysiqueForSelection(normalizePhysiqueClient(character?.appearance?.physique || character?.physique) || 'Average', character?.gender, charStature, character?.race) || 'Average';
  const charBSizeRaw = character?.appearance?.breast_size || character?.breast_size || 'average';
  const charPSizeRaw = character?.appearance?.penis_size || character?.penis_size || 'average';
  const charRSizeRaw = character?.appearance?.rear_size || character?.rear_size || 'average';
  const charBSize = classifyAssetSizeTierClient(charBSizeRaw, false);
  const charPSize = classifyAssetSizeTierClient(charPSizeRaw, true);
  const charRSize = classifyRearSizeTierClient(charRSizeRaw);
  const charAssetTex = healTextureForSelection(
    character?.appearance?.asset_texture || character?.asset_texture || '',
    isMale,
    isMale ? charPSize : charBSize
  );
  const charRearTex = healRearTextureForSelection(
    character?.appearance?.rear_texture || character?.rear_texture || '',
    charRSize
  );

  const [editStature, setEditStature] = useState(charStature);
  const [editPhysique, setEditPhysique] = useState(charPhysique);
  const prevModalOpenRef = useRef(false);

  useEffect(() => {
    const opening = showAppearanceModal && !prevModalOpenRef.current;
    prevModalOpenRef.current = showAppearanceModal;
    if (charPresent && opening) {
      setEditStature(charStature);
      setEditPhysique(charPhysique);
      setEditBSize(charBSize);
      setEditPSize(charPSize);
      setEditTexture(charAssetTex);
      setEditRSize(charRSize);
      setEditRTexture(charRearTex);
    }
  }, [charPresent, charStature, charPhysique, charBSize, charPSize, charAssetTex, charRSize, charRearTex, showAppearanceModal]);

  const effScenario = String(scenario?.scenario || (typeof scenario === 'string' ? scenario : '') || character?.scenario || '').toLowerCase();
  const isNsfw = Boolean(
    scenario?.is_nsfw ||
    (Array.isArray(scenario?.tags) && scenario.tags.includes('nsfw')) ||
    effScenario.includes('nsfw')
  );
  const allowedEditPhysiques = getAllowedPhysiqueOptions(character?.gender, editStature, character?.race);
  const editSizeTier = isMale ? classifyAssetSizeTierClient(editPSize, true) : classifyAssetSizeTierClient(editBSize, false);
  const allowedEditTextures = getAllowedTextureOptions(isMale, editSizeTier);
  const editRearTier = classifyRearSizeTierClient(editRSize);
  const allowedEditRearTextures = getAllowedRearTextureOptions(editRearTier);
  const editSpeciesSurface = getSpeciesSurfaceClient(character?.race, character?.appearance?.skin_type);

  const handleSaveAppearance = async () => {
    setSavingApp(true);
    try {
      const payload = {
        user_id: character.user_id,
        character_id: character.id,
        stature: editStature || 'average',
        physique: healPhysiqueForSelection(editPhysique, character?.gender, editStature, character?.race) || 'Average',
      };
      if (isNsfw) {
        if (isMale) {
          payload.penis_size = editPSize !== charPSize ? editPSize : (stripTextureFromSizeClient(charPSizeRaw, true) || editPSize);
        } else {
          payload.breast_size = editBSize !== charBSize ? editBSize : (stripTextureFromSizeClient(charBSizeRaw, false) || editBSize);
        }
        payload.asset_texture = editTexture ? healTextureForSelection(editTexture, isMale, editSizeTier) : '';
        if (!feralRearExcluded) {
          payload.rear_size = editRSize !== charRSize ? editRSize : (stripRearTextureFromSizeClient(charRSizeRaw) || editRSize);
          payload.rear_texture = editRTexture ? healRearTextureForSelection(editRTexture, editRearTier) : '';
        }
      }
      const res = await apiCall('/api/character/appearance', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (res?.character) {
        await onRefreshCharacter?.();
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
  const skillsMeta = getScenarioSkillsMeta(scenario || character?.scenario);
  const SkillsIcon = skillsMeta.icon;

  return (
    <div className="space-y-3 select-none">
      
      {/* Hero Header */}
      <div className="space-y-2 border-b border-fantasy-border/35 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="grid place-items-center w-10 h-10 rounded-full bg-fantasy-accent/15 text-fantasy-accent font-bold shrink-0">
            {(character.name || '?').charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="hk-display font-bold text-lg text-gray-50 leading-tight truncate">{character.name}</h2>
            <p className="text-xs text-gray-400 truncate" title={`Lv.${character.level || 1} ${character.char_class || character.class_name || 'Adventurer'}`}>
              <span className="text-fantasy-accent font-semibold">Lv.{character.level || 1}</span> {character.char_class || character.class_name || 'Adventurer'}
            </p>
          </div>
          <CurrencyBadge
            amount={character.gold !== undefined ? character.gold : 0}
            scenario={scenario || character?.scenario}
            size="lg"
          />
        </div>
        <div className="flex items-center gap-1 flex-wrap text-xs text-gray-300">
          {character.race && <span className="hk-chip">{formatRace(character.race, t)}</span>}
          {character.gender && (() => {
            const gInfo = formatGender(character.gender, t);
            return (
              <span className="hk-chip">
                {gInfo ? `${gInfo.symbol ? `${gInfo.symbol} ` : ''}${gInfo.label}` : character.gender}
              </span>
            );
          })()}
          {playerProfile?.badge_label && (
            <span
              className={`px-2 py-0.5 rounded-md border font-semibold text-xs ${
                playerProfile.is_student
                  ? 'bg-sky-950/70 border-sky-700/60 text-sky-200'
                  : 'bg-emerald-950/70 border-emerald-700/60 text-emerald-200'
              }`}
            >
              {playerProfile.is_student
                ? t('character.profile_badge_student', playerProfile.badge_label)
                : playerProfile.origin_mode === 'adult'
                ? t('character.profile_badge_agent', playerProfile.badge_label)
                : t('character.profile_badge_adult', playerProfile.badge_label)}
            </span>
          )}
          {playerProfile?.is_student && playerProfile?.student_grade && (
            <span className="hk-chip text-indigo-200 border-indigo-700/50 bg-indigo-950/50">
              {playerProfile.student_grade}
            </span>
          )}
          <button
            type="button"
            onClick={() => setShowAppearanceModal(true)}
            className="px-2.5 py-0.5 rounded-md bg-fantasy-accent/15 hover:bg-fantasy-accent/25 border border-fantasy-accent/40 text-amber-200 font-semibold text-xs flex items-center gap-1 transition-colors"
            title={t('character.customize_build_tooltip', 'Click to customize height & physique')}
          >
            <span>📐 {[formatStature(charStature, t), formatPhysique(charPhysique, t)].filter(Boolean).join(' • ')}</span>
          </button>
              {isNsfw && (isFemale || Boolean(character.appearance?.breast_size || character.breast_size)) && (
                <button
                  type="button"
                  onClick={() => setShowAppearanceModal(true)}
                  className="px-2.5 py-0.5 rounded-md bg-pink-950/70 hover:bg-pink-900/90 border border-pink-700/70 text-pink-300 font-semibold text-xs flex items-center gap-1 transition-colors"
                  title={t('character.customize_breast_tooltip', 'Click to customize breast size & tactile flavor')}
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
                  title={t('character.customize_penis_tooltip', 'Click to customize penis size & tactile flavor')}
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
              {isNsfw && !feralRearExcluded && (
                <button
                  type="button"
                  onClick={() => setShowAppearanceModal(true)}
                  className="px-2.5 py-0.5 rounded-md bg-rose-950/70 hover:bg-rose-900/90 border border-rose-700/70 text-rose-200 font-semibold text-xs flex items-center gap-1 transition-colors"
                  title={t('character.customize_rear_tooltip', 'Click to customize rear size & tactile flavor')}
                >
                  {(() => {
                    const rawRSize = character.appearance?.rear_size || character.rear_size || 'average';
                    const rawRTex = character.appearance?.rear_texture || character.rear_texture || '';
                    const fusedRear = formatFusedRear(rawRSize, rawRTex, t).label || rawRSize;
                    return (
                      <span>🍑 {t('anatomy.rear_size', 'Rear')}: {fusedRear}</span>
                    );
                  })()}
                </button>
              )}
        </div>
      </div>

      {/* Roleplay Mode Notice */}
      {isNonCombat && (
        <div className="bg-cyan-950/40 border border-cyan-800/60 px-3 py-1.5 rounded-lg text-xs text-cyan-200 flex items-center gap-2 shadow-sm">
          <Sparkles size={14} className="text-cyan-400 shrink-0" />
          <span className="leading-tight">{t('stats.social_scenario_notice', 'Social / Roleplay Scenario: Attributes scale social influence and stamina.')}</span>
        </div>
      )}

      {/* Status Effect & Clothing Status Strip (Above Vitals) */}
      <div className="space-y-2 pb-2.5 border-b border-fantasy-border/35 text-xs">
        <div className="flex items-start justify-between gap-2">
          <span className="text-gray-300 font-medium flex items-center gap-1.5 min-w-0 pt-0.5">
            <Activity size={14} className="text-amber-400 shrink-0" />
            <span className="truncate">{t('stats.status_effect', 'Status Effect')}:</span>
          </span>
          {statusList && statusList.length > 0 ? (
            <div className="flex flex-wrap justify-end gap-1">
              {statusList.map((eff, idx) => (
                <StatusEffectBadge key={idx} effect={eff} />
              ))}
            </div>
          ) : (
            <span className="font-semibold text-gray-400 bg-gray-500/15 px-2.5 py-0.5 rounded-lg border border-fantasy-border/35 text-xs shrink-0">
              {t('stats.status_none', 'None')}
            </span>
          )}
        </div>

        {character.clothing_status && (
          <div className="flex items-center justify-between gap-2">
            <span className="text-gray-300 font-medium flex items-center gap-1.5 min-w-0">
              <Shirt size={14} className="text-sky-400 shrink-0" />
              <span className="truncate">{t('stats.clothing_status', 'Clothing Status')}:</span>
            </span>
            <span className="font-semibold text-gray-100 bg-gray-500/15 px-2.5 py-0.5 rounded-lg border border-fantasy-border/40 text-xs shrink-0">
              {character.clothing_status}
            </span>
          </div>
        )}
      </div>

      {/* Vitals (HP, Temp Shield & MP) */}
      <div className="space-y-2 pb-3 border-b border-fantasy-border/35">
        {tempHp > 0 && (
          <div className="flex justify-end mb-0.5">
            <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-cyan-950/90 text-cyan-300 border border-cyan-600/70 flex items-center gap-1">
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
            <span className="font-mono tabular-nums text-xs font-semibold text-purple-200">{character.xp || 0} / {nextLevelXp} XP ({xpPct}%)</span>
          </div>
          <div className="h-2 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/50 p-0.5">
            <div 
              className="h-full bg-purple-500 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${xpPct}%` }}
            />
          </div>
        </div>
      </div>

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
        <button
          type="button"
          onClick={() => setSpecialOpen((v) => !v)}
          aria-expanded={specialOpen}
          className="w-full py-1 text-xs uppercase font-bold text-gray-200 hover:text-fantasy-accent tracking-wider flex justify-between items-center transition-colors"
        >
          <span className="flex items-center gap-1.5 min-w-0">
            <Sparkles size={14} className="text-amber-400 shrink-0" />
            <span className="truncate">{t('stats.special_attributes', 'S.P.E.C.I.A.L. Attributes')}</span>
          </span>
          <ChevronDown
            size={14}
            className={`text-gray-400 shrink-0 transition-transform duration-200 ${specialOpen ? 'rotate-180' : ''}`}
          />
        </button>
        <CollapsibleSection isOpen={specialOpen}>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(5.6rem,1fr))] gap-2 pt-0.5">
            {coreStats.map(st => (
              <div 
                key={st.key}
                className="bg-gradient-to-b from-black/55 to-black/80 p-2.5 rounded-lg border border-fantasy-border/70 hover:border-fantasy-accent/60 transition-all flex flex-col justify-between min-h-[5.25rem] shadow-sm relative group"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-gray-200 uppercase tracking-wider">{st.label}</span>
                    <span className="text-[11px] opacity-75">{st.icon}</span>
                  </div>
                  <div className="text-[10.5px] text-gray-400 font-medium truncate max-w-full" title={st.desc}>
                    {st.fullLabel}
                  </div>
                </div>
                
                <div className="font-mono tabular-nums text-xl font-bold text-amber-300 my-0.5 text-center">{st.val}</div>
                
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
            <div className="bg-gradient-to-b from-black/55 to-black/80 p-2.5 rounded-lg border border-fantasy-border/70 flex flex-col justify-between min-h-[5.25rem] shadow-sm text-center">
              <div>
                <div className="text-xs font-bold text-gray-300 uppercase tracking-wider">{t('stats.slots_label', 'Slots')}</div>
                <div className="text-[10.5px] text-gray-400 font-medium">{t('character.capacity', 'Capacity')}</div>
              </div>
              <div className="font-mono tabular-nums text-xs sm:text-[0.875rem] font-bold text-gray-200 my-auto whitespace-nowrap">
                {character.used_inventory_slots ?? 0} / {character.inventory_capacity ?? 10}
              </div>
            </div>
          </div>
        </CollapsibleSection>
      </div>

      {/* Derived Combat Attributes Grid */}
      <div className="pt-1.5 border-t border-fantasy-border/40 space-y-1.5">
        <button
          type="button"
          onClick={() => setCombatStatsOpen((v) => !v)}
          aria-expanded={combatStatsOpen}
          className="w-full py-1 text-xs uppercase font-bold text-gray-300 hover:text-fantasy-accent tracking-wider flex justify-between items-center transition-colors"
        >
          <span className="flex items-center gap-1.5 min-w-0">
            <Swords size={14} className="text-rose-400 shrink-0" />
            <span className="truncate">{t('stats.combat_tactical_stats', 'Combat & Tactical Stats')}</span>
          </span>
          <ChevronDown
            size={14}
            className={`text-gray-400 shrink-0 transition-transform duration-200 ${combatStatsOpen ? 'rotate-180' : ''}`}
          />
        </button>
        <CollapsibleSection isOpen={combatStatsOpen}>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(4.6rem,1fr))] gap-1.5 text-center pt-0.5">
            {combatGrid.map((cg) => (
              <div key={cg.label} className="bg-black/45 border border-fantasy-border/60 hover:border-fantasy-border/90 rounded-lg p-2 shadow-sm transition-colors">
                <div className="text-[10px] font-bold text-gray-400 uppercase truncate">{cg.label}</div>
                <div className="text-[13px] font-mono tabular-nums font-bold text-gray-100 mt-0.5">{cg.val}</div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      </div>

      {/* Dynamic Scenario Skills / Abilities / Grimoire */}
      {Array.isArray(character.learned_spells) && character.learned_spells.length > 0 && (
        <div className="pt-1.5 border-t border-fantasy-border/40 space-y-1.5">
          <button
            type="button"
            onClick={() => setSkillsOpen((v) => !v)}
            aria-expanded={skillsOpen}
            className="w-full py-1 text-xs uppercase font-bold text-indigo-300 hover:text-indigo-200 tracking-wider flex items-center justify-between transition-colors"
          >
            <span className="flex items-center gap-1.5 min-w-0">
              <SkillsIcon size={14} className="text-indigo-400 shrink-0" />
              <span className="truncate">
                {t(skillsMeta.labelKey, skillsMeta.defaultLabel)} ({character.learned_spells.length})
              </span>
            </span>
            <ChevronDown
              size={14}
              className={`text-gray-400 shrink-0 transition-transform duration-200 ${skillsOpen ? 'rotate-180' : ''}`}
            />
          </button>
          <CollapsibleSection isOpen={skillsOpen}>
            <div className="space-y-1.5 max-h-72 overflow-y-auto custom-scrollbar pr-1 pt-0.5">
              {character.learned_spells.map((sp, idx) => {
                const mpCost = Number(sp.mp_cost || 0);
                const canAffordMp = (character.mp ?? 0) >= mpCost;
                return (
                  <div
                    key={sp.id || idx}
                    className="bg-black/60 border border-indigo-900/60 rounded-lg p-2.5 flex flex-col gap-1 shadow-sm"
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <span className="text-[13px] font-bold text-indigo-200 truncate">{sp.name}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {sp.tier_name && (
                          <span className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-indigo-950/90 text-indigo-300 border border-indigo-800/60 font-semibold">
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
                      <p className="text-xs text-gray-300 leading-relaxed">{sp.description}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </CollapsibleSection>
        </div>
      )}

      {/* Appearance & Physical Build Live Customization Modal */}
      <AcrylicModal
        isOpen={showAppearanceModal}
        onClose={() => setShowAppearanceModal(false)}
        label={t('character.customize_appearance', 'Customize Appearance')}
        maxWidthClass="max-w-md"
        zIndexClass="z-[100]"
        className="p-5 space-y-4"
      >
        <div className="flex items-center justify-between border-b border-fantasy-border/35 pb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-lg shrink-0">📐</span>
            <div className="min-w-0">
              <h3 className="font-rpg font-bold text-sm text-fantasy-accent truncate">
                {t('character.customize_appearance', 'Customize Appearance')}
              </h3>
              <p className="text-[10px] text-gray-400 truncate">
                {t('character.appearance_desc', "Live update your character's build and appearance")}
              </p>
            </div>
          </div>
          <MotionButton
            onClick={() => setShowAppearanceModal(false)}
            aria-label={t('common.close', 'Close')}
            className="hk-icon-btn h-7 min-w-7 shrink-0"
          >
            <X size={16} />
          </MotionButton>
        </div>

        <div className="space-y-4 text-xs">
          {/* Section 1: Physical Build (always shown for SFW & NSFW) */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <h4 className="text-[11px] uppercase tracking-wider font-bold text-amber-300">
                📐 {t('character.physical_build_section', 'Physical Build')}
              </h4>
              <button
                type="button"
                onClick={() => {
                  const rolled = rollClientBuild(character?.race, character?.gender);
                  setEditStature(rolled.stature);
                  setEditPhysique(rolled.physique);
                }}
                className="text-[10px] text-fantasy-accent hover:text-amber-300 flex items-center gap-1 font-semibold"
              >
                🎲 {t('build.roll_build', 'Roll Build')}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-gray-300 mb-1">
                  {t('build.height_label', 'Height')}
                </label>
                <select
                  value={editStature}
                  onChange={(e) => {
                    const nextStature = e.target.value;
                    setEditStature(nextStature);
                    setEditPhysique(healPhysiqueForSelection(editPhysique, character?.gender, nextStature, character?.race) || 'Average');
                  }}
                  className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                >
                  {STATURE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {t(opt.i18nKey, opt.fallback)}{opt.rangeHint ? ` ${opt.rangeHint}` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-gray-300 mb-1">
                  {t('build.physique_label', 'Physique')}
                </label>
                <select
                  value={editPhysique}
                  onChange={(e) => setEditPhysique(e.target.value)}
                  className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                >
                  {allowedEditPhysiques.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {t(opt.i18nKey, opt.fallback)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Section 2: Intimate Anatomy (NSFW scenarios only) */}
          {isNsfw && (
            <div className="space-y-3.5 pt-3 border-t border-fantasy-border/35">
              <h4 className="text-[11px] uppercase tracking-wider font-bold text-pink-300">
                🔞 {t('character.intimate_anatomy_section', 'Intimate Anatomy')}
              </h4>
              {isMale ? (
                <div>
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-purple-300 mb-1">
                    {t('character.penis_size_tier', 'Penis Size Tier')}
                  </label>
                  <select
                    value={editPSize}
                    onChange={(e) => {
                      const nextSz = e.target.value;
                      setEditPSize(nextSz);
                      if (editTexture) {
                        setEditTexture(healTextureForSelection(editTexture, true, classifyAssetSizeTierClient(nextSz, true)));
                      }
                    }}
                    className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                  >
                    <option value="small">{t('character.penis_compact', 'Petite / Modest (Compact)')}</option>
                    <option value="average">{t('character.penis_average', 'Proportional (Average)')}</option>
                    <option value="large">{t('character.penis_large', 'Well-Endowed / Formidable (Large)')}</option>
                    <option value="huge">{t('character.penis_huge', 'Massive / Heavy (Huge)')}</option>
                  </select>
                </div>
              ) : (
                <div>
                  <label className="block text-[11px] uppercase tracking-wider font-bold text-pink-300 mb-1">
                    {t('character.breast_size_tier', 'Breast Size Tier')}
                  </label>
                  <select
                    value={editBSize}
                    onChange={(e) => {
                      const nextSz = e.target.value;
                      setEditBSize(nextSz);
                      if (editTexture) {
                        setEditTexture(healTextureForSelection(editTexture, false, classifyAssetSizeTierClient(nextSz, false)));
                      }
                    }}
                    className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                  >
                    <option value="flat">{t('character.breast_flat', 'Flat (AA-Cup / Barely There)')}</option>
                    <option value="small">{t('character.breast_petite', 'Petite / Modest (A-B Cup)')}</option>
                    <option value="average">{t('character.breast_proportional', 'Proportional (C-Cup)')}</option>
                    <option value="large">{t('character.breast_voluptuous', 'Voluptuous / Full (D-DD Cup)')}</option>
                    <option value="huge">{t('character.breast_bountiful', 'Bountiful / Massive (E+ Cup)')}</option>
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
                      setEditTexture(rollClientAssetTexture(isMale, editSizeTier, character?.race, editPhysique));
                    }}
                    className="text-[10px] text-pink-400 hover:text-pink-300 flex items-center gap-1 font-semibold"
                  >
                    <Sparkles size={11} /> {t('character.roll_feature', 'Roll Feature')}
                  </button>
                </div>
                <select
                  value={editTexture}
                  onChange={(e) => setEditTexture(e.target.value)}
                  className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                >
                  <option value="">{t('character.auto_assign_anatomy', 'Auto-Assign from Race & Build (Dynamic Roll)')}</option>
                  {allowedEditTextures.map(opt => (
                    <option key={opt.value} value={opt.value}>{t(opt.i18nKey, opt.fallback)}</option>
                  ))}
                </select>
              </div>

              {/* Rear / Ass Anatomy (All Genders, NSFW only, non-feral) */}
              {!feralRearExcluded && (
                <div className="pt-2.5 border-t border-fantasy-border/25 space-y-3">
                  <div>
                    <label className="block text-[11px] uppercase tracking-wider font-bold text-rose-300 mb-1">
                      {t('character.rear_size_tier', 'Rear / Ass Size Tier')}
                    </label>
                    <select
                      value={editRSize}
                      onChange={(e) => {
                        const nextSz = e.target.value;
                        setEditRSize(nextSz);
                        if (editRTexture) {
                          setEditRTexture(healRearTextureForSelection(editRTexture, classifyRearSizeTierClient(nextSz)));
                        }
                      }}
                      className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                    >
                      {REAR_SIZE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{t(opt.selectKey, opt.selectFallback)}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-300">
                        {t('character.rear_texture', 'Rear Tactile Texture')}
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setEditRTexture(rollClientRearTexture(editRearTier, character?.race, editPhysique));
                        }}
                        className="text-[10px] text-rose-300 hover:text-rose-200 flex items-center gap-1 font-semibold"
                      >
                        <Sparkles size={11} /> {t('character.roll_rear_feature', 'Roll Rear Feature')}
                      </button>
                    </div>
                    <select
                      value={editRTexture}
                      onChange={(e) => setEditRTexture(e.target.value)}
                      className="w-full bg-fantasy-dark/70 border border-fantasy-border/60 p-2 rounded-lg text-xs text-gray-100"
                    >
                      <option value="">{t('character.auto_assign_anatomy', 'Auto-Assign from Race & Build (Dynamic Roll)')}</option>
                      {allowedEditRearTextures.map((opt) => (
                        <option key={opt.value} value={opt.value}>{t(opt.i18nKey, opt.label)}</option>
                      ))}
                    </select>
                  </div>

                  {editSpeciesSurface && (
                    <p className="mt-1.5 text-[10px] text-amber-300/90 flex items-center gap-1">
                      ✨ {t('anatomy.species_surface.label', 'Auto species surface')}:{' '}
                      <strong className="font-semibold">{t(editSpeciesSurface.i18nKey, editSpeciesSurface.fallback)}</strong>
                    </p>
                  )}
                </div>
              )}
              {feralRearExcluded && editSpeciesSurface && (
                <p className="mt-1.5 text-[10px] text-amber-300/90 flex items-center gap-1">
                  ✨ {t('anatomy.species_surface.label', 'Auto species surface')}:{' '}
                  <strong className="font-semibold">{t(editSpeciesSurface.i18nKey, editSpeciesSurface.fallback)}</strong>
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-fantasy-border/35">
          <MotionButton
            onClick={() => setShowAppearanceModal(false)}
            className="px-3 py-1.5 rounded-lg border border-fantasy-border/60 text-xs text-gray-300 hover:text-white hover:bg-gray-500/15"
          >
            {t('common.cancel', 'Cancel')}
          </MotionButton>
          <MotionButton
            onClick={handleSaveAppearance}
            disabled={savingApp}
            className="px-4 py-1.5 rounded-lg bg-fantasy-accent hover:bg-amber-400 text-black font-bold text-xs uppercase disabled:opacity-50 transition-colors"
          >
            {savingApp ? t('common.saving', 'Saving...') : t('common.save_changes', 'Save Changes')}
          </MotionButton>
        </div>
      </AcrylicModal>

    </div>
  );
};

export default CharacterSheet;
