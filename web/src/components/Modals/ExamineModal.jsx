import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Eye,
  Swords,
  Users,
  Package,
  Compass,
  ShieldAlert,
  Sparkles,
  FlaskConical,
  Gift,
  Hand,
  MapPin,
  Lock,
  X,
} from 'lucide-react';
import { apiCall } from '../../api/client';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import { useUiPreferences } from '../../theme/UiPreferencesProvider';
import {
  formatClockTime,
  getDayOfWeekLabel,
  getTimeOfDayPhaseInfo,
} from '../../utils/timeFormat';
import { resolveNpcDemographics } from '../../utils/npcDemographics';

const ExamineModal = ({
  isOpen,
  onClose,
  session,
  user,
  inCombat = false,
  processing = false,
  onTargetUseItem,
  onTargetGiveGift,
  onPickupItem,
  onOpenWorldMap,
}) => {
  const { t } = useTranslation();
  const { clockFormat } = useUiPreferences();
  const [snapshot, setSnapshot] = useState(null);
  const [loadingSnap, setLoadingSnap] = useState(false);
  const [loadingProse, setLoadingProse] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen || !session?.id || !user?.user_id) return;
    let cancelled = false;
    const controller = new AbortController();

    const loadExamine = async () => {
      setError(null);
      setLoadingSnap(true);
      setLoadingProse(false);
      try {
        const snap = await apiCall(
          `/api/adventure/examine?session_id=${encodeURIComponent(session.id)}&user_id=${encodeURIComponent(user.user_id)}&include_prose=false`,
          { signal: controller.signal }
        );
        if (cancelled) return;
        setSnapshot(snap);
        setLoadingSnap(false);

        if (!snap?.prose_ready) {
          setLoadingProse(true);
          try {
            const full = await apiCall(
              `/api/adventure/examine?session_id=${encodeURIComponent(session.id)}&user_id=${encodeURIComponent(user.user_id)}&include_prose=true`,
              { signal: controller.signal }
            );
            if (!cancelled && full) {
              setSnapshot(full);
            }
          } catch (proseErr) {
            if (proseErr?.isUserAbort || proseErr?.name === 'AbortError') return;
            if (!cancelled) {
              setSnapshot((prev) =>
                prev
                  ? {
                      ...prev,
                      narrative_prose: prev.fallback_prose || '',
                      prose_ready: true,
                    }
                  : prev
              );
            }
          } finally {
            if (!cancelled) setLoadingProse(false);
          }
        }
      } catch (err) {
        if (err?.isUserAbort || err?.name === 'AbortError') return;
        if (!cancelled) {
          setError(err?.message || 'Could not inspect the scene.');
          setLoadingSnap(false);
          setLoadingProse(false);
        }
      }
    };

    loadExamine();
    return () => {
      cancelled = true;
      try {
        controller.abort();
      } catch {}
    };
  }, [isOpen, session?.id, session?.turn_count, session?.current_location, session?.stealth_state?.is_hidden, user?.user_id]);

  const env = snapshot?.environment || {};
  const sceneMode = snapshot?.scene_mode || (inCombat ? 'combat' : 'exploration');
  const dayNum = Number(env.current_day || session?.current_day || 1);
  const curMin = Number(env.current_minute ?? session?.current_minute ?? 480);
  const dayLabel = getDayOfWeekLabel(dayNum, t);
  const clockLabel = formatClockTime(curMin, clockFormat);
  const phaseInfo = getTimeOfDayPhaseInfo(curMin, t);
  const PhaseIcon = phaseInfo.Icon;

  const npcs = snapshot?.present_npcs || [];
  const objects = snapshot?.objects || [];
  const clues = snapshot?.clues || [];
  const exits = env.exits || [];
  const stealth = snapshot?.stealth_and_epistemic || {};
  const combatIntel = snapshot?.combat_intel || [];

  const titleLabel =
    sceneMode === 'combat'
      ? t('examine.intel_title', 'Tactical Intel')
      : t('examine.title', 'Examine Surroundings');

  const proseText = snapshot?.narrative_prose || (!loadingProse ? snapshot?.fallback_prose : '');

  const modeBadgeLabel =
    sceneMode === 'combat'
      ? t('examine.mode_combat', 'Combat Intel')
      : sceneMode === 'intimate'
        ? t('examine.mode_intimate', 'Intimate Scene')
        : sceneMode === 'dialogue'
          ? t('examine.mode_dialogue', 'Conversation')
          : t('examine.mode_exploration', 'Exploration');

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={titleLabel}
      maxWidthClass="max-w-2xl"
      className="p-4 sm:p-5 space-y-4 max-h-[85dvh] flex flex-col overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-fantasy-border/35 pb-3 shrink-0">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            {sceneMode === 'combat' ? (
              <Swords size={17} className="text-rose-400 shrink-0" />
            ) : (
              <Eye size={17} className="text-fantasy-accent shrink-0" />
            )}
            <h3 className="font-rpg font-bold text-fantasy-accent text-base leading-none">
              {titleLabel}
            </h3>
            <span className="hk-chip hk-chip-accent text-[10px]">
              {modeBadgeLabel}
            </span>
            <span className="hk-chip text-[10px] text-emerald-300 border-emerald-500/40 bg-emerald-500/10">
              {t('examine.zero_turn_badge', '0 Turns')}
            </span>
          </div>

          <div className="flex items-center gap-2 text-xs text-gray-300 flex-wrap">
            <span className="inline-flex items-center gap-1 min-w-0">
              <MapPin size={12} className="text-fantasy-accent shrink-0" />
              <span className="truncate font-semibold">
                {env.sub_location && !String(env.location || '').toLowerCase().includes(String(env.sub_location).toLowerCase())
                  ? `${env.location || session?.current_location} · ${env.sub_location}`
                  : env.location || session?.current_location || 'Unknown Area'}
              </span>
            </span>
            <span className="text-gray-500">•</span>
            <span className="inline-flex items-center gap-1 whitespace-nowrap">
              <PhaseIcon size={12} className={`${phaseInfo.colorClass} shrink-0`} />
              <span>{dayLabel} • {clockLabel}</span>
            </span>
          </div>
        </div>

        <MotionButton
          onClick={onClose}
          aria-label={t('common.close', 'Close')}
          className="hk-icon-btn h-8 min-w-8 shrink-0"
        >
          <X size={16} />
        </MotionButton>
      </div>

      {/* Scrollable Body */}
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar space-y-4 pr-1">
        {error && (
          <div className="p-3 rounded-xl bg-red-500/15 border border-red-500/40 text-red-200 text-xs">
            {error}
          </div>
        )}

        {loadingSnap && !snapshot ? (
          <div className="space-y-3 animate-pulse">
            <div className="h-20 rounded-xl bg-gray-500/15 border border-fantasy-border/25" />
            <div className="h-24 rounded-xl bg-gray-500/15 border border-fantasy-border/25" />
          </div>
        ) : (
          <>
            {/* Sensory / Overview Prose */}
            <div className="rounded-xl p-3.5 bg-gray-500/10 border border-fantasy-border/30 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-fantasy-accent flex items-center gap-1.5">
                  <Sparkles size={12} />
                  {t('examine.overview_heading', 'Sensory Impressions')}
                </span>
                {snapshot?.per_tier && (
                  <span className="text-[10px] font-mono uppercase text-gray-400">
                    PER: {snapshot.per_tier}
                  </span>
                )}
              </div>
              {loadingProse && !snapshot?.narrative_prose ? (
                <div className="space-y-2 py-1 animate-pulse">
                  <div className="h-3.5 w-full rounded bg-gray-400/20" />
                  <div className="h-3.5 w-5/6 rounded bg-gray-400/20" />
                  <span className="block text-[11px] text-gray-400 italic pt-0.5">
                    {t('examine.loading_prose', 'Taking in the finer details...')}
                  </span>
                </div>
              ) : (
                <p className="text-sm text-gray-100 leading-relaxed font-serif">
                  {proseText}
                </p>
              )}
            </div>

            {/* Stealth, Privacy & Epistemic Awareness */}
            {(stealth.is_hidden || stealth.detection_meter > 0 || stealth.witness_count > 0 || sceneMode === 'dialogue' || sceneMode === 'intimate') && (
              <div className="rounded-xl p-3 bg-gray-500/10 border border-fantasy-border/30 flex items-center justify-between gap-2 flex-wrap text-xs">
                <div className="flex items-center gap-2">
                  <ShieldAlert size={14} className="text-amber-400 shrink-0" />
                  <span className="font-semibold text-gray-200">
                    {stealth.is_hidden
                      ? t('examine.stealth_active', {
                          alert: stealth.alert_level || 'unaware',
                          defaultValue: `Hidden · Alert: ${stealth.alert_level || 'unaware'}`,
                        })
                      : t('examine.privacy_status', {
                          privacy: String(stealth.privacy_level || 'public').replace('_', ' '),
                          bystanders: stealth.bystander_count ?? 0,
                          defaultValue: `Privacy: ${String(stealth.privacy_level || 'public').replace('_', ' ')} (${stealth.bystander_count ?? 0} onlookers)`,
                        })}
                  </span>
                </div>
                {stealth.witness_count > 0 && (
                  <span className="hk-chip text-[10px] text-amber-200 border-amber-500/40 bg-amber-500/15">
                    {t('examine.witnesses_count', { count: stealth.witness_count, defaultValue: `${stealth.witness_count} witnesses` })}
                  </span>
                )}
              </div>
            )}

            {/* Combat Tactical Intel */}
            {sceneMode === 'combat' && combatIntel.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-rose-300 flex items-center gap-1.5">
                  <Swords size={13} />
                  {t('examine.combat_intel_section', 'Hostile Threats')} ({combatIntel.length})
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {combatIntel.map((en, idx) => (
                    <div
                      key={`${en.name}-${idx}`}
                      className="rounded-xl p-3 bg-rose-500/10 border border-rose-500/30 space-y-1.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-gray-100 truncate">{en.name}</span>
                        <span className="hk-chip text-[10px] text-rose-200 border-rose-500/40 bg-rose-500/20 shrink-0">
                          {snapshot?.show_enemy_hp && en.hp != null
                            ? `${en.hp}/${en.max_hp} HP · ${en.condition_label}`
                            : en.condition_label}
                        </span>
                      </div>
                      {en.intent && (
                        <p className="text-[11px] text-amber-200">
                          ⚡ {t('examine.telegraphed_intent', 'Intent')}: {en.intent}
                        </p>
                      )}
                      {en.status_effects?.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {en.status_effects.map((st, sIdx) => (
                            <span key={sIdx} className="hk-chip text-[10px]">
                              {st}
                            </span>
                          ))}
                        </div>
                      )}
                      {(en.weaknesses?.length > 0 || en.resistances?.length > 0 || en.immunities?.length > 0) ? (
                        <div className="text-[11px] text-gray-300 space-y-0.5 pt-0.5 border-t border-rose-500/20">
                          {en.weaknesses?.length > 0 && (
                            <div className="text-emerald-300">
                              ✦ {t('examine.weaknesses', 'Weaknesses')}: {en.weaknesses.join(', ')}
                            </div>
                          )}
                          {en.resistances?.length > 0 && (
                            <div className="text-amber-300">
                              🛡 {t('examine.resistances', 'Resistances')}: {en.resistances.join(', ')}
                            </div>
                          )}
                          {en.immunities?.length > 0 && (
                            <div className="text-rose-300">
                              🚫 {t('examine.immunities', 'Immunities')}: {en.immunities.join(', ')}
                            </div>
                          )}
                        </div>
                      ) : (
                        snapshot?.per_tier && !['high', 'keen'].includes(snapshot.per_tier) && (
                          <div className="text-[10px] text-gray-400 flex items-center gap-1 pt-0.5">
                            <Lock size={10} />
                            <span>{t('examine.higher_per_hint', 'Higher PER reveals detailed weaknesses')}</span>
                          </div>
                        )
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Present NPCs */}
            <div className="space-y-2">
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
                <Users size={13} className="text-fantasy-accent" />
                {t('examine.npcs_section', 'People Present')} ({npcs.length})
              </h4>
              {npcs.length === 0 ? (
                <p className="text-xs text-gray-400 italic px-1">
                  {t('examine.no_npcs', 'Nobody else is visible nearby.')}
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {npcs.map((npc, idx) => {
                    const demographics = resolveNpcDemographics(npc, t);
                    return (
                    <div
                      key={`${npc.name}-${idx}`}
                      className="rounded-xl p-3 bg-gray-500/10 border border-fantasy-border/30 flex flex-col justify-between gap-2"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-bold text-gray-100 truncate">
                            {npc.name}
                          </span>
                          <span className="hk-chip text-[10px] shrink-0">
                            {npc.relationship_tier || 'Stranger'}
                          </span>
                        </div>
                        {demographics?.hasAny && (
                          <div className="flex flex-wrap items-center gap-1 text-[9.5px] leading-tight">
                            {demographics.ageCategory && (
                              <span className={`px-1.5 py-0.5 rounded border font-medium ${demographics.ageCategory.pillClass}`}>
                                {demographics.ageCategory.label}
                              </span>
                            )}
                            {demographics.genderInfo && (
                              <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border ${demographics.genderInfo.pillClass}`}>
                                {demographics.genderInfo.symbol && (
                                  <span aria-hidden="true">{demographics.genderInfo.symbol}</span>
                                )}
                                <span>{demographics.genderInfo.label}</span>
                              </span>
                            )}
                            {demographics.raceLabel && (
                              <span className="hk-chip text-[9.5px]">{demographics.raceLabel}</span>
                            )}
                          </div>
                        )}
                        {(npc.role || npc.is_party_companion || npc.is_dialogue_partner) && (
                          <div className="flex flex-wrap gap-1 text-[10px] text-gray-400">
                            {npc.role && <span>{npc.role}</span>}
                            {npc.is_party_companion && (
                              <span className="text-cyan-300 font-semibold">• Companion</span>
                            )}
                            {npc.is_dialogue_partner && (
                              <span className="text-fantasy-accent font-semibold">• Conversing</span>
                            )}
                          </div>
                        )}
                        {npc.activity && (
                          <p className="text-[11px] text-amber-200/90">
                            🎯 {npc.activity}
                          </p>
                        )}
                        {npc.clothing_summary && (
                          <p className="text-[11px] text-gray-300 truncate" title={npc.clothing_summary}>
                            👔 {npc.clothing_summary}
                          </p>
                        )}
                        {npc.holding && (
                          <p className="text-[11px] text-gray-400 truncate">
                            ✋ {t('examine.holding', 'Holding')}: {npc.holding}
                          </p>
                        )}
                        {npc.subtle_tell && (
                          <p className="text-[11px] text-purple-300 italic">
                            ✦ {npc.subtle_tell}
                          </p>
                        )}
                      </div>

                      {!npc.is_anomalous && (
                        <div className="flex items-center gap-1.5 pt-1 border-t border-fantasy-border/20">
                          {onTargetUseItem && (
                            <MotionButton
                              disabled={processing}
                              onClick={() =>
                                onTargetUseItem({
                                  type: npc.is_party_companion ? 'companion' : 'npc',
                                  name: npc.name,
                                })
                              }
                              className="flex-1 px-2 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/35 text-emerald-200 text-[10px] font-semibold flex items-center justify-center gap-1 disabled:opacity-40"
                            >
                              <FlaskConical size={11} />
                              <span>{t('examine.use_item_shortcut', 'Use Item')}</span>
                            </MotionButton>
                          )}
                          {onTargetGiveGift && (
                            <MotionButton
                              disabled={processing || sceneMode === 'combat'}
                              onClick={() =>
                                onTargetGiveGift({
                                  type: npc.is_party_companion ? 'companion' : 'npc',
                                  name: npc.name,
                                })
                              }
                              className="flex-1 px-2 py-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/35 text-amber-200 text-[10px] font-semibold flex items-center justify-center gap-1 disabled:opacity-40"
                            >
                              <Gift size={11} />
                              <span>{t('examine.gift_shortcut', 'Gift')}</span>
                            </MotionButton>
                          )}
                        </div>
                      )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Scene Objects & Clues */}
            {(objects.length > 0 || clues.length > 0) && (
              <div className="space-y-2">
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
                  <Package size={13} className="text-fantasy-accent" />
                  {t('examine.objects_section', 'Notable Objects & Leads')}
                </h4>
                <div className="space-y-1.5">
                  {objects.map((obj, idx) => (
                    <div
                      key={`${obj.display_name}-${idx}`}
                      className="rounded-xl p-2.5 bg-gray-500/10 border border-fantasy-border/25 flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-gray-100 truncate">
                          {obj.display_name}
                        </div>
                        {obj.description && (
                          <div className="text-[11px] text-gray-400 truncate">
                            {obj.description}
                          </div>
                        )}
                      </div>
                      {obj.pickupable && sceneMode !== 'combat' && onPickupItem && (
                        <MotionButton
                          disabled={processing}
                          onClick={() => onPickupItem(obj.raw_name || obj.display_name, obj.display_name)}
                          className="shrink-0 px-2.5 py-1 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/35 border border-fantasy-accent/45 text-fantasy-accent text-[11px] font-semibold flex items-center gap-1 disabled:opacity-40"
                        >
                          <Hand size={12} />
                          <span>{t('examine.pickup_shortcut', 'Pick Up')}</span>
                        </MotionButton>
                      )}
                    </div>
                  ))}
                  {clues.map((clue, idx) => (
                    <div
                      key={`${clue.title}-${idx}`}
                      className="rounded-xl p-2.5 bg-cyan-500/10 border border-cyan-500/30 space-y-0.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-cyan-200 truncate">
                          🔍 {clue.title}
                        </span>
                        <span className="hk-chip text-[10px]">
                          {clue.category || 'lead'}
                        </span>
                      </div>
                      {clue.lead_text && (
                        <p className="text-[11px] text-gray-300 leading-snug">
                          {clue.lead_text}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Visible Exits */}
            {exits.length > 0 && (
              <div className="space-y-1.5">
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center gap-1.5">
                  <Compass size={13} className="text-fantasy-accent" />
                  {t('examine.exits_section', 'Visible Exits')}
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {exits.map((exName, idx) => (
                    <button
                      key={`${exName}-${idx}`}
                      type="button"
                      onClick={() => {
                        if (onOpenWorldMap) {
                          onClose();
                          onOpenWorldMap(exName);
                        }
                      }}
                      className="px-2.5 py-1 rounded-lg bg-gray-500/15 hover:bg-fantasy-accent/20 border border-fantasy-border/35 text-xs text-gray-200 hover:text-fantasy-accent transition-colors"
                    >
                      {exName}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AcrylicModal>
  );
};

export default ExamineModal;
