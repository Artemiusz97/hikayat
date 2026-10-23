import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Sparkles, Swords, ScrollText, Heart, ShieldAlert, Coins, Gift, ChevronDown, ChevronUp,
  Compass, MapPin, Map, Calendar, Users
} from 'lucide-react';
import { getOutcomeTierTheme } from '../StoryFeed/HistoryCard';
import { StatusEffectBadge } from './CharacterSheet';
import { getRelationshipTier } from './CodexPanel';

const parseLocationTiers = (rawLocation, fallbackTitle) => {
  const loc = String(rawLocation || fallbackTitle || 'Local Region').trim();
  const parts = loc.split(/\s*(?:➔|->|>)\s*/).map(s => s.trim()).filter(Boolean);
  return parts.length > 0 ? parts : ['Local Region'];
};

const parseClues = (raw) => {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .map(c => String(typeof c === 'string' ? c : (c?.text || c?.lead || '')).replace(/^[\s•*\-\d.)]+/, '').trim())
      .filter(Boolean);
  }
  return String(raw)
    .split(/\r?\n/)
    .map(line => line.replace(/^[\s•*\-\d.)]+/, '').trim())
    .filter(line => line.length > 0);
};

const normalizeClue = (str) => {
  return String(str || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
};

export const extractTurnOutcomes = (entry, turnNumber, seenClues = new Set(), seenCompletedSubs = new Set()) => {
  if (!entry || typeof entry !== 'object' || entry.type === 'scene') return null;

  const outcome = typeof entry.outcome === 'object' && entry.outcome ? entry.outcome : {};
  const rawCheck = entry.check || outcome.check || outcome.skill_check || {};
  const checkTier = entry.tier || entry.check_tier || outcome.check_tier || rawCheck.check_tier || rawCheck.tier || null;
  const tierLabel = entry.tier_label || outcome.tier_label || rawCheck.tier_label || checkTier || null;
  const checkStat = entry.stat || outcome.stat || rawCheck.stat || null;
  const checkChance = entry.chance ?? outcome.chance ?? rawCheck.chance ?? rawCheck.success_pct ?? null;
  const checkRoll = entry.roll ?? outcome.roll ?? rawCheck.roll ?? null;

  const xpGained = Number(entry.xp_gained || outcome.xp_gained || 0);
  const levelsGained = Array.isArray(entry.levels_gained) ? entry.levels_gained : [];
  const mpSpent = Number(entry.mp_spent || 0);

  // Character outcomes (HP, MP, Gold, Items, Status)
  const charOutcomes = Array.isArray(entry.character_outcomes)
    ? entry.character_outcomes
    : (Array.isArray(outcome.character_outcomes) ? outcome.character_outcomes : []);

  let hpDelta = 0;
  let mpDelta = mpSpent > 0 ? -mpSpent : 0;
  let goldDelta = Number(entry.gold_delta ?? outcome.gold_delta ?? outcome.gold_change ?? 0);
  const itemsGained = new Set();
  const itemsLost = new Set();
  const statusEffects = new Set();

  (Array.isArray(entry.items_gained) ? entry.items_gained : []).forEach(it => {
    const name = typeof it === 'string' ? it : it?.name;
    if (name) itemsGained.add(name);
  });
  (Array.isArray(entry.loot) ? entry.loot : []).forEach(it => {
    const name = typeof it === 'string' ? it : it?.name;
    if (name) itemsGained.add(name);
  });

  charOutcomes.forEach(co => {
    if (!co || typeof co !== 'object') return;
    hpDelta += Number(co.hp_change || 0);
    mpDelta += Number(co.mp_change || 0);
    goldDelta += Number(co.gold_change || 0);
    (Array.isArray(co.items_gained) ? co.items_gained : []).forEach(it => {
      const name = typeof it === 'string' ? it : it?.name;
      if (name) itemsGained.add(name);
    });
    (Array.isArray(co.loot) ? co.loot : []).forEach(it => {
      const name = typeof it === 'string' ? it : it?.name;
      if (name) itemsGained.add(name);
    });
    (Array.isArray(co.items_lost) ? co.items_lost : []).forEach(it => {
      const name = typeof it === 'string' ? it : it?.name;
      if (name) itemsLost.add(name);
    });
    (Array.isArray(co.status_effects) ? co.status_effects : []).forEach(st => {
      const name = String(typeof st === 'string' ? st : (st?.name || '')).trim();
      if (name && !['[]', '{}', '""', "''", 'none', 'null'].includes(name.toLowerCase())) {
        statusEffects.add(name);
      }
    });
  });

  // Relationships & Factions
  const rawRelUpdates = (Array.isArray(entry.relationship_updates) ? entry.relationship_updates : (outcome.relationship_updates || []))
    .filter(r => r && (typeof r === 'string' || Number(r.delta_score ?? r.delta ?? 0) !== 0 || r.milestone_event));
  const seenRelNames = new Set();
  const relUpdates = [];
  rawRelUpdates.forEach(r => {
    const rawName = typeof r === 'string' ? r : (r.npc_name || r.npc || r.name || '');
    const cleanName = String(rawName).trim().toLowerCase();
    if (cleanName) {
      if (!seenRelNames.has(cleanName)) {
        seenRelNames.add(cleanName);
        relUpdates.push(r);
      }
    } else {
      relUpdates.push(r);
    }
  });
  const facUpdates = (Array.isArray(entry.faction_updates) ? entry.faction_updates : (outcome.faction_updates || []))
    .filter(f => f && (typeof f === 'string' || Number(f.delta_score ?? f.delta ?? 0) !== 0));

  // Quests & Objectives with strict turn-by-turn Clue & Sub-objective deduplication
  const rawQuests = Array.isArray(entry.quest_updates) ? entry.quest_updates : (outcome.quest_updates || []);
  const questUpdates = [];
  rawQuests.forEach(q => {
    if (!q || typeof q !== 'object') return;

    // Filter clues to only ones discovered on THIS specific turn
    const allClues = parseClues(q.current_clues);
    const newCluesThisTurn = [];
    allClues.forEach(clue => {
      const norm = normalizeClue(clue);
      if (norm && !seenClues.has(norm)) {
        seenClues.add(norm);
        newCluesThisTurn.push(clue);
      }
    });

    // Filter completed sub-quests to only ones completed on THIS specific turn
    const rawSubs = Array.isArray(q.completed_sub_quest_ids) ? q.completed_sub_quest_ids : [];
    const newCompletedSubs = [];
    const qKey = String(q.quest_id || q.title || 'quest').toLowerCase().trim();
    rawSubs.forEach(subId => {
      const subKey = `${qKey}_sub_${subId}`;
      if (!seenCompletedSubs.has(subKey)) {
        seenCompletedSubs.add(subKey);
        newCompletedSubs.push(subId);
      }
    });

    const hasStatusChange = q.status === 'Completed' || q.status === 'Failed';
    const hasCompletedSubs = newCompletedSubs.length > 0;
    const hasNewClues = newCluesThisTurn.length > 0;

    // Only surface quest update if something NEW actually happened this turn
    if (hasStatusChange || hasCompletedSubs || hasNewClues) {
      questUpdates.push({
        ...q,
        completed_sub_quest_ids: newCompletedSubs,
        new_clues: newCluesThisTurn,
      });
    }
  });

  // Combat Log
  const rawCombat = entry.combat_log || outcome.combat_log || outcome._combat_log || [];
  const combatLines = Array.isArray(rawCombat)
    ? rawCombat.filter(Boolean).map(String)
    : (typeof rawCombat === 'string' && rawCombat.trim() ? rawCombat.split('\n').filter(Boolean) : []);
  if (entry.enemy_attack_notice) {
    combatLines.push(String(entry.enemy_attack_notice));
  }

  const intimateUpdate = outcome.intimate_update || entry.intimate_update || null;
  const refractoryNotice = outcome._refractory_recovered_notice || entry._refractory_recovered_notice || null;

  return {
    turnNumber,
    label: entry.label || entry.summary || 'Action',
    characterName: entry.character_name || 'Hero',
    checkTier,
    tierLabel,
    checkStat,
    checkChance,
    checkRoll,
    xpGained,
    levelsGained,
    hpDelta,
    mpDelta,
    goldDelta,
    itemsGained: Array.from(itemsGained),
    itemsLost: Array.from(itemsLost),
    statusEffects: Array.from(statusEffects),
    relUpdates,
    facUpdates,
    questUpdates,
    combatLines,
    intimateUpdate,
    refractoryNotice,
  };
};

const WorldOutcomeSidebar = ({
  session,
  onOpenWorldMap,
  onSelectContact,
  isMobileDrawer = false,
}) => {
  const { t } = useTranslation();
  const [expandedTurnMap, setExpandedTurnMap] = useState({});

  const toggleTurnExpanded = (turnNumber, defaultExpanded) => {
    setExpandedTurnMap((prev) => {
      const current = prev[turnNumber] !== undefined ? prev[turnNumber] : defaultExpanded;
      return { ...prev, [turnNumber]: !current };
    });
  };

  const locationTiers = parseLocationTiers(session?.current_location, session?.scene_title);
  const currentPlace = locationTiers[locationTiers.length - 1];
  const parentRegions = locationTiers.slice(0, -1);

  const npcs = Array.isArray(session?.current_npcs) ? session.current_npcs : [];
  const dialoguePartners = new Set(
    (() => {
      let list = [];
      if (Array.isArray(session?.dialogue_partners)) {
        list = session.dialogue_partners;
      } else if (session?.dialogue_partner) {
        const dp = session.dialogue_partner;
        if (Array.isArray(dp)) {
          list = dp;
        } else if (typeof dp === 'string') {
          const trimmed = dp.trim();
          if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
            try {
              const parsed = JSON.parse(trimmed);
              list = Array.isArray(parsed) ? parsed : [dp];
            } catch {
              list = [dp];
            }
          } else {
            list = [dp];
          }
        }
      }
      return list;
    })().map(n => String(n || '').toLowerCase().trim()).filter(Boolean)
  );

  // Extract turn outcomes chronologically with persistent deduplication, then display newest first
  const rawHistory = Array.isArray(session?.history) ? session.history : [];
  let actionCount = 0;
  const turnOutcomes = [];
  const seenClues = new Set();
  const seenCompletedSubs = new Set();

  rawHistory.forEach((entry) => {
    if (entry && typeof entry === 'object' && entry.type !== 'scene') {
      actionCount += 1;
      const parsed = extractTurnOutcomes(entry, actionCount, seenClues, seenCompletedSubs);
      if (parsed) {
        turnOutcomes.push(parsed);
      }
    }
  });
  turnOutcomes.reverse();

  const rawTime = session?.formatted_time || 'Day 1 • 08:00';
  const localizedTime = rawTime.replace(/\bDay\b/gi, t('scene.day', 'Day'));

  return (
    <div className="flex flex-col h-full bg-fantasy-panel text-gray-200 select-none">
      {/* SECTION 1: World & Scene Context (Location, Map, Day/Time, Present NPCs) - Desktop only (hidden in mobile drawer) */}
      {!isMobileDrawer && (
        <div className="p-3.5 sm:p-4 border-b border-fantasy-border bg-black/40 space-y-3 shrink-0">
          {/* Header Row: Region & Day/Time */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs sm:text-sm font-rpg font-bold uppercase tracking-wider text-fantasy-accent">
              <Compass size={16} />
              <span>{t('scene.title', 'Scene & World')}</span>
            </div>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-950/70 border border-amber-600/60 text-[11px] font-mono font-bold text-amber-300 shadow-sm">
              <Calendar size={12} className="text-amber-400" />
              <span>{localizedTime}</span>
            </span>
          </div>

          {/* Location Card + World Map Button */}
          <div className="p-3 rounded-xl bg-gradient-to-b from-black/70 to-black/90 border border-fantasy-border/90 space-y-2.5 shadow-md">
            <div className="flex items-start gap-2">
              <MapPin size={16} className="text-fantasy-accent shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1">
                {parentRegions.length > 0 && (
                  <div className="text-[11px] font-mono text-gray-400 truncate mb-0.5">
                    {parentRegions.join(' ➔ ')}
                  </div>
                )}
                <div className="text-sm sm:text-base font-rpg font-bold text-amber-100 leading-snug break-words">
                  {currentPlace}
                </div>
              </div>
            </div>

            {onOpenWorldMap && (
              <button
                type="button"
                onClick={onOpenWorldMap}
                className="w-full py-2 px-3 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/30 border border-fantasy-accent/50 hover:border-fantasy-accent text-fantasy-accent text-xs font-bold flex items-center justify-center gap-1.5 transition-all shadow-sm active:scale-[0.99]"
              >
                <Map size={14} />
                <span>{t('scene.open_map', 'Open World Map & Fast Travel')}</span>
              </button>
            )}
          </div>

          {/* Present NPCs in Scene */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs font-mono uppercase tracking-wider text-gray-300">
              <span className="flex items-center gap-1.5">
                <Users size={14} className="text-fantasy-accent/90" />
                <span>{t('scene.present', 'Present in Scene')}</span>
              </span>
              <span className="px-1.5 py-0.2 rounded bg-black/70 border border-fantasy-border text-[11px] text-gray-200 font-bold">
                {npcs.length}
              </span>
            </div>

            {npcs.length > 0 ? (
              <div className="flex flex-col gap-1.5 max-h-64 sm:max-h-72 overflow-y-auto custom-scrollbar pr-0.5">
                {npcs.map((npc, idx) => {
                  const name = typeof npc === 'string' ? npc : (npc?.name || 'Unknown');
                  const isPartner = dialoguePartners.has(name.toLowerCase().trim());
                  const clothing = typeof npc === 'object' ? npc?.clothing_status : null;
                  const statusEffects = (typeof npc === 'object' && Array.isArray(npc?.status_effects) ? npc.status_effects : []).filter(eff => {
                    const str = (typeof eff === 'string' ? eff : (eff?.name || '')).trim();
                    const low = str.toLowerCase();
                    return str && str !== '[]' && str !== '{}' && str !== '""' && str !== "''" && low !== 'none' && low !== 'null' && low !== 'present' && low !== 'absent' && low !== 'nearby';
                  });

                  // 1. Affinity Meter resolution
                  const score = npc?.relationship_score ?? npc?.affinity ?? 0;
                  const isRomantic = (npc?.track === 'romantic') || (npc?.relations?.track === 'romantic');
                  const tier = getRelationshipTier(score, isRomantic ? 'romantic' : 'platonic', t);

                  // 2. Excitement Meter resolution (when applicable)
                  const physExc = session?.physical_state?.excitement;
                  const physActors = (physExc?.actors && typeof physExc.actors === 'object') ? physExc.actors : {};
                  let actorExc = (npc?.excitement_meter !== undefined && npc?.excitement_meter !== null) ? {
                    meter: Number(npc.excitement_meter),
                    status: npc.excitement_status,
                    climaxed: npc.excitement_climaxed,
                    active: npc.excitement_active
                  } : null;

                  if (!actorExc && physActors) {
                    const cleanN = name.toLowerCase().trim();
                    for (const [k, v] of Object.entries(physActors)) {
                      const cleanK = String(k || '').toLowerCase().trim();
                      if (cleanK && (cleanK === cleanN || cleanN.includes(cleanK) || cleanK.includes(cleanN))) {
                        actorExc = v;
                        break;
                      }
                    }
                  }

                  if (!actorExc) {
                    const latestTurn = turnOutcomes[0];
                    const intUp = latestTurn?.intimateUpdate;
                    if (intUp?.active) {
                      const cleanN = name.toLowerCase().trim();
                      const pMatch = (intUp.partner_meters || []).find(pm => {
                        const pName = String(pm?.name || '').toLowerCase().trim();
                        return pName && (pName === cleanN || cleanN.includes(pName) || pName.includes(cleanN));
                      });
                      if (pMatch) {
                        actorExc = pMatch;
                      } else if (intUp.partner_meter !== undefined && isPartner) {
                        actorExc = {
                          meter: intUp.partner_meter,
                          status: intUp.act_type,
                          climaxed: intUp.simultaneous_partner_climax
                        };
                      }
                    }
                  }

                  const excMeter = actorExc?.meter !== undefined && actorExc?.meter !== null ? Number(actorExc.meter) : null;
                  const isExcActive = Boolean(actorExc?.active || physExc?.active || (excMeter !== null && excMeter > 0));
                  const showExcitement = isExcActive && excMeter !== null;

                  return (
                    <div
                      key={`${name}-${idx}`}
                      className={`flex flex-col gap-1.5 p-2 rounded-lg border text-xs transition-all shadow-sm ${
                        isPartner
                          ? 'bg-purple-950/45 border-purple-500/60 shadow-purple-950/40'
                          : 'bg-black/50 border-neutral-800/90 hover:border-neutral-700 hover:bg-black/70'
                      }`}
                    >
                      {/* Row 1: Dot + Character Name + Talking Badge + Clothing Status */}
                      <div className="flex items-center justify-between gap-1.5">
                        <button
                          type="button"
                          onClick={() => onSelectContact && onSelectContact(name)}
                          className={`inline-flex items-center gap-1.5 font-bold transition-colors text-left truncate ${
                            isPartner
                              ? 'text-purple-200 hover:text-purple-100'
                              : 'text-gray-100 hover:text-fantasy-accent'
                          }`}
                          title={onSelectContact ? `View ${name} in Codex` : name}
                        >
                          <span className={`w-2 h-2 rounded-full shrink-0 ${isPartner ? 'bg-purple-400 animate-pulse' : 'bg-emerald-400'}`} />
                          <span className="truncate max-w-[150px] text-xs">{name}</span>
                          {isPartner && (
                            <span className="text-[9px] font-mono uppercase px-1.5 py-0.2 rounded bg-purple-900/90 text-purple-200 font-bold shrink-0">
                              {t('scene.talking', 'Talking')}
                            </span>
                          )}
                        </button>
                        {clothing && (
                          <span className="text-[10px] font-mono px-2 py-0.2 rounded bg-neutral-900/95 border border-neutral-700 text-gray-300 font-normal shrink-0">
                            {clothing}
                          </span>
                        )}
                      </div>

                      {/* Row 2: Affinity Meter Bar */}
                      <div className="space-y-0.5 pt-1 border-t border-fantasy-border/25">
                        <div className="flex items-center justify-between text-[10px]">
                          <span className={`font-semibold ${tier.color}`}>
                            {tier.label}
                          </span>
                          <span className="font-mono font-bold text-gray-300">
                            {score > 0 ? `+${score}` : score}
                          </span>
                        </div>
                        <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
                          <div 
                            className={`h-full ${tier.bg} transition-all duration-300`}
                            style={{ width: `${Math.max(5, Math.min(100, ((score + 100) / 400) * 100))}%` }}
                          />
                        </div>
                      </div>

                      {/* Row 3: Excitement Meter (When Applicable) */}
                      {showExcitement && (
                        <div className="space-y-0.5 pt-1 border-t border-rose-900/40">
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="font-semibold text-rose-300 flex items-center gap-1">
                              <span>💋</span>
                              <span>{t('scene.excitement', 'Excitement')}</span>
                              {actorExc?.climaxed && <span className="text-amber-300 font-bold ml-0.5">💥</span>}
                              {actorExc?.status && (
                                <span className="text-[9px] font-mono font-normal text-rose-400 ml-0.5">
                                  ({actorExc.status})
                                </span>
                              )}
                            </span>
                            <span className="font-mono font-bold text-rose-300">
                              {excMeter}%
                            </span>
                          </div>
                          <div className="h-1.5 w-full bg-neutral-900/90 rounded-full overflow-hidden border border-rose-900/60 p-0.5">
                            <div 
                              className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r from-rose-500 via-pink-500 to-red-500 ${
                                excMeter >= 80 ? 'animate-pulse' : ''
                              }`}
                              style={{ width: `${Math.min(100, Math.max(0, excMeter))}%` }}
                            />
                          </div>
                        </div>
                      )}

                      {/* Row 4: Active Status Effects */}
                      {statusEffects && statusEffects.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-1 border-t border-fantasy-border/20">
                          {statusEffects.map((eff, eIdx) => (
                            <StatusEffectBadge key={eIdx} effect={eff} />
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-black/40 border border-neutral-800 text-center text-xs text-gray-400 italic">
                {t('scene.no_npcs', 'No other characters in the immediate area.')}
              </div>
            )}
          </div>
        </div>
      )}

      {/* SECTION 2: Outcomes & Changes Header */}
      <div className="px-3.5 py-2 border-b border-fantasy-border bg-black/60 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 text-xs font-rpg font-bold uppercase tracking-wider text-fantasy-accent">
          <ScrollText size={14} />
          <span>{t('scene.outcomes_title', 'Outcomes & Changes')}</span>
        </div>
        <span className="text-[11px] font-mono font-bold text-gray-300 bg-black/70 px-2 py-0.5 rounded border border-fantasy-border">
          {turnOutcomes.length === 1
            ? t('scene.turns_count_one', { count: 1, defaultValue: '1 Turn' })
            : t('scene.turns_count_other', { count: turnOutcomes.length, defaultValue: `${turnOutcomes.length} Turns` })}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2.5">
        {turnOutcomes.length === 0 ? (
          /* Clean & balanced empty state that does not force a scrollbar */
          <div className="text-center py-10 px-4 text-xs text-gray-400 space-y-2.5">
            <div className="w-10 h-10 rounded-xl bg-fantasy-dark border border-fantasy-accent/40 flex items-center justify-center mx-auto shadow-md">
              <Sparkles size={18} className="text-fantasy-accent" />
            </div>
            <p className="font-semibold text-gray-200 text-sm">{t('scene.no_outcomes_title', 'No Turn Outcomes Yet')}</p>
            <p className="text-xs text-gray-400 leading-relaxed max-w-xs mx-auto">
              {t('scene.no_outcomes_desc', 'Skill check rolls, EXP gains, combat logs, loot, and newly discovered clues will appear here as your story unfolds.')}
            </p>
          </div>
        ) : (
          turnOutcomes.map((item, idx) => {
            const isLatest = idx === 0;
            const isExpanded = expandedTurnMap[item.turnNumber] !== undefined ? expandedTurnMap[item.turnNumber] : isLatest;
            const theme = getOutcomeTierTheme(item.checkTier, item.tierLabel, item.checkStat);
            const statPrefix = item.checkStat && item.checkStat !== 'NONE' && item.checkStat !== 'FREE' ? `${item.checkStat} • ` : '';
            const tierText = (item.tierLabel || theme.defaultLabel).toUpperCase();
            const chanceText =
              item.checkChance !== null && item.checkChance !== undefined && item.checkStat !== 'NONE' && item.checkStat !== 'FREE'
                ? ` (${Math.round(Number(item.checkChance))}%)`
                : '';

            return (
              <React.Fragment key={`turn-outcome-${item.turnNumber}`}>
                {!isExpanded ? (
                  /* Compact Collapsed Row */
                  <div
                    onClick={() => toggleTurnExpanded(item.turnNumber, isLatest)}
                    className={`rounded-lg cursor-pointer transition-all ${
                      isLatest
                        ? 'p-2.5 bg-gradient-to-b from-amber-950/30 to-black/85 border border-fantasy-accent/60 hover:border-fantasy-accent'
                        : 'p-2 bg-black/50 border border-fantasy-border/60 hover:border-fantasy-border hover:bg-black/70'
                    }`}
                    title="Click to expand turn details"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {isLatest ? (
                          <span className="px-1.5 py-0.5 rounded bg-fantasy-accent/20 border border-fantasy-accent/60 text-fantasy-accent text-[10px] font-mono font-bold uppercase shrink-0">
                            {t('scene.turn_number', { number: item.turnNumber, defaultValue: `Turn #${item.turnNumber}` })}
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono uppercase text-gray-400 font-semibold shrink-0">
                            {t('scene.turn_number', { number: item.turnNumber, defaultValue: `Turn #${item.turnNumber}` })}
                          </span>
                        )}
                        <span className="text-xs text-gray-200 truncate font-medium">
                          {item.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className={`inline-flex items-center gap-1 rounded-full border font-mono font-bold uppercase px-2 py-0.5 text-[10px] ${theme.badgeClass}`}>
                          <span>{theme.icon}</span>
                          <span>{tierText}</span>
                        </span>
                        <ChevronDown size={14} className="text-gray-400" />
                      </div>
                    </div>
                  </div>
                ) : (
                  /* Expanded Outcome Box */
                  <div
                    className={`rounded-xl transition-all ${
                      isLatest
                        ? 'p-3.5 bg-gradient-to-b from-amber-950/25 via-black/85 to-fantasy-panel/95 border-2 border-fantasy-accent/80 shadow-[0_0_20px_rgba(217,119,6,0.18)] ring-1 ring-fantasy-accent/40 space-y-2.5 relative overflow-hidden'
                        : 'p-2.5 bg-black/50 border border-fantasy-border/70 hover:border-fantasy-border hover:bg-black/70 space-y-2'
                    }`}
                  >
                    {/* Turn Header & Check Result Badge */}
                    <div className="flex items-center justify-between gap-2">
                      {isLatest ? (
                        <div className="flex items-center gap-2">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-fantasy-accent opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-fantasy-accent"></span>
                          </span>
                          <span className="px-2 py-0.5 rounded-full bg-fantasy-accent/20 border border-fantasy-accent/60 text-fantasy-accent text-[11px] font-mono font-bold uppercase tracking-wider shadow-sm">
                            {t('scene.latest_outcome', { number: item.turnNumber, defaultValue: `Latest Outcome • Turn #${item.turnNumber}` })}
                          </span>
                        </div>
                      ) : (
                        <span className="text-[10px] font-mono uppercase tracking-wider text-gray-400 font-semibold">
                          {t('scene.turn_number', { number: item.turnNumber, defaultValue: `Turn #${item.turnNumber}` })}
                        </span>
                      )}

                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full border font-mono font-bold uppercase shadow-sm ${
                            isLatest ? 'px-2.5 py-0.5 text-[11px]' : 'px-2 py-0.5 text-[10px]'
                          } ${theme.badgeClass}`}
                        >
                          <span>{theme.icon}</span>
                          <span>{statPrefix}{tierText}{chanceText}</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => toggleTurnExpanded(item.turnNumber, isLatest)}
                          className="p-1 rounded text-gray-400 hover:text-gray-200 hover:bg-white/10 transition-colors"
                          title="Collapse outcome"
                        >
                          <ChevronUp size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Chosen Action Label */}
                    <div
                      className={`font-semibold leading-snug ${
                        isLatest
                          ? 'text-xs sm:text-sm text-white pl-2.5 py-0.5 bg-white/[0.05] border-l-4 border-fantasy-accent rounded-r'
                          : 'text-xs text-gray-200 pl-2 py-0.5 border-l-2 border-fantasy-accent/40'
                      }`}
                    >
                      {item.label}
                    </div>

                    {/* Mechanical Deltas Pills (EXP, Level Up, HP, MP, Gold, Loot, Status) */}
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {item.xpGained > 0 && (
                        <span
                          className={`inline-flex items-center gap-1 rounded bg-amber-950/70 border border-amber-600/60 text-amber-300 font-mono font-bold ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          }`}
                        >
                          ✨ +{item.xpGained} EXP
                        </span>
                      )}

                      {item.levelsGained.length > 0 && (
                        <span
                          className={`inline-flex items-center gap-1 rounded bg-yellow-500/30 border border-yellow-400 text-yellow-300 font-mono font-extrabold animate-pulse ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          }`}
                        >
                          🎉 {t('outcomes.level_up', 'LEVEL UP')} (Lv.{item.levelsGained[item.levelsGained.length - 1]})
                        </span>
                      )}

                      {item.hpDelta !== 0 && (
                        <span
                          className={`inline-flex items-center gap-1 rounded border font-mono font-bold ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          } ${
                            item.hpDelta > 0
                              ? 'bg-emerald-950/70 border-emerald-700/60 text-emerald-300'
                              : 'bg-red-950/80 border-red-700/70 text-red-300'
                          }`}
                        >
                          <Heart size={isLatest ? 11 : 9} />
                          {item.hpDelta > 0 ? `+${item.hpDelta}` : item.hpDelta} HP
                        </span>
                      )}

                      {item.mpDelta !== 0 && (
                        <span
                          className={`inline-flex items-center gap-1 rounded border font-mono font-bold ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          } ${
                            item.mpDelta > 0
                              ? 'bg-blue-950/70 border-blue-700/60 text-blue-300'
                              : 'bg-indigo-950/80 border-indigo-700/70 text-indigo-300'
                          }`}
                        >
                          💧 {item.mpDelta > 0 ? `+${item.mpDelta}` : item.mpDelta} MP
                        </span>
                      )}

                      {item.goldDelta !== 0 && (
                        <span
                          className={`inline-flex items-center gap-1 rounded border font-mono font-bold ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          } ${
                            item.goldDelta > 0
                              ? 'bg-amber-950/80 border-amber-600/60 text-amber-300'
                              : 'bg-orange-950/80 border-orange-700/60 text-orange-300'
                          }`}
                        >
                          <Coins size={isLatest ? 11 : 9} />
                          {item.goldDelta > 0 ? `+${item.goldDelta}` : item.goldDelta} Gold
                        </span>
                      )}

                      {item.itemsGained.map((it, iIdx) => (
                        <span
                          key={`gain-${iIdx}`}
                          className={`inline-flex items-center gap-1 rounded bg-cyan-950/70 border border-cyan-700/60 text-cyan-200 font-semibold ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          }`}
                        >
                          <Gift size={isLatest ? 11 : 9} /> +{it}
                        </span>
                      ))}

                      {item.itemsLost.map((it, iIdx) => (
                        <span
                          key={`lost-${iIdx}`}
                          className={`inline-flex items-center gap-1 rounded bg-neutral-900 border border-neutral-700 text-gray-400 line-through ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          }`}
                        >
                          -{it}
                        </span>
                      ))}

                      {item.statusEffects.map((st, sIdx) => (
                        <span
                          key={`st-${sIdx}`}
                          className={`inline-flex items-center gap-1 rounded bg-rose-950/70 border border-rose-700/60 text-rose-200 font-semibold ${
                            isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                          }`}
                        >
                          <ShieldAlert size={isLatest ? 11 : 9} /> {st}
                        </span>
                      ))}

                      {item.relUpdates.map((ru, rIdx) => {
                        const label = typeof ru === 'string'
                          ? ru
                          : `${ru.npc_name || ru.npc || ru.name || 'NPC'}: ${(ru.delta_score ?? ru.delta ?? 0) > 0 ? `+${ru.delta_score ?? ru.delta}` : (ru.delta_score ?? ru.delta ?? '')}`;
                        return (
                          <span
                            key={`rel-${rIdx}`}
                            className={`inline-flex items-center gap-1 rounded bg-pink-950/70 border border-pink-700/60 text-pink-200 font-semibold ${
                              isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                            }`}
                          >
                            💕 {label}
                          </span>
                        );
                      })}

                      {item.facUpdates.map((fu, fIdx) => {
                        const label = typeof fu === 'string'
                          ? fu
                          : `${fu.faction_name || fu.faction || fu.name || 'Faction'}: ${(fu.delta_score ?? fu.delta ?? 0) > 0 ? `+${fu.delta_score ?? fu.delta}` : (fu.delta_score ?? fu.delta ?? 0)} Rep`;
                        return (
                          <span
                            key={`fac-${fIdx}`}
                            className={`inline-flex items-center gap-1 rounded bg-purple-950/70 border border-purple-700/60 text-purple-200 font-semibold ${
                              isLatest ? 'px-2 py-0.5 text-xs' : 'px-1.5 py-0.5 text-[10px]'
                            }`}
                          >
                            🚩 {label}
                          </span>
                        );
                      })}
                    </div>

                    {/* Refractory Recovery Banner */}
                    {item.refractoryNotice && (
                      <div className="rounded-lg p-2 bg-emerald-950/50 border border-emerald-600/60 text-emerald-300 text-xs flex items-center gap-1.5">
                        <span className="text-sm">⚡</span>
                        <span className="font-semibold">{item.refractoryNotice}</span>
                      </div>
                    )}

                    {/* Intimate Excitement & Arousal Gauge Block */}
                    {item.intimateUpdate && item.intimateUpdate.active && (
                      <div
                        className={`rounded-lg space-y-1.5 border ${
                          isLatest
                            ? 'p-2.5 bg-rose-950/45 border-pink-600/60 text-xs shadow-sm'
                            : 'p-2 bg-rose-950/30 border-pink-800/40 text-[10px]'
                        }`}
                      >
                        <div className="flex items-center justify-between font-bold text-pink-300">
                          <span className="flex items-center gap-1">
                            <span>💋</span> Intimate Excitement & Arousal
                          </span>
                          <div className="flex items-center gap-1">
                            {item.intimateUpdate.mutual_group_climax && (
                              <span className="text-[9px] uppercase font-bold font-mono tracking-wider px-1.5 py-0.2 rounded bg-amber-500/30 text-amber-200 border border-amber-400/50 animate-pulse">
                                ✨ Group Climax
                              </span>
                            )}
                            {!item.intimateUpdate.mutual_group_climax && item.intimateUpdate.simultaneous_partner_climax && (
                              <span className="text-[9px] uppercase font-bold font-mono tracking-wider px-1.5 py-0.2 rounded bg-rose-500/30 text-rose-200 border border-rose-400/50 animate-pulse">
                                {item.intimateUpdate.partner_meters?.filter(p => p.climaxed).length > 2 ? '💥 Multi Climax' : '💥 Dual Climax'}
                              </span>
                            )}
                            {item.intimateUpdate.act_type && (
                              <span className="text-[9px] uppercase font-mono font-bold tracking-wider px-1.5 py-0.2 rounded bg-pink-900/60 text-pink-200">
                                {item.intimateUpdate.act_type === 'foreplay_nongenital' ? 'Foreplay' : item.intimateUpdate.act_type.replace(/_/g, ' ')}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Player Progress Bar */}
                        <div className="space-y-0.5">
                          <div className="flex justify-between items-center text-[10px]">
                            <span className="font-semibold text-pink-100">
                              {item.characterName} (You)
                              {item.intimateUpdate.player_climaxed && (
                                <span className="text-[10px] font-bold text-amber-300 ml-1">💥</span>
                              )}
                            </span>
                            <span className="font-mono text-pink-300 font-bold">
                              {item.intimateUpdate.player_meter}%
                              {item.intimateUpdate.player_delta > 0 && (
                                <span className="text-[9px] text-pink-400 font-normal ml-1">
                                  (+{item.intimateUpdate.player_delta}%)
                                </span>
                              )}
                            </span>
                          </div>
                          <div className="w-full bg-neutral-900/90 rounded-full h-1.5 sm:h-2 overflow-hidden border border-pink-900/60 p-0.5">
                            <div
                              className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r from-pink-500 via-rose-500 to-red-500 ${
                                item.intimateUpdate.player_meter >= 80 ? 'animate-pulse' : ''
                              }`}
                              style={{ width: `${Math.min(100, item.intimateUpdate.player_meter)}%` }}
                            />
                          </div>
                        </div>

                        {/* Partner Progress Bar(s) */}
                        {(item.intimateUpdate.partner_meters && item.intimateUpdate.partner_meters.length > 0
                          ? item.intimateUpdate.partner_meters
                          : [{
                              name: session?.dialogue_partner || item.intimateUpdate.partner_name || 'Partner',
                              meter: item.intimateUpdate.partner_meter,
                              delta: item.intimateUpdate.partner_delta
                            }]
                        ).map((p, pIdx) => (
                          <div key={`partner-meter-${pIdx}`} className="space-y-0.5">
                            <div className="flex justify-between items-center text-[10px]">
                              <span className="font-semibold text-pink-100">
                                {p.name || 'Partner'}
                                {p.climaxed && (
                                  <span className="text-[10px] font-bold text-amber-300 ml-1">💥</span>
                                )}
                                {!p.climaxed && (p.status?.includes('Recoiling') || p.status?.includes('Turned Off')) && (
                                  <span className="text-[10px] font-bold text-amber-400 ml-1" title={p.status}>⚠️</span>
                                )}
                              </span>
                              <span className="font-mono text-rose-300 font-bold">
                                {p.meter}%
                                {p.delta > 0 && (
                                  <span className="text-[9px] text-rose-400 font-normal ml-1">
                                    (+{p.delta}%)
                                  </span>
                                )}
                              </span>
                            </div>
                            <div className="w-full bg-neutral-900/90 rounded-full h-1.5 sm:h-2 overflow-hidden border border-rose-900/60 p-0.5">
                              <div
                                className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r from-rose-500 via-pink-500 to-red-500 ${
                                  p.meter >= 80 ? 'animate-pulse' : ''
                                }`}
                                style={{ width: `${Math.min(100, p.meter)}%` }}
                              />
                            </div>
                          </div>
                        ))}

                        {/* Sensitive Spot Notification */}
                        {item.intimateUpdate.sensitive_spot_matched && item.intimateUpdate.matched_spot && (
                          <div className="text-[10px] text-amber-300 font-semibold pt-0.5 flex items-center gap-1">
                            <span>✨</span> Sensitive Spot Triggered: {item.intimateUpdate.matched_spot} (+6% bonus!)
                          </div>
                        )}

                        {/* Climax & Refractory Alerts */}
                        {item.intimateUpdate.mutual_group_climax && (
                          <div className="text-[10px] text-pink-300 font-semibold pt-0.5 flex items-center gap-1">
                            <span>✨</span> Mutual Group Climax! Shared peak in passionate release.
                          </div>
                        )}
                        {!item.intimateUpdate.mutual_group_climax && item.intimateUpdate.simultaneous_partner_climax && (
                          <div className="text-[10px] text-pink-300 font-semibold pt-0.5 flex items-center gap-1">
                            <span>✨</span> Simultaneous Climax! Multiple partners peak together.
                          </div>
                        )}
                        {item.intimateUpdate.premature_finish && (
                          <div className="text-[10px] text-amber-300 font-semibold pt-0.5 flex items-center gap-1">
                            <span>⚠️</span> Spent: Stamina depleted while {
                              item.intimateUpdate.unsatisfied_partners && item.intimateUpdate.unsatisfied_partners.length >= 2
                                ? `${item.intimateUpdate.unsatisfied_partners.slice(0, -1).join(', ')} and ${item.intimateUpdate.unsatisfied_partners.slice(-1)} remain unsatisfied.`
                                : `${item.intimateUpdate.unsatisfied_partner || 'partner'} remains unsatisfied.`
                            }
                          </div>
                        )}
                      </div>
                    )}

                    {/* Quest & Objective Progress Block */}
                    {item.questUpdates.length > 0 && (
                      <div
                        className={`rounded-lg space-y-1.5 border ${
                          isLatest
                            ? 'p-2.5 bg-emerald-950/40 border-emerald-600/60 text-xs shadow-sm'
                            : 'p-2 bg-emerald-950/25 border-emerald-800/40 text-[10px]'
                        }`}
                      >
                        {item.questUpdates.map((q, qIdx) => (
                          <div key={`q-${qIdx}`} className="space-y-1">
                            <div className="flex items-center justify-between gap-1.5 font-bold text-emerald-300">
                              <span className="truncate">📜 {q.title || q.quest_id || 'Quest Updated'}</span>
                              {q.status && (
                                <span className="text-[9px] font-mono uppercase px-1.5 py-0.2 rounded bg-emerald-900/80 border border-emerald-500/60 shadow-sm shrink-0">
                                  {q.status}
                                </span>
                              )}
                            </div>
                            {Array.isArray(q.completed_sub_quest_ids) && q.completed_sub_quest_ids.length > 0 && (
                              <div className={`text-emerald-200 font-semibold ${isLatest ? 'text-xs' : 'text-[10px]'}`}>
                                ✅ Sub-objective #{q.completed_sub_quest_ids.join(', #')} completed!
                              </div>
                            )}
                            {Array.isArray(q.new_clues) && q.new_clues.length > 0 && (
                              <div className="space-y-1 pt-0.5">
                                {q.new_clues.map((clue, cIdx) => (
                                  <div
                                    key={`clue-${cIdx}`}
                                    className={`rounded border flex items-start gap-1.5 ${
                                      isLatest
                                        ? 'p-2 bg-amber-950/40 border-amber-500/60 text-amber-100 text-xs shadow-sm'
                                        : 'p-1.5 bg-amber-950/25 border-amber-700/40 text-amber-200 text-[10px]'
                                    }`}
                                  >
                                    <Sparkles size={isLatest ? 13 : 11} className="text-amber-400 shrink-0 mt-0.5" />
                                    <div className="leading-relaxed">
                                      <span className="font-bold text-amber-300 uppercase tracking-wider text-[9px] block mb-0.5">
                                        Clue Discovered:
                                      </span>
                                      <span className="italic">{clue}</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Combat Log Block */}
                    {item.combatLines.length > 0 && (
                      <div
                        className={`rounded-lg bg-red-950/35 border border-red-800/50 space-y-1 font-mono text-red-200 shadow-sm ${
                          isLatest ? 'p-2.5 text-xs' : 'p-2 text-[10px]'
                        }`}
                      >
                        <div className="flex items-center gap-1.5 text-red-300 font-bold uppercase tracking-wider">
                          <Swords size={isLatest ? 12 : 10} />
                          <span>Combat Log</span>
                        </div>
                        {item.combatLines.map((line, lIdx) => (
                          <div key={`c-${lIdx}`} className="leading-relaxed text-gray-200">
                            • {line}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Clear Visual Divider between Latest Turn and Past Turns */}
                {isLatest && turnOutcomes.length > 1 && (
                  <div className="flex items-center gap-2 pt-1 pb-0.5">
                    <div className="h-px bg-fantasy-border/70 flex-1" />
                    <span className="text-[10px] font-mono uppercase tracking-wider text-gray-400 font-semibold px-2 py-0.2 rounded-full bg-black/70 border border-fantasy-border/70 shadow-sm">
                      Previous Turns ({turnOutcomes.length - 1})
                    </span>
                    <div className="h-px bg-fantasy-border/70 flex-1" />
                  </div>
                )}
              </React.Fragment>
            );
          })
        )}
      </div>
    </div>
  );
};

export default WorldOutcomeSidebar;
