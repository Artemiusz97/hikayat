import React from 'react';
import { MapPin, Map, Calendar, Users, Sparkles, Swords, Compass, ScrollText, Heart, ShieldAlert, Coins, Gift } from 'lucide-react';
import { getOutcomeTierTheme } from '../StoryFeed/HistoryCard';

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

const extractTurnOutcomes = (entry, turnNumber, seenClues = new Set(), seenCompletedSubs = new Set()) => {
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
      const name = typeof st === 'string' ? st : st?.name;
      if (name) statusEffects.add(name);
    });
  });

  // Relationships & Factions
  const relUpdates = (Array.isArray(entry.relationship_updates) ? entry.relationship_updates : (outcome.relationship_updates || []))
    .filter(r => r && (typeof r === 'string' || Number(r.delta_score ?? r.delta ?? 0) !== 0 || r.milestone_event));
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
  };
};

const WorldOutcomeSidebar = ({
  session,
  onOpenWorldMap,
}) => {
  const locationTiers = parseLocationTiers(session?.current_location, session?.scene_title);
  const currentPlace = locationTiers[locationTiers.length - 1];
  const parentRegions = locationTiers.slice(0, -1);

  const npcs = Array.isArray(session?.current_npcs) ? session.current_npcs : [];
  const dialoguePartners = new Set(
    (Array.isArray(session?.dialogue_partners)
      ? session.dialogue_partners
      : (session?.dialogue_partner ? [session.dialogue_partner] : [])
    ).map(n => String(n || '').toLowerCase().trim()).filter(Boolean)
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

  return (
    <div className="flex flex-col h-full bg-fantasy-panel text-gray-200 select-none">
      {/* SECTION 1: World & Scene Context (Location, Map, Day/Time, Present NPCs) */}
      <div className="p-4 border-b border-fantasy-border bg-black/40 space-y-3.5">
        {/* Header Row: Region & Day/Time */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-rpg font-bold uppercase tracking-wider text-fantasy-accent">
            <Compass size={16} />
            <span>Scene & World</span>
          </div>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-950/60 border border-amber-600/50 text-xs font-mono text-amber-300 shadow-sm">
            <Calendar size={12} className="text-amber-400" />
            <span>{session?.formatted_time || 'Day 1 • 08:00'}</span>
          </span>
        </div>

        {/* Location Card + World Map Button */}
        <div className="p-3.5 rounded-xl bg-black/60 border border-fantasy-border/80 space-y-3 shadow-inner">
          <div className="flex items-start gap-2.5">
            <MapPin size={17} className="text-fantasy-accent shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              {parentRegions.length > 0 && (
                <div className="text-xs font-mono text-gray-400 truncate mb-0.5">
                  {parentRegions.join(' ➔ ')}
                </div>
              )}
              <div className="text-base font-bold text-gray-100 leading-snug break-words">
                {currentPlace}
              </div>
            </div>
          </div>

          <button
            onClick={onOpenWorldMap}
            className="w-full py-2 px-3.5 rounded-lg bg-fantasy-accent/15 hover:bg-fantasy-accent/25 border border-fantasy-accent/40 hover:border-fantasy-accent text-fantasy-accent text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-sm active:scale-[0.99]"
          >
            <Map size={14} />
            <span>Open World Map & Fast Travel</span>
          </button>
        </div>

        {/* Present NPCs in Scene */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono uppercase tracking-wider text-gray-300">
            <span className="flex items-center gap-1.5">
              <Users size={13} className="text-fantasy-accent/80" />
              <span>Present in Scene</span>
            </span>
            <span className="px-2 py-0.5 rounded bg-black/60 border border-fantasy-border text-xs text-gray-300 font-bold">
              {npcs.length}
            </span>
          </div>

          {npcs.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto custom-scrollbar pr-0.5">
              {npcs.map((npc, idx) => {
                const name = typeof npc === 'string' ? npc : (npc?.name || 'Unknown');
                const isPartner = dialoguePartners.has(name.toLowerCase().trim());
                return (
                  <div
                    key={`${name}-${idx}`}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                      isPartner
                        ? 'bg-purple-950/60 border-purple-500/60 text-purple-200'
                        : 'bg-black/60 border-neutral-800 text-gray-200 hover:border-neutral-700'
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full ${isPartner ? 'bg-purple-400 animate-pulse' : 'bg-emerald-400/80'}`} />
                    <span className="truncate max-w-[220px]">{name}</span>
                    {isPartner && (
                      <span className="text-[10px] font-mono uppercase px-1.5 py-0.2 rounded bg-purple-900/80 text-purple-300 font-semibold">
                        Talking
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-xs text-gray-500 italic px-1">
              No other characters in the immediate area.
            </div>
          )}
        </div>
      </div>

      {/* SECTION 2: Dedicated Outcomes & Changes Feed (EXP, Combat Logs, Quests, Vitals, Loot) */}
      <div className="px-4 py-3 border-b border-fantasy-border bg-black/60 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-rpg font-bold uppercase tracking-wider text-fantasy-accent">
          <ScrollText size={15} />
          <span>Outcomes & Changes</span>
        </div>
        <span className="text-xs font-mono text-gray-300 bg-black/60 px-2.5 py-0.5 rounded border border-fantasy-border">
          {turnOutcomes.length} {turnOutcomes.length === 1 ? 'Turn' : 'Turns'}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-3.5 space-y-3">
        {turnOutcomes.length === 0 ? (
          <div className="text-center py-12 px-4 text-xs text-gray-500 space-y-2">
            <Sparkles size={20} className="mx-auto text-fantasy-accent/50" />
            <p className="font-semibold text-gray-300 text-sm">No Turn Outcomes Yet</p>
            <p className="text-xs text-gray-400 leading-relaxed max-w-xs mx-auto">
              Skill check rolls, EXP gains, combat logs, loot, and newly discovered clues will appear here as your story unfolds.
            </p>
          </div>
        ) : (
          turnOutcomes.map((item, idx) => {
            const isLatest = idx === 0;
            const theme = getOutcomeTierTheme(item.checkTier, item.tierLabel, item.checkStat);
            const statPrefix = item.checkStat && item.checkStat !== 'NONE' && item.checkStat !== 'FREE' ? `${item.checkStat} • ` : '';
            const tierText = (item.tierLabel || theme.defaultLabel).toUpperCase();
            const chanceText =
              item.checkChance !== null && item.checkChance !== undefined && item.checkStat !== 'NONE' && item.checkStat !== 'FREE'
                ? ` (${Math.round(Number(item.checkChance))}%)`
                : '';

            return (
              <React.Fragment key={`turn-outcome-${item.turnNumber}`}>
                <div
                  className={`rounded-xl transition-all ${
                    isLatest
                      ? 'p-4 bg-gradient-to-b from-amber-950/25 via-black/85 to-fantasy-panel/95 border-2 border-fantasy-accent/80 shadow-[0_0_20px_rgba(217,119,6,0.18)] ring-1 ring-fantasy-accent/40 space-y-3 relative overflow-hidden'
                      : 'p-3 bg-black/45 border border-fantasy-border/60 hover:border-fantasy-border hover:bg-black/60 opacity-80 hover:opacity-100 space-y-2'
                  }`}
                >
                  {/* Turn Header & Check Result Badge */}
                  <div className="flex items-center justify-between gap-2">
                    {isLatest ? (
                      <div className="flex items-center gap-2">
                        <span className="relative flex h-2.5 w-2.5">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-fantasy-accent opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-fantasy-accent"></span>
                        </span>
                        <span className="px-2.5 py-0.5 rounded-full bg-fantasy-accent/20 border border-fantasy-accent/60 text-fantasy-accent text-xs font-mono font-bold uppercase tracking-wider shadow-sm">
                          Latest Outcome • Turn #{item.turnNumber}
                        </span>
                      </div>
                    ) : (
                      <span className="text-[11px] font-mono uppercase tracking-wider text-gray-400 font-medium">
                        Turn #{item.turnNumber}
                      </span>
                    )}

                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full border font-mono font-bold uppercase shadow-sm ${
                        isLatest ? 'px-3 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                      } ${theme.badgeClass}`}
                    >
                      <span>{theme.icon}</span>
                      <span>{statPrefix}{tierText}{chanceText}</span>
                    </span>
                  </div>

                  {/* Chosen Action Label */}
                  <div
                    className={`font-semibold leading-snug border-l-4 ${
                      isLatest
                        ? 'text-sm md:text-[15px] text-white pl-3 py-1 bg-white/[0.04] border-fantasy-accent rounded-r'
                        : 'text-xs text-gray-300 pl-2.5 py-0.5 border-fantasy-accent/40'
                    }`}
                  >
                    {item.label}
                  </div>

                  {/* Mechanical Deltas Pills (EXP, Level Up, HP, MP, Gold, Loot, Status) */}
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {item.xpGained > 0 && (
                      <span
                        className={`inline-flex items-center gap-1 rounded bg-amber-950/60 border border-amber-600/50 text-amber-300 font-mono font-semibold ${
                          isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        }`}
                      >
                        ✨ +{item.xpGained} EXP
                      </span>
                    )}

                    {item.levelsGained.length > 0 && (
                      <span
                        className={`inline-flex items-center gap-1 rounded bg-yellow-500/25 border border-yellow-400 text-yellow-300 font-mono font-bold animate-pulse ${
                          isLatest ? 'px-3 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        }`}
                      >
                        🎉 LEVEL UP (Lv.{item.levelsGained[item.levelsGained.length - 1]})
                      </span>
                    )}

                    {item.hpDelta !== 0 && (
                      <span
                        className={`inline-flex items-center gap-1 rounded border font-mono font-semibold ${
                          isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        } ${
                          item.hpDelta > 0
                            ? 'bg-emerald-950/60 border-emerald-700/50 text-emerald-300'
                            : 'bg-red-950/70 border-red-700/60 text-red-300'
                        }`}
                      >
                        <Heart size={isLatest ? 12 : 10} />
                        {item.hpDelta > 0 ? `+${item.hpDelta}` : item.hpDelta} HP
                      </span>
                    )}

                    {item.mpDelta !== 0 && (
                      <span
                        className={`inline-flex items-center gap-1 rounded border font-mono font-semibold ${
                          isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        } ${
                          item.mpDelta > 0
                            ? 'bg-blue-950/60 border-blue-700/50 text-blue-300'
                            : 'bg-indigo-950/70 border-indigo-700/60 text-indigo-300'
                        }`}
                      >
                        💧 {item.mpDelta > 0 ? `+${item.mpDelta}` : item.mpDelta} MP
                      </span>
                    )}

                    {item.goldDelta !== 0 && (
                      <span
                        className={`inline-flex items-center gap-1 rounded border font-mono font-semibold ${
                          isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        } ${
                          item.goldDelta > 0
                            ? 'bg-amber-950/70 border-amber-600/50 text-amber-300'
                            : 'bg-orange-950/70 border-orange-700/50 text-orange-300'
                        }`}
                      >
                        <Coins size={isLatest ? 12 : 10} />
                        {item.goldDelta > 0 ? `+${item.goldDelta}` : item.goldDelta} Gold
                      </span>
                    )}

                    {item.itemsGained.map((it, iIdx) => (
                      <span
                        key={`gain-${iIdx}`}
                        className={`inline-flex items-center gap-1 rounded bg-cyan-950/60 border border-cyan-700/50 text-cyan-200 font-medium ${
                          isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        }`}
                      >
                        <Gift size={isLatest ? 12 : 10} /> +{it}
                      </span>
                    ))}

                    {item.itemsLost.map((it, iIdx) => (
                      <span
                        key={`lost-${iIdx}`}
                        className={`inline-flex items-center gap-1 rounded bg-neutral-900 border border-neutral-700 text-gray-400 line-through ${
                          isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        }`}
                      >
                        -{it}
                      </span>
                    ))}

                    {item.statusEffects.map((st, sIdx) => (
                      <span
                        key={`st-${sIdx}`}
                        className={`inline-flex items-center gap-1 rounded bg-rose-950/60 border border-rose-700/50 text-rose-200 font-medium ${
                          isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                        }`}
                      >
                        <ShieldAlert size={isLatest ? 12 : 10} /> {st}
                      </span>
                    ))}

                    {item.relUpdates.map((ru, rIdx) => {
                      const label = typeof ru === 'string'
                        ? ru
                        : `${ru.npc_name || ru.npc || ru.name || 'NPC'}: ${(ru.delta_score ?? ru.delta ?? 0) > 0 ? `+${ru.delta_score ?? ru.delta}` : (ru.delta_score ?? ru.delta ?? '')}`;
                      return (
                        <span
                          key={`rel-${rIdx}`}
                          className={`inline-flex items-center gap-1 rounded bg-pink-950/60 border border-pink-700/50 text-pink-200 ${
                            isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
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
                          className={`inline-flex items-center gap-1 rounded bg-purple-950/60 border border-purple-700/50 text-purple-200 ${
                            isLatest ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[10px]'
                          }`}
                        >
                          🚩 {label}
                        </span>
                      );
                    })}
                  </div>

                  {/* Quest & Objective Progress Block */}
                  {item.questUpdates.length > 0 && (
                    <div
                      className={`rounded-lg space-y-2 border ${
                        isLatest
                          ? 'p-3 bg-emerald-950/35 border-emerald-600/50 text-xs'
                          : 'p-2 bg-emerald-950/20 border-emerald-800/30 text-[11px]'
                      }`}
                    >
                      {item.questUpdates.map((q, qIdx) => (
                        <div key={`q-${qIdx}`} className="space-y-1">
                          <div className="flex items-center justify-between gap-1.5 font-bold text-emerald-300">
                            <span className="truncate">📜 {q.title || q.quest_id || 'Quest Updated'}</span>
                            {q.status && (
                              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-emerald-900/70 border border-emerald-500/50 shadow-sm shrink-0">
                                {q.status}
                              </span>
                            )}
                          </div>
                          {Array.isArray(q.completed_sub_quest_ids) && q.completed_sub_quest_ids.length > 0 && (
                            <div className={`text-emerald-200 font-medium ${isLatest ? 'text-xs' : 'text-[10px]'}`}>
                              ✅ Sub-objective #{q.completed_sub_quest_ids.join(', #')} completed!
                            </div>
                          )}
                          {Array.isArray(q.new_clues) && q.new_clues.length > 0 && (
                            <div className="space-y-1 pt-0.5">
                              {q.new_clues.map((clue, cIdx) => (
                                <div
                                  key={`clue-${cIdx}`}
                                  className={`rounded border flex items-start gap-2 ${
                                    isLatest
                                      ? 'p-2.5 bg-amber-950/35 border-amber-500/50 text-amber-100 text-xs shadow-sm'
                                      : 'p-1.5 bg-amber-950/20 border-amber-700/30 text-amber-200 text-[10px]'
                                  }`}
                                >
                                  <Sparkles size={isLatest ? 14 : 12} className="text-amber-400 shrink-0 mt-0.5" />
                                  <div className="leading-relaxed">
                                    <span className="font-bold text-amber-300 uppercase tracking-wider text-[10px] block mb-0.5">
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
                      className={`rounded-lg bg-red-950/30 border border-red-800/40 space-y-1.5 font-mono text-red-200 ${
                        isLatest ? 'p-3 text-xs' : 'p-2 text-[10px]'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 text-red-300 font-bold uppercase tracking-wider">
                        <Swords size={isLatest ? 13 : 11} />
                        <span>Combat Log</span>
                      </div>
                      {item.combatLines.map((line, lIdx) => (
                        <div key={`c-${lIdx}`} className="leading-relaxed text-gray-300">
                          • {line}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Clear Visual Divider between Latest Turn and Past Turns */}
                {isLatest && turnOutcomes.length > 1 && (
                  <div className="flex items-center gap-2.5 pt-2 pb-1">
                    <div className="h-px bg-fantasy-border/70 flex-1" />
                    <span className="text-[10px] font-mono uppercase tracking-wider text-gray-400 font-semibold px-2.5 py-0.5 rounded-full bg-black/70 border border-fantasy-border/70 shadow-sm">
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
