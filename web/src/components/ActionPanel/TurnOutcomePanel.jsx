import React, { useState, useEffect, useRef } from 'react';
import { ScrollText, ChevronDown, ChevronUp, Heart, Zap, Coins, Gift, ShieldAlert, Sparkles } from 'lucide-react';
import { getOutcomeTierTheme } from '../StoryFeed/HistoryCard';
import { extractTurnOutcomes } from '../Sidebar/WorldOutcomeSidebar';

const TurnOutcomePanel = ({ session }) => {
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

  const latestOutcome = turnOutcomes.length > 0 ? turnOutcomes[turnOutcomes.length - 1] : null;
  const excitement = session?.physical_state?.excitement;
  const isExcitementActive = Boolean(excitement?.active);

  // If there are no past action outcomes AND excitement is not active, render nothing
  if (!latestOutcome && !isExcitementActive) {
    return null;
  }

  // Turn key to detect when a new turn arrives
  const currentTurnKey = latestOutcome
    ? `turn-${latestOutcome.turnNumber}-${session?.id || ''}`
    : `scene-${session?.scene_count || session?.history?.length || 0}`;

  // Collapsed by default on initial load and whenever a new turn arrives!
  const [isExpanded, setIsExpanded] = useState(false);
  const [hasUnread, setHasUnread] = useState(true);
  const lastTurnKeyRef = useRef(currentTurnKey);

  useEffect(() => {
    if (currentTurnKey && currentTurnKey !== lastTurnKeyRef.current) {
      lastTurnKeyRef.current = currentTurnKey;
      setIsExpanded(false); // Collapsed by default on every new turn!
      setHasUnread(true);   // Notification badge on every new turn!
    }
  }, [currentTurnKey]);

  const handleToggle = () => {
    if (!isExpanded) {
      setIsExpanded(true);
      setHasUnread(false); // Mark outcome as acknowledged/checked!
    } else {
      setIsExpanded(false);
    }
  };

  const theme = latestOutcome
    ? getOutcomeTierTheme(latestOutcome.checkTier, latestOutcome.tierLabel, latestOutcome.checkStat)
    : null;

  const statPrefix =
    latestOutcome?.checkStat && latestOutcome.checkStat !== 'NONE' && latestOutcome.checkStat !== 'FREE'
      ? `${latestOutcome.checkStat} • `
      : '';
  const tierText = latestOutcome?.tierLabel || theme?.defaultLabel || 'RESOLVED';
  const chanceText =
    latestOutcome?.checkChance !== null &&
    latestOutcome?.checkChance !== undefined &&
    latestOutcome?.checkStat !== 'NONE' &&
    latestOutcome?.checkStat !== 'FREE'
      ? ` (${Math.round(Number(latestOutcome.checkChance))}%)`
      : '';

  // Get preview excitement info if active
  const excitementActors = isExcitementActive ? Object.entries(excitement.actors || {}) : [];
  const firstActor = excitementActors[0];

  return (
    <div className="w-full mb-2">
      {/* Collapsed / Expandable Header Banner */}
      <div
        role="button"
        tabIndex={0}
        onClick={handleToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleToggle();
          }
        }}
        className={`group w-full flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg border transition-all cursor-pointer select-none text-left ${
          isExpanded
            ? 'bg-black/80 border-fantasy-accent/60 shadow-md'
            : isExcitementActive
              ? 'bg-gradient-to-r from-rose-950/40 via-pink-950/25 to-black/60 border-pink-500/40 hover:border-pink-400/70 hover:bg-rose-950/60'
              : 'bg-black/60 border-fantasy-border/80 hover:border-fantasy-accent/60 hover:bg-black/80'
        }`}
        title={isExpanded ? 'Collapse Turn Outcome' : 'Expand to see full Turn Outcome & Details'}
      >
        {/* Left Side: Icon, Turn Title, and Notification Badge */}
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs shrink-0">
            {isExcitementActive ? '💋' : <ScrollText size={14} className="text-fantasy-accent" />}
          </span>

          <span className="text-xs font-semibold text-gray-200 group-hover:text-white truncate">
            {latestOutcome ? `Turn #${latestOutcome.turnNumber} Outcome` : 'Intimate State'}
          </span>

          {/* New Turn Notification Badge */}
          {hasUnread && (
            <span className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-500 text-black text-[9px] font-mono font-extrabold uppercase tracking-wider animate-pulse shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-black animate-ping" />
              <span>NEW</span>
            </span>
          )}
        </div>

        {/* Center / Preview Pills (when collapsed) */}
        {!isExpanded && (
          <div className="hidden sm:flex items-center gap-1.5 min-w-0 overflow-hidden text-[10px]">
            {theme && latestOutcome?.checkStat && latestOutcome.checkStat !== 'NONE' && (
              <span className={`px-2 py-0.2 rounded-full border font-mono font-bold truncate ${theme.badgeClass}`}>
                {theme.icon} {tierText}
              </span>
            )}
            {latestOutcome?.xpGained > 0 && (
              <span className="px-1.5 py-0.2 rounded bg-amber-950/60 border border-amber-600/50 text-amber-300 font-mono">
                +{latestOutcome.xpGained} XP
              </span>
            )}
            {isExcitementActive && excitementActors.length > 0 && (
              <span className="px-1.5 py-0.2 rounded bg-pink-950/60 border border-pink-700/50 text-pink-300 font-mono truncate">
                💋 {excitementActors.map(([aName, aData]) => `${aName}: ${aData?.meter ?? 0}%`).join(' | ')}
              </span>
            )}
          </div>
        )}

        {/* Right Side: Toggle Chevron */}
        <div className="flex items-center gap-1 shrink-0 text-gray-400 group-hover:text-fantasy-accent transition-colors">
          <span className="text-[10px] font-mono hidden xs:inline text-gray-400">
            {isExpanded ? 'Hide' : 'Details'}
          </span>
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {/* Expanded Outcome & State Card */}
      {isExpanded && (
        <div className="mt-1.5 rounded-xl border border-fantasy-border/80 bg-black/85 backdrop-blur-md p-3 space-y-2.5 shadow-xl animate-in fade-in zoom-in-95 duration-150 max-h-[35vh] overflow-y-auto custom-scrollbar">
          {/* Latest Outcome Details */}
          {latestOutcome && (
            <div className="space-y-2 pb-1.5 border-b border-fantasy-border/50">
              {/* Outcome Check Result Header */}
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <div className="text-[11px] text-gray-300 italic truncate max-w-[280px]">
                  <span className="text-fantasy-accent font-mono not-italic mr-1">▸</span>
                  <span>{latestOutcome.label}</span>
                </div>

                {theme && (
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-[10px] font-mono font-bold uppercase tracking-wider ${theme.badgeClass}`}
                  >
                    <span>{theme.icon}</span>
                    <span>{statPrefix}{tierText}{chanceText}</span>
                  </span>
                )}
              </div>

              {/* Mechanical Deltas Row: EXP, HP, MP, Gold, Loot, Status, Relations */}
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {latestOutcome.xpGained > 0 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-950/60 border border-amber-600/50 text-amber-300 font-mono text-[10px] font-semibold">
                    ✨ +{latestOutcome.xpGained} EXP
                  </span>
                )}

                {latestOutcome.levelsGained.length > 0 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-yellow-500/25 border border-yellow-400 text-yellow-300 font-mono text-[10px] font-bold animate-pulse">
                    🎉 LEVEL UP (Lv.{latestOutcome.levelsGained[latestOutcome.levelsGained.length - 1]})
                  </span>
                )}

                {latestOutcome.hpDelta !== 0 && (
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[10px] font-semibold ${
                      latestOutcome.hpDelta > 0
                        ? 'bg-emerald-950/60 border-emerald-700/50 text-emerald-300'
                        : 'bg-red-950/70 border-red-700/60 text-red-300'
                    }`}
                  >
                    <Heart size={10} />
                    {latestOutcome.hpDelta > 0 ? `+${latestOutcome.hpDelta}` : latestOutcome.hpDelta} HP
                  </span>
                )}

                {latestOutcome.mpDelta !== 0 && (
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[10px] font-semibold ${
                      latestOutcome.mpDelta > 0
                        ? 'bg-blue-950/60 border-blue-700/50 text-blue-300'
                        : 'bg-indigo-950/70 border-indigo-700/60 text-indigo-300'
                    }`}
                  >
                    <Zap size={10} />
                    {latestOutcome.mpDelta > 0 ? `+${latestOutcome.mpDelta}` : latestOutcome.mpDelta} MP
                  </span>
                )}

                {latestOutcome.goldDelta !== 0 && (
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border font-mono text-[10px] font-semibold ${
                      latestOutcome.goldDelta > 0
                        ? 'bg-amber-950/70 border-amber-600/50 text-amber-300'
                        : 'bg-orange-950/70 border-orange-700/50 text-orange-300'
                    }`}
                  >
                    <Coins size={10} />
                    {latestOutcome.goldDelta > 0 ? `+${latestOutcome.goldDelta}` : latestOutcome.goldDelta} Gold
                  </span>
                )}

                {latestOutcome.itemsGained.map((it, idx) => (
                  <span
                    key={`item-gain-${idx}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-700/50 text-cyan-200 text-[10px] font-medium"
                  >
                    <Gift size={10} /> +{it}
                  </span>
                ))}

                {latestOutcome.itemsLost.map((it, idx) => (
                  <span
                    key={`item-lost-${idx}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-gray-400 text-[10px] line-through"
                  >
                    -{it}
                  </span>
                ))}

                {latestOutcome.statusEffects.map((st, idx) => (
                  <span
                    key={`status-${idx}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-950/60 border border-rose-700/50 text-rose-200 text-[10px] font-medium"
                  >
                    <ShieldAlert size={10} /> {st}
                  </span>
                ))}

                {latestOutcome.relUpdates.map((ru, idx) => {
                  const label =
                    typeof ru === 'string'
                      ? ru
                      : `${ru.npc_name || ru.npc || ru.name || 'NPC'}: ${(ru.delta_score ?? ru.delta ?? 0) > 0 ? `+${ru.delta_score ?? ru.delta}` : (ru.delta_score ?? ru.delta ?? '')}`;
                  return (
                    <span
                      key={`rel-${idx}`}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-pink-950/60 border border-pink-700/50 text-pink-200 text-[10px]"
                    >
                      💕 {label}
                    </span>
                  );
                })}

                {latestOutcome.facUpdates.map((fu, idx) => {
                  const label =
                    typeof fu === 'string'
                      ? fu
                      : `${fu.faction_name || fu.faction || fu.name || 'Faction'}: ${(fu.delta_score ?? fu.delta ?? 0) > 0 ? `+${fu.delta_score ?? fu.delta}` : (fu.delta_score ?? fu.delta ?? 0)} Rep`;
                  return (
                    <span
                      key={`fac-${idx}`}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-950/60 border border-purple-700/50 text-purple-200 text-[10px]"
                    >
                      🚩 {label}
                    </span>
                  );
                })}
              </div>

              {/* Quest Updates / Newly Discovered Clues */}
              {latestOutcome.questUpdates.length > 0 && (
                <div className="space-y-1 pt-1">
                  {latestOutcome.questUpdates.map((q, qIdx) => (
                    <div
                      key={`quest-up-${qIdx}`}
                      className="p-1.5 rounded bg-amber-950/25 border border-amber-700/40 text-[10px] text-amber-200 space-y-0.5"
                    >
                      <div className="font-semibold flex items-center gap-1 text-amber-300">
                        <span>📜</span>
                        <span>{q.title || 'Quest Updated'}</span>
                        {q.status && <span className="text-[9px] uppercase font-mono px-1 rounded bg-amber-900/60">({q.status})</span>}
                      </div>
                      {Array.isArray(q.new_clues) && q.new_clues.map((clue, cIdx) => (
                        <div key={`clue-${cIdx}`} className="text-gray-300 italic pl-3">
                          • {clue}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {/* Refractory Recovery Notice */}
              {latestOutcome.refractoryNotice && (
                <div className="p-1.5 rounded bg-emerald-950/40 border border-emerald-600/50 text-emerald-300 text-[10px] flex items-center gap-1.5">
                  <span>⚡</span>
                  <span>{latestOutcome.refractoryNotice}</span>
                </div>
              )}
            </div>
          )}

          {/* Compact Intimate Excitement & Arousal Meter */}
          {isExcitementActive && (
            <div className="rounded-lg border border-pink-500/30 bg-gradient-to-br from-rose-950/40 via-pink-950/30 to-black/60 p-2.5 space-y-1.5 shadow-sm">
              <div className="flex items-center justify-between text-xs font-semibold text-pink-300 pb-1 border-b border-pink-900/40">
                <span className="flex items-center gap-1.5">
                  <span className="text-xs">💋</span>
                  <span className="font-rpg tracking-wider uppercase text-[10px] md:text-xs text-pink-200">
                    Intimate Excitement & Arousal
                  </span>
                </span>
                {excitement.last_act && (
                  <span className="text-[9px] uppercase font-mono tracking-wider px-2 py-0.5 rounded-full bg-pink-900/60 border border-pink-500/40 text-pink-200">
                    {excitement.last_act === 'foreplay_nongenital' ? 'Foreplay' : excitement.last_act.replace(/_/g, ' ')}
                  </span>
                )}
              </div>

              {/* Space-efficient Compact Multi-Actor Meters */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-0.5">
                {Object.entries(excitement.actors || {}).map(([name, data]) => {
                  const meter = Number(data.meter ?? 0);
                  const delta = Number(data.delta ?? 0);
                  const status = data.status || '';
                  const climaxes = Number(data.climaxes_count ?? 0);
                  const recoiled = Boolean(data.recoiled);
                  return (
                    <div
                      key={name}
                      className="bg-black/50 rounded-lg p-2 border border-pink-950/60 space-y-1"
                    >
                      <div className="flex justify-between items-center text-[11px]">
                        <span className="font-medium text-pink-100 flex items-center gap-1 truncate max-w-[140px]">
                          <span>{name}</span>
                          {climaxes > 0 && <span className="text-amber-300 text-[9px]">💥 x{climaxes}</span>}
                          {recoiled && <span className="text-orange-400 text-[9px]" title="Hypersensitive recoil!">⚠️</span>}
                        </span>
                        <span className="font-mono text-pink-300 font-bold text-[11px] shrink-0 flex items-center gap-1">
                          <span>{meter}%</span>
                          {delta > 0 && <span className="text-[9px] text-pink-400 font-normal">(+{delta}%)</span>}
                        </span>
                      </div>
                      <div className="w-full bg-neutral-900/90 rounded-full h-1.5 overflow-hidden border border-pink-900/50">
                        <div
                          className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r from-pink-500 via-rose-500 to-red-500 ${
                            meter >= 80 ? 'animate-pulse' : ''
                          }`}
                          style={{ width: `${Math.min(100, meter)}%` }}
                        />
                      </div>
                      {status && <div className="text-[9px] text-pink-300/80 italic truncate">{status}</div>}
                    </div>
                  );
                })}
              </div>

              {/* Sensitive Spot Notification Chip */}
              {excitement.sensitive_spot_hit && (
                <div className="text-[10px] text-amber-300 font-medium flex items-center gap-1 pt-0.5">
                  <span>✨</span>
                  <span>
                    Sensitive Spot: <span className="font-bold underline decoration-amber-400/60">{excitement.sensitive_spot_hit}</span> (+6% bonus!)
                  </span>
                </div>
              )}

              {/* Simultaneous / Mutual Group Climax Notification Chip */}
              {excitement.mutual_group_climax ? (
                <div className="text-[10px] text-pink-200 bg-pink-950/50 border border-pink-500/50 rounded p-1.5 flex items-center gap-1">
                  <span>💥</span>
                  <span>Mutual group climax reached together!</span>
                </div>
              ) : excitement.simultaneous_partner_climax ? (
                <div className="text-[10px] text-pink-200 bg-pink-950/50 border border-pink-500/50 rounded p-1.5 flex items-center gap-1">
                  <span>💥</span>
                  <span>Partners reached climax simultaneously!</span>
                </div>
              ) : null}

              {/* Premature Finish Warning Chip */}
              {excitement.premature_finish && (
                <div className="text-[10px] text-orange-200 bg-orange-950/40 border border-orange-700/50 rounded p-1.5 flex items-center gap-1">
                  <span>⚠️</span>
                  <span>
                    Physical exhaustion: Climax reached before{' '}
                    {Array.isArray(excitement.unsatisfied_partners) && excitement.unsatisfied_partners.length > 0
                      ? `${excitement.unsatisfied_partners.join(' & ')} ${excitement.unsatisfied_partners.length > 1 ? 'were' : 'was'}`
                      : excitement.unsatisfied_partner
                        ? `${excitement.unsatisfied_partner} was`
                        : 'partner was'}{' '}
                    satisfied!
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TurnOutcomePanel;
