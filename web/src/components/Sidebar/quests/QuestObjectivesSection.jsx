import {
  CheckCircle2,
  Circle,
  Flame,
  Lock,
  MapPin,
  Search,
  SkipForward,
  Snowflake,
  Star,
  User,
} from 'lucide-react';
import {
  cleanProseLocations,
  formatCleanLocation,
  formatFullLocationPath,
} from '../../../utils/locationFormat';
import { formatScenarioCurrency } from '../../../utils/currency';

const getOptionalRoleStyle = (role) => {
  const norm = String(role || 'aid').toLowerCase();
  if (norm === 'bypass') {
    return {
      accentBar: 'border-l-amber-400',
      badge: 'bg-amber-950/70 text-amber-300 border-amber-700/60',
    };
  }
  if (norm === 'alternative') {
    return {
      accentBar: 'border-l-purple-400',
      badge: 'bg-purple-950/70 text-purple-200 border-purple-600/60',
    };
  }
  if (norm === 'threatened') {
    return {
      accentBar: 'border-l-rose-400',
      badge: 'bg-rose-950/70 text-rose-300 border-rose-600/60',
    };
  }
  return {
    accentBar: 'border-l-cyan-400',
    badge: 'bg-cyan-950/70 text-cyan-200 border-cyan-700/60',
  };
};

const stripLeadingEmoji = (str, emoji) => String(str || '').replace(new RegExp(`^${emoji}\\s*`), '');

export const StructuredObjectives = ({
  questObj,
  onOpenWorldMap,
  scenario = 'fantasy',
  t,
  showStageBadge = false,
}) => {
  const mainObj = questObj?.main_objective || questObj?.fow_dossier?.main_objective;
  const hasStructured = Boolean(
    (questObj?.has_structured_objectives || questObj?.fow_dossier?.has_structured_objectives) && mainObj
  );
  if (!hasStructured) return null;

  const mainStages = Array.isArray(mainObj.stages) ? mainObj.stages : [];
  const totalMainStages = mainObj.total_stages || mainStages.length || 2;
  const curMainStage = mainObj.current_stage || 1;
  const isMainDone = Boolean(mainObj.completed);
  const activeStage =
    mainStages.find((s) => !s.completed && s.status !== 'completed' && s.status !== 'bypassed') ||
    mainStages[mainStages.length - 1] ||
    null;
  const isPeak = Boolean(questObj?.is_peak_chapter || questObj?.fow_dossier?.is_peak_chapter);
  const opts = (questObj?.optional_objectives || questObj?.fow_dossier?.optional_objectives || []).filter(
    (o) => o && o.is_discovered !== false
  );
  const doneOpts = opts.filter((o) => o.completed || o.status === 'completed').length;

  const mainText = cleanProseLocations(
    mainObj.title &&
      (questObj?.is_story_quest || questObj?.quest_type === 'Story Quest' || mainObj.title !== questObj?.objective)
      ? mainObj.title
      : mainObj.text &&
          (questObj?.is_story_quest || questObj?.quest_type === 'Story Quest' || mainObj.text !== questObj?.objective)
        ? mainObj.text
        : t('quests.primary_operation', 'Primary Operation')
  );

  const currentStepEyebrow = stripLeadingEmoji(t('quests.current_step', 'Current Step'), '🎯').replace(/[:：]\s*$/, '');
  const keyContactLabel = stripLeadingEmoji(t('quests.key_contact', 'Key Contact:'), '👤');

  const hasCurrentStep = Boolean(
    !isMainDone &&
      activeStage &&
      (activeStage.stage_label ||
        (activeStage.target_location && activeStage.target_location !== 'Hidden Lair') ||
        activeStage.target_npc ||
        (Array.isArray(activeStage.clue_sources) && activeStage.clue_sources.length > 0))
  );

  return (
    <div className="border-t border-white/[0.07]">
      {/* Main Objective */}
      <div className="px-3 py-2.5 space-y-1.5">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-fantasy-accent">
              {isMainDone ? (
                <CheckCircle2 size={12} className="text-emerald-400 shrink-0" />
              ) : (
                <Star size={12} className="text-fantasy-accent shrink-0" />
              )}
              <span>{t('quests.main_objective', 'Main Objective')}</span>
            </span>
            {isPeak && (
              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-rose-950/70 text-rose-300 border border-rose-600/50">
                ⚡ {t('quests.peak_chapter', 'Peak Set-Piece')}
              </span>
            )}
            {mainObj.aid_dc_reduction > 0 && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-700/50">
                🛡️ {t('quests.aid_secured', 'Aid Active')}
              </span>
            )}
            {mainObj.bypass_unlocked && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-700/50">
                ⏭️ {t('quests.bypass_active', 'Shortcut Active')}
              </span>
            )}
          </div>
          {showStageBadge && (
            <span
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                isMainDone
                  ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                  : 'bg-amber-950/60 text-amber-300 border-amber-700/50 font-bold'
              }`}
            >
              {isMainDone
                ? `✓ ${totalMainStages}/${totalMainStages}`
                : `${t('quests.stage_label_short', 'Stage')} ${curMainStage}/${totalMainStages}`}
            </span>
          )}
        </div>

        <p
          className={`text-[12.5px] leading-[1.5] hk-quest-prose ${
            isMainDone ? 'text-gray-400 line-through' : 'text-gray-100 font-medium'
          }`}
        >
          {mainText}
        </p>
      </div>

      {/* Current Step Focus Strip */}
      {hasCurrentStep && (
        <div className="border-t border-white/[0.07] border-l-2 border-l-fantasy-accent bg-fantasy-accent/[0.06] px-3 py-2.5 space-y-2">
          <div className="space-y-1">
            <div className="text-[10px] font-bold uppercase tracking-wider text-fantasy-accent">
              {currentStepEyebrow}
            </div>
            {activeStage.stage_label && (
              <p className="text-[12.5px] font-semibold leading-[1.45] text-gray-50 hk-quest-prose">
                {cleanProseLocations(activeStage.stage_label)}
              </p>
            )}
          </div>

          {((activeStage.target_location && activeStage.target_location !== 'Hidden Lair') ||
            activeStage.target_npc) && (
            <div className="space-y-1.5">
              {activeStage.target_location && activeStage.target_location !== 'Hidden Lair' && (
                <div className="flex items-start justify-between gap-2">
                  <div
                    className="flex items-start gap-1.5 text-[12px] text-amber-200 font-medium leading-snug min-w-0 flex-1"
                    title={formatFullLocationPath(activeStage.target_location)}
                  >
                    <MapPin size={13} className="text-amber-400 shrink-0 mt-0.5" />
                    <span className="break-words">{formatCleanLocation(activeStage.target_location)}</span>
                  </div>
                  {onOpenWorldMap && (
                    <button
                      type="button"
                      onClick={() => onOpenWorldMap(activeStage.target_location)}
                      className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10.5px] font-bold shrink-0 transition-colors"
                    >
                      {t('quests.locate_btn', 'Map')}
                    </button>
                  )}
                </div>
              )}

              {activeStage.target_npc && (
                <div className="flex items-center gap-1.5 text-[11.5px] text-cyan-200">
                  <User size={12} className="text-cyan-400 shrink-0" />
                  <span>
                    <span className="text-cyan-300/85">{keyContactLabel}</span>{' '}
                    <strong className="text-cyan-100">{activeStage.target_npc}</strong>
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Clue Avenues */}
          {Array.isArray(activeStage.clue_sources) && activeStage.clue_sources.length > 0 && (
            <div className="pt-2 border-t border-fantasy-accent/15 space-y-1.5">
              <div className="text-[10px] uppercase tracking-wider font-bold text-gray-400">
                {t('quests.clue_sources', 'Clue Avenues')}
              </div>
              <div className="divide-y divide-white/[0.06]">
                {activeStage.clue_sources.map((src, sIdx) => {
                  const srcStat = String(src.status || 'open').toLowerCase();
                  const isBurnedOrCold = srcStat === 'burned' || srcStat === 'cold';
                  const isClaimed = srcStat === 'claimed';
                  const isBonus = Boolean(src.bonus) && srcStat === 'closed';
                  const badgeLabel = isClaimed
                    ? t('quests.source_claimed', 'Claimed')
                    : srcStat === 'burned'
                      ? t('quests.source_burned', 'Burned')
                      : srcStat === 'cold'
                        ? t('quests.source_cold', 'Cold')
                        : isBonus
                          ? t('quests.source_bonus', 'Bonus Lead')
                          : t('quests.source_open', 'Open');

                  const StatusIcon = isClaimed
                    ? CheckCircle2
                    : srcStat === 'burned'
                      ? Flame
                      : srcStat === 'cold'
                        ? Snowflake
                        : Search;
                  const iconColor = isClaimed
                    ? 'text-emerald-400'
                    : srcStat === 'burned'
                      ? 'text-orange-400'
                      : srcStat === 'cold'
                        ? 'text-sky-400'
                        : 'text-amber-400';

                  return (
                    <div key={src.source_id || sIdx} className="py-2 first:pt-0.5 last:pb-0 space-y-1">
                      <div
                        className={`flex items-start gap-1.5 text-[12px] leading-[1.45] hk-quest-prose ${
                          isBurnedOrCold
                            ? 'text-gray-500 line-through'
                            : isClaimed
                              ? 'text-emerald-300/90'
                              : 'text-gray-100'
                        }`}
                      >
                        <StatusIcon size={12} className={`${iconColor} shrink-0 mt-1`} />
                        <span className="min-w-0 flex-1">
                          {cleanProseLocations(src.approach_hint || src.label || '')}
                        </span>
                      </div>

                      {(src.location || src.off_hours_fallback || badgeLabel) && (
                        <div className="flex items-start justify-between gap-2 pl-[18px] text-[11px]">
                          <div className="min-w-0 flex-1">
                            {src.location && (
                              <span
                                className="text-amber-300/85 leading-snug break-words"
                                title={formatFullLocationPath(src.location)}
                              >
                                {src.location_display || formatCleanLocation(src.location)}
                                {src.npc ? ` · ${src.npc}` : ''}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            {src.off_hours_fallback && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded border font-mono bg-orange-950/60 text-orange-200 border-orange-600/40">
                                {t('quests.off_hours_trace', 'Off-Hours Trace (+2 DC)')}
                              </span>
                            )}
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${
                                isBurnedOrCold
                                  ? 'bg-neutral-900/70 text-gray-400 border-gray-700/50'
                                  : isClaimed
                                    ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                                    : 'bg-amber-950/50 text-amber-200 border-amber-600/45'
                              }`}
                            >
                              {badgeLabel}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Stages Roadmap (Active stage rendered as compact marker so Current Step is not duplicated) */}
      {mainStages.length > 1 && !isMainDone && (
        <div className="px-3 py-2.5 border-t border-white/[0.07] space-y-2">
          {mainStages.map((st, sIdx) => {
            const stStatus = String(st.status || 'locked').toLowerCase();
            const stDone = Boolean(st.completed || stStatus === 'completed');
            const stBypassed = Boolean(st.bypassed || stStatus === 'bypassed');
            const stActive = stStatus === 'active' && !stDone && !stBypassed;
            const stageNum = st.stage_index || sIdx + 1;
            const bonusSources =
              stDone && Array.isArray(st.clue_sources)
                ? st.clue_sources.filter(
                    (src) => src && src.bonus && String(src.status || '').toLowerCase() === 'closed'
                  )
                : [];

            if (stActive) {
              return (
                <div key={sIdx} className="flex items-center gap-2 text-[11.5px] leading-snug">
                  <span className="w-2 h-2 rounded-full bg-fantasy-accent shrink-0 shadow-[0_0_6px_oklch(var(--accent)/0.8)]" />
                  <span className="font-semibold text-amber-200">
                    {t('quests.stage_label_short', 'Stage')} {stageNum}
                  </span>
                  <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/35">
                    {t('quests.in_progress', 'In Progress')}
                  </span>
                </div>
              );
            }

            return (
              <div
                key={sIdx}
                className={`flex items-start gap-2 text-[11.5px] leading-snug ${
                  stDone
                    ? 'text-emerald-400/80'
                    : stBypassed
                      ? 'text-amber-300/75 italic'
                      : 'text-gray-300/80'
                }`}
              >
                {stDone ? (
                  <CheckCircle2 size={12} className="text-emerald-400 shrink-0 mt-0.5" />
                ) : stBypassed ? (
                  <SkipForward size={12} className="text-amber-300 shrink-0 mt-0.5" />
                ) : (
                  <Lock size={11} className="text-gray-400 shrink-0 mt-0.5" />
                )}
                <div className="min-w-0 flex-1 space-y-0.5">
                  <span className={stDone || stBypassed ? 'line-through hk-quest-prose' : 'hk-quest-prose'}>
                    {t('quests.stage_label_short', 'Stage')} {stageNum}:{' '}
                    {cleanProseLocations(st.stage_label || st.text)}
                  </span>
                  {st.target_location && st.target_location !== 'Hidden Lair' && (
                    <span
                      className="block text-[11px] text-gray-400 break-words"
                      title={formatFullLocationPath(st.target_location)}
                    >
                      {formatCleanLocation(st.target_location)}
                      {st.target_npc ? ` · ${st.target_npc}` : ''}
                    </span>
                  )}
                  {bonusSources.map((bSrc, bIdx) => (
                    <span
                      key={bSrc.source_id || bIdx}
                      className="block text-[11px] text-cyan-300 not-italic no-underline font-normal"
                      style={{ textDecoration: 'none' }}
                      title={formatFullLocationPath(bSrc.location)}
                    >
                      ⭐ {t('quests.source_bonus', 'Bonus Lead')}:{' '}
                      {cleanProseLocations(bSrc.approach_hint || bSrc.label || '')} (
                      {bSrc.location_display || formatCleanLocation(bSrc.location)})
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Discovered Optional Objectives */}
      {opts.length > 0 && (
        <div className="px-3 py-2.5 border-t border-white/[0.07] space-y-2">
          <div className="flex items-center justify-between text-[10px] font-bold text-gray-400 uppercase tracking-wider">
            <span>{t('quests.optional_objectives', 'Optional Tactical Routes')}</span>
            <span className="font-mono text-cyan-300">
              {doneOpts}/{opts.length} {t('quests.optional_short', 'Optional')}
            </span>
          </div>

          <div className="space-y-2">
            {opts.map((opt, oIdx) => {
              const st = String(opt.status || 'active').toLowerCase();
              const isDone = Boolean(opt.completed || st === 'completed');
              const isFailed = Boolean(opt.failed || st === 'failed');
              const isBypassed = Boolean(opt.bypassed || st === 'bypassed');
              const isLockedOut = Boolean(opt.locked_out || st === 'locked_out');
              const isTerminal = isDone || isFailed || isBypassed || isLockedOut;
              const roleKey = String(opt.role || 'aid').toLowerCase();
              const roleStyle = getOptionalRoleStyle(roleKey);

              return (
                <div
                  key={opt.optional_id || opt.id || oIdx}
                  className={`border-l-2 ${roleStyle.accentBar} bg-white/[0.025] rounded-r-lg px-2.5 py-2 space-y-1.5 ${
                    isLockedOut ? 'opacity-70' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-1.5 flex-wrap">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase font-bold ${roleStyle.badge}`}>
                        {cleanProseLocations(opt.badge || t(`quests.optional_role_${roleKey}`, `Optional — ${roleKey}`))}
                      </span>
                      {(roleKey === 'aid' || roleKey === 'bypass') && !isFailed && !isLockedOut && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-teal-950/60 text-teal-300 border border-teal-700/50">
                          ⏪ -1 {t('quests.threat_clock', 'Threat')}
                        </span>
                      )}
                    </div>

                    {isDone && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-700/50">
                        ✓ {opt.bonus_claimed ? t('quests.bonus_claimed', 'Bonus Claimed') : t('quests.completed', 'Completed')}
                      </span>
                    )}
                    {isFailed && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-950/70 text-rose-300 border border-rose-700/50 uppercase">
                        ✕ {t('quests.failed', 'Failed')}
                      </span>
                    )}
                    {isBypassed && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-700/50 uppercase">
                        ⏭️ {t('quests.bypassed', 'Bypassed')}
                      </span>
                    )}
                    {isLockedOut && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-900 text-gray-400 border border-neutral-700 uppercase">
                        🔒 {t('quests.locked_out', 'Locked Out')}
                      </span>
                    )}
                  </div>

                  <p
                    className={`text-[12px] leading-[1.45] hk-quest-prose ${
                      isDone
                        ? 'text-emerald-300/80 line-through'
                        : isFailed
                          ? 'text-rose-300/75 line-through'
                          : isLockedOut
                            ? 'text-gray-500 line-through'
                            : 'text-gray-100 font-medium'
                    }`}
                  >
                    {cleanProseLocations(opt.title || opt.text)}
                  </p>

                  {opt.stakes_hint && !isDone && (
                    <p
                      className={`text-[11px] leading-snug italic hk-quest-prose ${
                        roleKey === 'threatened' ? 'text-rose-300/90' : 'text-gray-400'
                      }`}
                    >
                      {cleanProseLocations(opt.stakes_hint)}
                    </p>
                  )}

                  {!isTerminal && (opt.target_location || opt.target_npc) && (
                    <div className="flex items-start justify-between gap-2 pt-0.5 text-[11px] text-amber-200/90">
                      <div className="flex items-start gap-1.5 min-w-0 flex-1">
                        <MapPin size={12} className="text-amber-400 shrink-0 mt-0.5" />
                        <span
                          className="break-words leading-snug"
                          title={opt.target_location ? formatFullLocationPath(opt.target_location) : undefined}
                        >
                          {opt.target_location ? formatCleanLocation(opt.target_location) : ''}
                          {opt.target_location && opt.target_npc ? ' · ' : ''}
                          {opt.target_npc ? opt.target_npc : ''}
                        </span>
                      </div>
                      {opt.target_location && onOpenWorldMap && (
                        <button
                          type="button"
                          onClick={() => onOpenWorldMap(opt.target_location)}
                          className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10px] font-bold shrink-0"
                        >
                          {t('quests.locate_btn', 'Map')}
                        </button>
                      )}
                    </div>
                  )}

                  {!isTerminal && Array.isArray(opt.approaches) && opt.approaches.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {opt.approaches.map((ap, aIdx) => (
                        <span
                          key={aIdx}
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                            ap.burned
                              ? 'bg-red-950/40 text-red-400/70 border-red-800/40 line-through'
                              : 'bg-white/5 text-gray-300 border-fantasy-border/50'
                          }`}
                        >
                          {ap.stat || ap.approach_id}
                          {ap.gold_cost ? ` (${formatScenarioCurrency(ap.gold_cost, scenario)})` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export const LegacySubObjectives = ({ subObjectives = [], onOpenWorldMap, t }) => {
  if (!Array.isArray(subObjectives) || subObjectives.length === 0) return null;
  const completedSubs = subObjectives.filter((so) => so.completed || so.done).length;
  const currentStepEyebrow = stripLeadingEmoji(t('quests.current_step', 'Current Step'), '🎯').replace(/[:：]\s*$/, '');
  const keyContactLabel = stripLeadingEmoji(t('quests.key_contact', 'Key Contact:'), '👤');

  return (
    <div className="border-t border-white/[0.07]">
      <div className="px-3 py-2 flex justify-between items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider">
        <span>{t('quests.objectives_and_waypoints', 'Objectives & Waypoint Locations')}</span>
        <span className="font-mono text-fantasy-accent">
          {completedSubs} / {subObjectives.length} {t('quests.completed_label', 'Completed')}
        </span>
      </div>

      <div className="divide-y divide-white/[0.07]">
        {subObjectives.map((so, idx) => {
          const isDone = Boolean(so.completed || so.done);
          const isObj = typeof so === 'object' && so !== null;
          const soText = typeof so === 'string' ? so : so.text || so.label || so.title || so.description;
          const soArch = isObj ? so.archetype : '';
          const soWps = isObj && Array.isArray(so.waypoints) ? so.waypoints : [];
          const activeWp = isObj ? so.active_waypoint : null;
          const targetLoc = isObj ? so.target_location || activeWp?.target_location || '' : '';
          const targetNpc = isObj ? so.target_npc || activeWp?.target_npc || '' : '';
          const stageLabel = isObj ? so.stage_label || activeWp?.stage_label || '' : '';
          const stageIdx = isObj ? so.stage_index || activeWp?.stage_index || 1 : 1;
          const totalStages = isObj ? so.total_stages || soWps.length || 0 : 0;

          return (
            <div key={idx} className="px-3 py-2.5 space-y-2">
              <div className="flex items-start gap-2">
                {isDone ? (
                  <CheckCircle2 size={14} className="text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <Circle size={14} className="text-amber-400 shrink-0 mt-0.5" />
                )}
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center justify-between gap-1.5 flex-wrap">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10.5px] font-mono font-bold text-fantasy-accent">
                        Objective #{isObj && so.id ? so.id : idx + 1}
                      </span>
                      {soArch && (
                        <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-white/5 text-gray-300 border border-fantasy-border/60 uppercase font-semibold">
                          {soArch}
                        </span>
                      )}
                    </div>
                    {totalStages > 0 && (
                      <span
                        className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                          isDone
                            ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                            : 'bg-amber-950/60 text-amber-300 border-amber-700/50 font-bold'
                        }`}
                      >
                        {isDone
                          ? `✓ ${totalStages}/${totalStages}`
                          : `${t('quests.stage_label_short', 'Stage')} ${stageIdx}/${totalStages}`}
                      </span>
                    )}
                  </div>
                  <p
                    className={`text-[12px] leading-[1.45] hk-quest-prose ${
                      isDone ? 'text-gray-500 line-through' : 'text-gray-100 font-medium'
                    }`}
                  >
                    {cleanProseLocations(soText)}
                  </p>
                </div>
              </div>

              {!isDone && (targetLoc || stageLabel || targetNpc) && (
                <div className="border-l-2 border-l-fantasy-accent bg-fantasy-accent/[0.06] rounded-r-lg px-2.5 py-2 space-y-1.5">
                  {stageLabel && (
                    <div className="space-y-0.5">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-fantasy-accent">
                        {currentStepEyebrow}
                      </div>
                      <p className="text-[12px] text-gray-100 font-semibold leading-snug hk-quest-prose">
                        {cleanProseLocations(stageLabel)}
                      </p>
                    </div>
                  )}
                  {targetLoc && (
                    <div className="flex items-start justify-between gap-2">
                      <div
                        className="flex items-start gap-1.5 text-[11.5px] text-amber-200 min-w-0 flex-1"
                        title={formatFullLocationPath(targetLoc)}
                      >
                        <MapPin size={12} className="text-amber-400 shrink-0 mt-0.5" />
                        <span className="break-words">{formatCleanLocation(targetLoc)}</span>
                      </div>
                      {onOpenWorldMap && (
                        <button
                          type="button"
                          onClick={() => onOpenWorldMap(targetLoc)}
                          className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10px] font-bold shrink-0 transition-colors"
                          title={t('quests.view_on_atlas', 'View on World Atlas')}
                        >
                          {t('quests.locate_btn', 'Map')}
                        </button>
                      )}
                    </div>
                  )}
                  {targetNpc && (
                    <div className="flex items-center gap-1.5 text-[11px] text-cyan-200">
                      <User size={12} className="text-cyan-400 shrink-0" />
                      <span>
                        <span className="text-cyan-300/85">{keyContactLabel}</span> <strong>{targetNpc}</strong>
                      </span>
                    </div>
                  )}
                </div>
              )}

              {soWps.length > 1 && !isDone && (
                <div className="pt-1 border-t border-white/[0.06] space-y-1.5">
                  {soWps.map((wp, wIdx) => {
                    const wpStatus = wp.status || 'locked';
                    const wpDone = wpStatus === 'completed';
                    const wpActive = wpStatus === 'active';
                    const wpStageNum = wp.stage_index || wIdx + 1;
                    if (wpActive) {
                      return (
                        <div key={wIdx} className="flex items-center gap-2 text-[11px]">
                          <span className="w-2 h-2 rounded-full bg-fantasy-accent shrink-0" />
                          <span className="font-semibold text-amber-200">
                            {t('quests.stage_label_short', 'Stage')} {wpStageNum}
                          </span>
                          <span className="text-[9.5px] font-mono uppercase px-1.5 py-0.5 rounded bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/35">
                            {t('quests.in_progress', 'In Progress')}
                          </span>
                        </div>
                      );
                    }
                    return (
                      <div
                        key={wIdx}
                        className={`flex items-start gap-1.5 text-[11px] leading-snug ${
                          wpDone ? 'text-emerald-400/75' : 'text-gray-400'
                        }`}
                      >
                        {wpDone ? (
                          <CheckCircle2 size={11} className="text-emerald-400 shrink-0 mt-0.5" />
                        ) : (
                          <Lock size={11} className="text-gray-400 shrink-0 mt-0.5" />
                        )}
                        <div className="min-w-0 flex-1">
                          <span className={wpDone ? 'line-through hk-quest-prose' : 'hk-quest-prose'}>
                            {t('quests.stage_label_short', 'Stage')} {wpStageNum}:{' '}
                            {cleanProseLocations(wp.stage_label)}
                          </span>
                          {wp.target_location && (
                            <span className="block text-[10.5px] text-gray-400 break-words">
                              {formatCleanLocation(wp.target_location)}
                              {wp.target_npc ? ` · ${wp.target_npc}` : ''}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const FogOfWarDossierSection = ({
  questObj,
  allowTurnIn = true,
  busyAction,
  onTurnIn,
  scenario = 'fantasy',
  t,
}) => {
  const fow = questObj?.fow_dossier;
  if (!fow || fow.dossier_stage !== 'compiled') return null;

  const maxAl = Math.max(2, fow.max_alert || 4);
  const curAl = Math.min(maxAl, fow.alert_level || 0);
  const leads = Array.isArray(fow.leads) ? fow.leads : [];
  const hasStructured = Boolean(
    (questObj?.has_structured_objectives || fow.has_structured_objectives) &&
      (questObj?.main_objective || fow.main_objective)
  );
  const displayLeads = hasStructured
    ? leads.filter((ld) => !ld.is_optional || (Array.isArray(ld.scouted_enemies) && ld.scouted_enemies.length > 0))
    : leads;
  const twist = fow.twist || {};
  const tItem = fow.tangible_item || {};
  const threatClock = fow.threat_clock && fow.threat_clock.enabled ? fow.threat_clock : null;
  const tcMax = threatClock ? Math.max(2, Number(threatClock.max_segments || 6)) : 6;
  const tcFilled = threatClock ? Math.min(tcMax, Math.max(0, Number(threatClock.filled || 0))) : 0;

  return (
    <div className="px-3 py-2.5 border-t border-white/[0.07] space-y-2.5">
      {/* Inline Alert & Threat Meters */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-bold uppercase tracking-wider text-gray-400">
            {t('quests.alert_meter', 'Alert')}:{' '}
            <span className={curAl >= maxAl - 1 ? 'text-red-400' : 'text-amber-300'}>
              {curAl}/{maxAl}
            </span>
          </span>
          <div className="flex items-center gap-1">
            {Array.from({ length: maxAl }).map((_, i) => (
              <span
                key={i}
                className={`w-2 h-2 rounded-full ${
                  i < curAl ? 'bg-red-500 shadow-[0_0_4px_rgba(239,68,68,0.8)]' : 'bg-neutral-700'
                }`}
              />
            ))}
          </div>
        </div>

        {threatClock && (
          <div className="space-y-1 pt-1 border-t border-white/[0.05]">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-bold uppercase tracking-wider text-orange-300/90">
                ⏳ {t('quests.threat_clock', 'Threat')}:{' '}
                <span className={tcFilled >= 4 ? 'text-red-400' : tcFilled >= 2 ? 'text-orange-300' : 'text-amber-200'}>
                  {tcFilled}/{tcMax}
                </span>
              </span>
              <div className="flex items-center gap-1">
                {Array.from({ length: tcMax }).map((_, i) => (
                  <span
                    key={i}
                    className={`w-2.5 h-2 rounded-sm ${
                      i < tcFilled
                        ? tcFilled >= 6
                          ? 'bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.85)]'
                          : tcFilled >= 4
                            ? 'bg-orange-500 shadow-[0_0_4px_rgba(249,115,22,0.75)]'
                            : 'bg-amber-400'
                        : 'bg-neutral-700'
                    }`}
                  />
                ))}
              </div>
            </div>

            {(threatClock.paused ||
              threatClock.pushed_back ||
              threatClock.engaged === false ||
              threatClock.next_threshold_teaser ||
              threatClock.last_consequence_note ||
              threatClock.last_consequence_event ||
              threatClock.reinforced ||
              threatClock.world_scar_pending) && (
              <div className="flex items-center justify-between gap-1.5 flex-wrap text-[10.5px] text-gray-300">
                <span className="text-orange-200/90 hk-quest-prose">
                  {cleanProseLocations(
                    (() => {
                      const ev = threatClock.last_consequence_event;
                      if (ev && ev.type) {
                        const tr = t('quest.threat_clock.consequences.' + ev.type, {
                          param: ev.param,
                          defaultValue: threatClock.last_consequence_note || '',
                        });
                        if (tr) {
                          return tr
                            .replace('{param}', ev.param != null ? ev.param : '')
                            .replace(/\s*\(\s*\)/g, '')
                            .replace(/\s*（\s*）/g, '')
                            .replace(/:\s*$/g, '')
                            .replace(/：\s*$/g, '')
                            .trim();
                        }
                      }
                      return (
                        threatClock.last_consequence_note ||
                        `${t('quests.threat_next', 'Next Threshold')} (${threatClock.next_threshold || 2}/${tcMax}): ${threatClock.next_threshold_teaser || threatClock.next_threshold_label || ''}`
                      );
                    })()
                  )}
                </span>
                <div className="flex items-center gap-1 flex-wrap">
                  {threatClock.paused && (
                    <span className="px-1.5 py-0.5 rounded bg-sky-950/70 text-sky-300 border border-sky-700/50 font-mono text-[9.5px]">
                      ⏸️ {t('quests.threat_paused', 'Paused (Climax)')}
                    </span>
                  )}
                  {threatClock.pushed_back && (
                    <span className="px-1.5 py-0.5 rounded bg-teal-950/70 text-teal-300 border border-teal-700/50 font-mono text-[9.5px]">
                      ⏪ {t('quests.threat_pushed_back', 'Threat Delayed (-1)')}
                    </span>
                  )}
                  {threatClock.engaged === false && (
                    <span className="px-1.5 py-0.5 rounded bg-neutral-800/80 text-gray-300 border border-neutral-600/50 font-mono text-[9.5px]">
                      💤 {t('quests.threat_dormant', 'Dormant until Chapter engaged')}
                    </span>
                  )}
                  {threatClock.reinforced && (
                    <span className="px-1.5 py-0.5 rounded bg-red-950/70 text-red-300 border border-red-700/50 font-mono text-[9.5px]">
                      {t('quests.threat_reinforced', 'Reinforcements')}
                    </span>
                  )}
                  {threatClock.world_scar_pending && (
                    <span className="px-1.5 py-0.5 rounded bg-rose-950/70 text-rose-200 border border-rose-700/50 font-mono text-[9.5px]">
                      {t('quests.threat_scar_pending', 'Chapter Scar Risk')}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Known Leads */}
      {displayLeads.length > 0 && (
        <div className="pt-2 border-t border-white/[0.06] space-y-1.5">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
            {t('quests.known_leads', 'Known Leads')}
          </span>
          <div className="divide-y divide-white/[0.06]">
            {displayLeads.map((ld, lIdx) => {
              const isDone = ld.status === 'completed';
              const isBypassed = ld.status === 'bypassed';
              return (
                <div key={ld.lead_id || lIdx} className="py-1.5 first:pt-0 last:pb-0 space-y-1">
                  <div className="flex items-start justify-between gap-2">
                    <span
                      className={`text-[12px] leading-snug hk-quest-prose ${
                        isDone
                          ? 'text-emerald-400/80 line-through'
                          : isBypassed
                            ? 'text-gray-500 italic'
                            : 'text-gray-200 font-medium'
                      }`}
                    >
                      {isDone ? '☑️ ' : isBypassed ? '⏭️ ' : '• '}
                      {cleanProseLocations(ld.title)}
                    </span>
                    {isBypassed && (
                      <span className="text-[9.5px] px-1.5 py-0.5 rounded bg-neutral-800 text-amber-300 border border-amber-700/40 uppercase font-mono shrink-0">
                        {t('quests.bypassed', 'Bypassed')}
                      </span>
                    )}
                  </div>
                  {Array.isArray(ld.approaches) && ld.approaches.length > 0 && !isDone && !isBypassed && (
                    <div className="flex flex-wrap gap-1">
                      {ld.approaches.map((ap, aIdx) => (
                        <span
                          key={aIdx}
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                            ap.burned
                              ? 'bg-red-950/40 text-red-400/70 border-red-800/40 line-through'
                              : 'bg-white/5 text-gray-300 border-fantasy-border/50'
                          }`}
                        >
                          {ap.stat || ap.approach_id}
                          {ap.gold_cost ? ` (${formatScenarioCurrency(ap.gold_cost, scenario)})` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                  {Array.isArray(ld.scouted_enemies) && ld.scouted_enemies.length > 0 && (
                    <div className="text-[10.5px] text-rose-300 font-mono">
                      👁️ {t('quests.scouted_pack', 'Scouted Pack')}:{' '}
                      {ld.scouted_enemies.map((e) => e.name).join(', ')}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Uncovered Twist */}
      {twist.is_discovered && twist.summary && (
        <div className="border-l-2 border-purple-400 bg-purple-950/25 rounded-r-lg px-2.5 py-2 text-[11.5px] text-purple-100 space-y-0.5">
          <strong className="text-[10px] uppercase tracking-wider text-purple-300 block">
            ⚡ {t('quests.uncovered_twist', 'Uncovered Twist')}
          </strong>
          <p className="leading-snug hk-quest-prose">{twist.summary}</p>
        </div>
      )}

      {/* Turn-In Disposition Actions */}
      {allowTurnIn &&
        questObj?.quest_id &&
        (() => {
          const hasAcquiredItem = Boolean(tItem.has_item && tItem.disposition === 'acquired');
          const hasUnacquiredRequiredItem = Boolean(questObj?.required_item && tItem.has_item && !hasAcquiredItem);
          const canDeliver =
            !hasUnacquiredRequiredItem &&
            (fow.turn_in_rules?.mode === 'direct_client' ||
              Boolean(
                fow.climax?.completed ||
                  fow.main_objective?.completed ||
                  questObj?.climax_ready ||
                  !fow.main_objective?.stages?.length
              ));
          if (!canDeliver && !hasAcquiredItem) return null;
          return (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {canDeliver && (
                <button
                  type="button"
                  disabled={Boolean(busyAction)}
                  onClick={() => onTurnIn(questObj.quest_id, 'deliver')}
                  className="px-2.5 py-1 rounded bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-300 border border-emerald-700/60 text-[11px] font-bold transition-colors"
                >
                  📦 {t('quests.deliver_contract', 'Deliver')}
                </button>
              )}
              {canDeliver && twist.is_discovered && twist.side_switch_available && (
                <button
                  type="button"
                  disabled={Boolean(busyAction)}
                  onClick={() => onTurnIn(questObj.quest_id, 'side_switch')}
                  className="px-2.5 py-1 rounded bg-purple-950/60 hover:bg-purple-900/70 text-purple-200 border border-purple-600/60 text-[11px] font-bold transition-colors"
                >
                  🤝 {t('quests.side_switch', 'Side-Switch (1.25x)')}
                </button>
              )}
              {canDeliver && twist.is_discovered && twist.blackmail_available && (
                <button
                  type="button"
                  disabled={Boolean(busyAction)}
                  onClick={() => onTurnIn(questObj.quest_id, 'blackmail_client')}
                  className="px-2.5 py-1 rounded bg-amber-950/60 hover:bg-amber-900/70 text-amber-200 border border-amber-600/60 text-[11px] font-bold transition-colors"
                >
                  🕵️ {t('quests.blackmail_client', 'Blackmail (2x)')}
                </button>
              )}
              {hasAcquiredItem && (
                <>
                  <button
                    type="button"
                    disabled={Boolean(busyAction)}
                    onClick={() => onTurnIn(questObj.quest_id, 'keep')}
                    className="px-2.5 py-1 rounded bg-cyan-950/50 hover:bg-cyan-900/60 text-cyan-200 border border-cyan-700/50 text-[11px] font-bold transition-colors"
                  >
                    🎒 {t('quests.keep_item', 'Keep Item')}
                  </button>
                  <button
                    type="button"
                    disabled={Boolean(busyAction)}
                    onClick={() => onTurnIn(questObj.quest_id, 'fence')}
                    className="px-2.5 py-1 rounded bg-amber-950/50 hover:bg-amber-900/60 text-amber-300 border border-amber-700/50 text-[11px] font-bold transition-colors"
                  >
                    💰 {t('quests.fence_item', 'Fence (1.5x)')}
                  </button>
                  <button
                    type="button"
                    disabled={Boolean(busyAction)}
                    onClick={() => onTurnIn(questObj.quest_id, 'destroy')}
                    className="px-2.5 py-1 rounded bg-red-950/50 hover:bg-red-900/60 text-red-300 border border-red-800/50 text-[11px] font-bold transition-colors"
                  >
                    🔥 {t('quests.destroy_item', 'Destroy')}
                  </button>
                </>
              )}
            </div>
          );
        })()}
    </div>
  );
};
