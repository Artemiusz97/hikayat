import React, { useState, useEffect, useRef, useId, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Flame, ShieldAlert, Sparkles, BookOpen, RefreshCw, X, Lock,
  Zap, Heart, Coins, ArrowUpCircle, CheckCircle2, Skull, Radio
} from 'lucide-react';
import { apiCall } from '../../api/client';
import { isValidSessionId } from '../../utils/session';

const TIER_ROMAN = { 1: 'I', 2: 'II', 3: 'III' };

const APPRAISAL_STYLES = {
  favored: 'bg-emerald-950/75 text-emerald-200 border-emerald-500/60',
  neutral: 'bg-amber-950/65 text-amber-200 border-amber-600/50',
  disdained: 'bg-rose-950/75 text-rose-200 border-rose-500/60',
};

const ELEMENT_BADGE = {
  solar: 'text-amber-300 bg-amber-950/60 border-amber-700/50',
  glacier: 'text-cyan-300 bg-cyan-950/60 border-cyan-700/50',
  voltaic: 'text-yellow-300 bg-yellow-950/60 border-yellow-700/50',
  tempest: 'text-teal-300 bg-teal-950/60 border-teal-700/50',
  seismic: 'text-orange-300 bg-orange-950/60 border-orange-700/50',
  abyssal: 'text-purple-300 bg-purple-950/60 border-purple-700/50',
  verdant: 'text-emerald-300 bg-emerald-950/60 border-emerald-700/50',
  aether: 'text-indigo-300 bg-indigo-950/60 border-indigo-700/50',
  kinetic: 'text-red-300 bg-red-950/60 border-red-700/50',
};

const formatStatLocks = (statLocks, maxHpLockPct) => {
  const parts = [];
  if (maxHpLockPct && Number(maxHpLockPct) > 0) {
    parts.push(`-${Math.round(Number(maxHpLockPct) * 100)}% Max HP`);
  }
  if (statLocks && typeof statLocks === 'object') {
    for (const [stat, delta] of Object.entries(statLocks)) {
      const n = Number(delta);
      if (!Number.isNaN(n) && n !== 0) {
        parts.push(`${n > 0 ? '+' : ''}${n} ${stat.toUpperCase()}`);
      }
    }
  }
  return parts;
};

const EntityContractsModal = ({
  isOpen,
  onClose,
  session,
  user,
  onContractMutated,
  onSessionUpdated,
}) => {
  const { t, i18n } = useTranslation();
  const dialogRef = useRef(null);
  const titleId = useId();

  const [activeTab, setActiveTab] = useState('active'); // 'active' | 'discover' | 'compendium'
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busyKey, setBusyKey] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [selectedTiers, setSelectedTiers] = useState({});

  const sessionId = session?.id;
  const userId = user?.user_id;
  const currentLang = String(i18n?.language || 'en').slice(0, 2);

  const fetchOverview = useCallback(async () => {
    if (!isValidSessionId(sessionId) || !userId) return;
    setLoading(true);
    try {
      const data = await apiCall(
        `/api/contracts/${sessionId}?user_id=${encodeURIComponent(userId)}&lang=${encodeURIComponent(currentLang)}`
      );
      setOverview(data);
      if (data && Array.isArray(data.active_pacts) && data.active_pacts.length === 0 && Array.isArray(data.available_patrons) && data.available_patrons.length > 0) {
        setActiveTab((prev) => (prev === 'active' ? 'discover' : prev));
      }
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Failed to load Entity Contracts.' });
    } finally {
      setLoading(false);
    }
  }, [sessionId, userId, currentLang]);

  // Open/close native <dialog> strictly via .showModal() / .close() (modern-web-guidance: dialog)
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen) {
      if (!dialog.open) {
        setFeedback(null);
        dialog.showModal();
      }
      fetchOverview();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [isOpen, fetchOverview]);

  // Fallback for browsers without native <dialog closedby="any"> support (modern-web-guidance: light-dismiss-a-dialog)
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || typeof HTMLDialogElement === 'undefined') return undefined;
    if ('closedBy' in HTMLDialogElement.prototype) return undefined;

    const handleBackdropClick = (event) => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      const isDialogContent =
        rect.top <= event.clientY &&
        event.clientY <= rect.top + rect.height &&
        rect.left <= event.clientX &&
        event.clientX <= rect.left + rect.width;
      if (isDialogContent) return;
      dialog.close();
    };

    dialog.addEventListener('click', handleBackdropClick);
    return () => dialog.removeEventListener('click', handleBackdropClick);
  }, []);

  const handleDialogClose = () => {
    if (dialogRef.current) {
      dialogRef.current.returnValue = '';
    }
    if (onClose) onClose();
  };

  const handleRitualAction = async (ritualAction, patronId, extra = {}) => {
    if (!isValidSessionId(sessionId) || !userId || busyKey) return;
    const actionTag = `${ritualAction}:${patronId}`;
    setBusyKey(actionTag);
    setFeedback(null);
    try {
      const res = await apiCall(`/api/contracts/${sessionId}/${ritualAction}`, {
        method: 'POST',
        body: JSON.stringify({
          user_id: userId,
          patron_id: patronId,
          tier: extra.tier || 1,
          use_credits: extra.use_credits !== false,
          lang: currentLang,
        }),
      });
      if (res?.overview) {
        setOverview(res.overview);
      } else {
        await fetchOverview();
      }
      if (res?.updated_session && onSessionUpdated) {
        onSessionUpdated(res.updated_session);
      }
      if (onContractMutated) {
        onContractMutated(res);
      }
      if (res?.spawned_exorcism_boss) {
        setFeedback({ type: 'warn', text: res.message || 'Manifestation Exorcism Duel initiated!' });
        if (dialogRef.current?.open) {
          dialogRef.current.close();
        }
        return;
      }
      setFeedback({ type: 'ok', text: res?.message || 'Covenant updated.' });
      if (ritualAction === 'sign') {
        setActiveTab('active');
      }
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Ritual action failed.' });
    } finally {
      setBusyKey(null);
    }
  };

  const activePacts = Array.isArray(overview?.active_pacts) ? overview.active_pacts : [];
  const availablePatrons = Array.isArray(overview?.available_patrons) ? overview.available_patrons : [];
  const compendium = Array.isArray(overview?.compendium) ? overview.compendium : [];
  const channelsActive = Array.isArray(overview?.channels_active) ? overview.channels_active : [];
  const activeGrudges = Array.isArray(overview?.active_grudges) ? overview.active_grudges : [];
  const slotUsed = Number(overview?.slot_used || 0);
  const slotCapacity = Number(overview?.slot_capacity || 2);
  const remoteReady = Boolean(overview?.remote_communion_available);

  return (
    <dialog
      ref={dialogRef}
      closedby="any"
      aria-labelledby={titleId}
      onClose={handleDialogClose}
      className="hk-contracts-dialog"
    >
      <div className="hk-surface bg-fantasy-panel border border-rose-900/60 rounded-2xl shadow-2xl flex flex-col max-h-[calc(var(--app-height,100dvh)-1.5rem)] overflow-hidden text-gray-100">
        {/* Header */}
        <div className="px-4 py-3 border-b border-rose-900/50 bg-gradient-to-r from-rose-950/50 via-fantasy-panel to-black/60 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-xl bg-rose-950/80 border border-rose-600/50 grid place-items-center text-rose-300 shrink-0">
              <Flame size={18} />
            </div>
            <div className="min-w-0">
              <h2 id={titleId} className="hk-display font-bold text-sm sm:text-base text-rose-100 truncate">
                {t('contracts.title', 'Entity Contracts & Devil Pacts')}
              </h2>
              <p className="text-[11px] text-gray-400 truncate">
                {t('contracts.subtitle', 'Zero-MP Covenants • Blood & Tribute Ledger')}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <span
              className="px-2 py-1 rounded-lg bg-black/60 border border-rose-800/50 font-mono text-[11px] text-rose-200 font-bold"
              title={t('contracts.slots_hint', 'Base 2 slots (3 when unmodified END ≥ 7)')}
            >
              🩸 {t('contracts.slots', 'Pact Slots')}: {slotUsed}/{slotCapacity}
            </span>
            <button
              type="button"
              onClick={fetchOverview}
              disabled={loading}
              className="hk-icon-btn"
              title={t('contracts.refresh', 'Refresh')}
              aria-label={t('contracts.refresh', 'Refresh')}
            >
              <RefreshCw size={15} className={loading ? 'animate-spin text-rose-300' : ''} />
            </button>
            <form method="dialog">
              <button
                type="submit"
                value="close"
                autofocus="true"
                className="hk-icon-btn"
                aria-label={t('common.close', 'Close')}
                title={t('common.close', 'Close')}
              >
                <X size={18} />
              </button>
            </form>
          </div>
        </div>

        {/* Status Strip & Tabs */}
        <div className="px-4 pt-2.5 pb-2 border-b border-fantasy-border/50 bg-black/35 space-y-2 shrink-0">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border font-medium ${
                remoteReady
                  ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                  : 'bg-amber-950/60 text-amber-300 border-amber-700/50'
              }`}
            >
              <Radio size={11} />
              <span>
                {remoteReady
                  ? t('contracts.remote_ready', 'Remote Communion Active')
                  : t('contracts.remote_blocked', 'Sanctuary / Quarters Required for Upgrades')}
              </span>
            </span>

            {activeGrudges.length > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-950/80 text-red-200 border border-red-600/60 font-semibold">
                <Skull size={11} />
                <span>{t('contracts.grudge_warning', { count: activeGrudges.length, defaultValue: `Active Grudge Nemeses: ${activeGrudges.length}` })}</span>
              </span>
            )}
          </div>

          <div className="hk-segmented" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'active'}
              onClick={() => setActiveTab('active')}
            >
              <Flame size={13} />
              <span className="truncate">{t('contracts.tabs.active', 'Active Covenants')} ({activePacts.length})</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'discover'}
              onClick={() => setActiveTab('discover')}
            >
              <Sparkles size={13} />
              <span className="truncate">{t('contracts.tabs.discover', 'Discover & Appraise')} ({availablePatrons.length})</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'compendium'}
              onClick={() => setActiveTab('compendium')}
            >
              <BookOpen size={13} />
              <span className="truncate">{t('contracts.tabs.compendium', 'Patron Compendium')} ({compendium.length})</span>
            </button>
          </div>
        </div>

        {/* Feedback Banner */}
        {feedback && (
          <div
            className={`mx-4 mt-2.5 px-3 py-2 rounded-lg border text-xs flex items-center justify-between gap-2 shrink-0 ${
              feedback.type === 'error'
                ? 'bg-red-950/75 border-red-700/70 text-red-200'
                : feedback.type === 'warn'
                  ? 'bg-amber-950/75 border-amber-600/70 text-amber-200'
                  : 'bg-emerald-950/75 border-emerald-700/70 text-emerald-200'
            }`}
          >
            <span>{feedback.text}</span>
            <button type="button" onClick={() => setFeedback(null)} className="text-gray-400 hover:text-white">
              <X size={13} />
            </button>
          </div>
        )}

        {/* Scrollable Content Body */}
        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-4 space-y-3">
          {/* TAB 1: ACTIVE COVENANTS */}
          {activeTab === 'active' && (
            activePacts.length === 0 ? (
              <div className="p-6 rounded-xl bg-black/40 border border-dashed border-rose-900/50 text-center space-y-2">
                <Flame size={26} className="mx-auto text-rose-400/50" />
                <p className="text-xs text-gray-300 max-w-lg mx-auto leading-relaxed">
                  {t('contracts.no_active', 'No active Entity Contracts bound right now.')}
                </p>
                {availablePatrons.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setActiveTab('discover')}
                    className="hk-btn hk-btn-primary mt-2"
                  >
                    <Sparkles size={14} />
                    <span>{t('contracts.tabs.discover', 'Discover & Appraise')} ({availablePatrons.length})</span>
                  </button>
                )}
              </div>
            ) : (
              activePacts.map((pact) => {
                const elemKey = String(pact.element || 'aether').toLowerCase();
                const elemCls = ELEMENT_BADGE[elemKey] || ELEMENT_BADGE.aether;
                const appCls = APPRAISAL_STYLES[pact.appraisal_state] || APPRAISAL_STYLES.neutral;
                const lockPills = formatStatLocks(pact.stat_locks, pact.max_hp_lock_pct);
                const castCosts = pact.cast_costs || {};
                const hpCost = Number(castCosts.hp_cost || 0);
                const credCost = Number(castCosts.credit_cost || 0);
                const isOverdraw = Boolean(castCosts.is_lethal_overdraw);
                const hasBreach = Number(pact.breach_stage || 0) > 0 || Number(pact.unpaid_blood_debt || 0) > 0;
                const nextTier = pact.tier < 3 ? pact.tier + 1 : null;
                const xpPct = pact.tier >= 3
                  ? 100
                  : Math.min(100, Math.round((Number(pact.resonance_xp || 0) / Math.max(1, Number(pact.next_tier_xp_required || 3))) * 100));

                return (
                  <div
                    key={pact.contract_key}
                    className={`rounded-xl border p-3.5 space-y-2.5 transition-colors ${
                      hasBreach
                        ? 'bg-red-950/25 border-red-600/70'
                        : 'bg-black/50 border-rose-900/50 hover:border-rose-700/70'
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-0.5 min-w-0">
                        <div className="flex items-center flex-wrap gap-1.5">
                          <span className="font-rpg font-bold text-sm sm:text-base text-rose-100">
                            {pact.name}
                          </span>
                          <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-rose-950/80 text-rose-200 border border-rose-600/60">
                            {pact.tier >= 3
                              ? t('contracts.max_tier', 'Tier III (Exclusive Core)')
                              : t('contracts.tier', { tier: TIER_ROMAN[pact.tier] || pact.tier, defaultValue: `Tier ${TIER_ROMAN[pact.tier] || pact.tier}` })}
                          </span>
                          <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded border ${elemCls}`}>
                            {pact.element} • {pact.synergy_stat}
                          </span>
                          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${appCls}`}>
                            {t(`contracts.appraisal.${pact.appraisal_state}`, pact.appraisal_state)}
                          </span>
                          {pact.bound_gear_slot && (
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-200 border border-purple-600/60">
                              🔒 {t('contracts.pact_bound', 'Pact-Bound')} ({pact.bound_gear_slot})
                            </span>
                          )}
                        </div>
                        {pact.title && (
                          <p className="text-xs italic text-amber-200/85">{pact.title}</p>
                        )}
                      </div>

                      {/* Resonance Progress */}
                      {pact.tier < 3 && (
                        <div className="w-36 shrink-0 space-y-1">
                          <div className="flex justify-between text-[10px] font-mono text-gray-300">
                            <span>{t('contracts.resonance', { xp: pact.resonance_xp, req: pact.next_tier_xp_required, defaultValue: `Resonance ${pact.resonance_xp}/${pact.next_tier_xp_required}` })}</span>
                            <span>{xpPct}%</span>
                          </div>
                          <div className="h-1.5 w-full rounded-full bg-black/80 border border-rose-900/50 overflow-hidden">
                            <div className="h-full bg-gradient-to-r from-rose-500 to-amber-400" style={{ width: `${xpPct}%` }} />
                          </div>
                        </div>
                      )}
                    </div>

                    {hasBreach && (
                      <div className="px-2.5 py-1.5 rounded-lg bg-red-950/80 border border-red-500/70 text-[11px] text-red-200 flex items-center gap-2 font-semibold">
                        <ShieldAlert size={14} className="text-red-400 shrink-0" />
                        <span>
                          {t('contracts.breach_warning', 'Displeased — Settle Blood Debt within 24h or suffer Violent Severance!')}
                          {pact.unpaid_blood_debt > 0 ? ` (${pact.unpaid_blood_debt} Blood Debt)` : ''}
                        </span>
                      </div>
                    )}

                    {/* Zero-MP Combat Skill + Field Utility */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      <div className="p-2.5 rounded-lg bg-black/60 border border-fantasy-border/50 space-y-1">
                        <div className="flex items-center justify-between gap-1.5">
                          <span className="font-bold text-rose-200 truncate">
                            {pact.combat_skill?.emoji || '🩸'} {pact.combat_skill?.name || 'Covenant Invocation'}
                          </span>
                          <div className="flex items-center gap-1 shrink-0 font-mono text-[10px]">
                            <span className="px-1.5 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-700/50">
                              {t('contracts.zero_mp', '0 MP')}
                            </span>
                            {hpCost > 0 && (
                              <span className={`px-1.5 py-0.5 rounded border ${isOverdraw ? 'bg-red-950 text-red-200 border-red-500 font-bold' : 'bg-rose-950/70 text-rose-200 border-rose-700/50'}`}>
                                <Heart size={9} className="inline mr-0.5" />
                                {hpCost} HP
                              </span>
                            )}
                            {credCost > 0 && (
                              <span className="px-1.5 py-0.5 rounded bg-amber-950/70 text-amber-200 border border-amber-700/50">
                                <Coins size={9} className="inline mr-0.5" />
                                {credCost}
                              </span>
                            )}
                          </div>
                        </div>
                        <p className="text-[11px] text-gray-300 leading-snug">
                          {pact.combat_skill?.description}
                        </p>
                      </div>

                      <div className="p-2.5 rounded-lg bg-black/60 border border-fantasy-border/50 space-y-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-cyan-300 font-bold block">
                          ✨ {t('contracts.passive_label', 'Field Utility')}: {pact.field_utility?.name || 'Pact Passive'}
                        </span>
                        <p className="text-[11px] text-gray-300 leading-snug">
                          {pact.field_utility?.description || 'Grants passive field authority and Kin recognition.'}
                        </p>
                      </div>
                    </div>

                    {/* Locks, Taboo & Tell */}
                    <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
                      {lockPills.map((lp) => (
                        <span key={lp} className="px-2 py-0.5 rounded bg-rose-950/60 text-rose-200 border border-rose-800/60 font-mono">
                          {lp}
                        </span>
                      ))}
                      {pact.taboo_desc && (
                        <span className="px-2 py-0.5 rounded bg-amber-950/50 text-amber-200 border border-amber-800/50">
                          ⚠️ {t('contracts.taboo_label', 'Taboo')}: {pact.taboo_desc}
                        </span>
                      )}
                      {pact.visual_tell && (
                        <span className="px-2 py-0.5 rounded bg-neutral-900/80 text-gray-300 border border-neutral-700/60 italic">
                          👁️ {pact.visual_tell}
                        </span>
                      )}
                    </div>

                    {/* Actions Footer */}
                    <div className="pt-2 border-t border-fantasy-border/40 flex flex-wrap items-center justify-end gap-2">
                      <button
                        type="button"
                        disabled={Boolean(busyKey)}
                        onClick={() => handleRitualAction('feed', pact.patron_id)}
                        className="px-3 py-1.5 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-200 border border-emerald-600/60 text-xs font-semibold flex items-center gap-1.5 disabled:opacity-45"
                      >
                        <Zap size={13} />
                        <span>{t('contracts.feed', 'Commune / Pay Tithe')}</span>
                      </button>

                      {nextTier && (
                        <button
                          type="button"
                          disabled={Boolean(busyKey) || !pact.can_upgrade}
                          onClick={() => handleRitualAction('upgrade', pact.patron_id, { tier: nextTier })}
                          className="px-3 py-1.5 rounded-lg bg-amber-950/60 hover:bg-amber-900/70 text-amber-200 border border-amber-500/60 text-xs font-semibold flex items-center gap-1.5 disabled:opacity-40"
                          title={!remoteReady ? t('contracts.remote_blocked') : undefined}
                        >
                          <ArrowUpCircle size={13} />
                          <span>{t('contracts.upgrade', { tier: TIER_ROMAN[nextTier] || nextTier, defaultValue: `Deepen to Tier ${TIER_ROMAN[nextTier]}` })}</span>
                        </button>
                      )}

                      <button
                        type="button"
                        disabled={Boolean(busyKey)}
                        onClick={() => handleRitualAction('sever', pact.patron_id)}
                        className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 disabled:opacity-45 ${
                          pact.peaceful_scrub_available
                            ? 'bg-cyan-950/50 hover:bg-cyan-900/60 text-cyan-200 border-cyan-700/60'
                            : 'bg-red-950/70 hover:bg-red-900/80 text-red-200 border-red-600/70'
                        }`}
                        title={pact.sever_method_label}
                      >
                        <Skull size={13} />
                        <span>
                          {pact.peaceful_scrub_available
                            ? t('contracts.sever_scrub', { fee: pact.scrub_credit_fee, defaultValue: `Cleanse (${pact.scrub_credit_fee} Cr)` })
                            : t('contracts.sever_exorcism', 'Exorcism Duel')}
                        </span>
                      </button>
                    </div>
                  </div>
                );
              })
            )
          )}

          {/* TAB 2: DISCOVER & APPRAISE */}
          {activeTab === 'discover' && (
            <div className="space-y-3">
              {channelsActive.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {channelsActive.map((ch) => (
                    <span
                      key={`${ch.channel}:${ch.label}`}
                      className="px-2.5 py-0.5 rounded-full text-[10.5px] font-mono bg-rose-950/60 text-rose-200 border border-rose-700/50"
                    >
                      📡 {ch.label}
                    </span>
                  ))}
                </div>
              )}

              {availablePatrons.length === 0 ? (
                <div className="p-6 rounded-xl bg-black/40 border border-dashed border-fantasy-border/60 text-center space-y-2">
                  <Sparkles size={26} className="mx-auto text-gray-500" />
                  <p className="text-xs text-gray-400 max-w-lg mx-auto leading-relaxed">
                    {t('contracts.no_available', 'No Patron channels reachable at your current coordinates.')}
                  </p>
                </div>
              ) : (
                availablePatrons.map((offer) => {
                  const pid = offer.patron_id;
                  const appState = offer.appraisal?.state || 'neutral';
                  const appCls = APPRAISAL_STYLES[appState] || APPRAISAL_STYLES.neutral;
                  const elemCls = ELEMENT_BADGE[String(offer.element || 'aether').toLowerCase()] || ELEMENT_BADGE.aether;
                  const upfrontCap = Number(offer.appraisal?.upfront_tier_cap || 1);
                  const chosenTier = selectedTiers[pid] || 1;
                  const lockPills = formatStatLocks(offer.tier1_stat_locks, offer.tier1_max_hp_lock_pct);
                  const isSigning = busyKey === `sign:${pid}`;

                  return (
                    <div
                      key={pid}
                      className="rounded-xl bg-black/50 border border-fantasy-border/70 hover:border-rose-700/60 p-3.5 space-y-2.5 transition-colors"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="space-y-0.5 min-w-0">
                          <div className="flex items-center flex-wrap gap-1.5">
                            <span className="font-rpg font-bold text-sm sm:text-base text-gray-100">
                              {offer.name}
                            </span>
                            <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded border ${elemCls}`}>
                              {offer.element} • {offer.synergy_stat}
                            </span>
                            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-bold ${appCls}`}>
                              {t(`contracts.appraisal.${appState}`, appState)}
                            </span>
                            {offer.has_bound_gear && (
                              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-purple-950/75 text-purple-200 border border-purple-600/60">
                                🗡️ {t('contracts.pact_bound', 'Pact-Bound')} ({offer.bound_gear_slot})
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-gray-400 flex flex-wrap items-center gap-1.5">
                            {offer.title && <span className="italic text-amber-200/85">{offer.title}</span>}
                            <span>•</span>
                            <span className="font-mono text-[10px] text-rose-300/90">{offer.channel_label}</span>
                          </div>
                        </div>

                        {offer.exclusive_tier3_holder && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/70 text-amber-200 border border-amber-700/60">
                            👑 Tier III Held: {offer.exclusive_tier3_holder}
                          </span>
                        )}
                      </div>

                      {offer.appraisal?.quote && (
                        <p className="text-xs italic text-rose-200/90 bg-rose-950/25 border-l-2 border-rose-500/70 pl-2.5 py-1">
                          “{offer.appraisal.quote}”
                        </p>
                      )}

                      {offer.summary && (
                        <p className="text-xs text-gray-300 leading-relaxed">{offer.summary}</p>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                        <div className="p-2 rounded-lg bg-black/60 border border-fantasy-border/50">
                          <span className="font-bold text-rose-200 block">
                            {offer.combat_skill?.emoji || '🩸'} {offer.combat_skill?.name} ({t('contracts.zero_mp', '0 MP')})
                          </span>
                          <span className="text-[11px] text-gray-400">{offer.combat_skill?.description}</span>
                        </div>
                        <div className="p-2 rounded-lg bg-black/60 border border-fantasy-border/50">
                          <span className="font-bold text-cyan-200 block">
                            ✨ {offer.field_utility?.name || t('contracts.passive_label', 'Field Utility')}
                          </span>
                          <span className="text-[11px] text-gray-400">{offer.field_utility?.description}</span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
                        {lockPills.map((lp) => (
                          <span key={lp} className="px-2 py-0.5 rounded bg-rose-950/60 text-rose-200 border border-rose-800/60 font-mono">
                            {lp}
                          </span>
                        ))}
                        {offer.taboo_desc && (
                          <span className="px-2 py-0.5 rounded bg-amber-950/50 text-amber-200 border border-amber-800/50">
                            ⚠️ {t('contracts.taboo_label', 'Taboo')}: {offer.taboo_desc}
                          </span>
                        )}
                      </div>

                      <div className="pt-2 border-t border-fantasy-border/40 flex flex-wrap items-center justify-between gap-2">
                        {upfrontCap > 1 ? (
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10.5px] font-mono text-emerald-300">
                              {t('contracts.select_tier', 'Initial Covenant Tier')}:
                            </span>
                            {[1, 2, 3].filter((tr) => tr <= upfrontCap && !(tr === 3 && offer.exclusive_tier3_holder)).map((tr) => (
                              <button
                                key={tr}
                                type="button"
                                onClick={() => setSelectedTiers((prev) => ({ ...prev, [pid]: tr }))}
                                className={`px-2 py-0.5 rounded text-[11px] font-mono border ${
                                  chosenTier === tr
                                    ? 'bg-emerald-900/80 text-emerald-100 border-emerald-400 font-bold'
                                    : 'bg-black/60 text-gray-400 border-fantasy-border'
                                }`}
                              >
                                {TIER_ROMAN[tr]}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <span className="text-[11px] text-gray-400 font-mono">
                            {offer.blocked_reason ? (
                              <span className="text-rose-300 flex items-center gap-1">
                                <Lock size={11} /> {offer.blocked_reason}
                              </span>
                            ) : (
                              t('contracts.tier', { tier: 'I', defaultValue: 'Tier I' })
                            )}
                          </span>
                        )}

                        <button
                          type="button"
                          disabled={!offer.can_sign || Boolean(busyKey)}
                          onClick={() => handleRitualAction('sign', pid, { tier: chosenTier })}
                          className="hk-btn hk-btn-primary !h-8 !px-3.5 text-xs"
                        >
                          <Flame size={13} />
                          <span>
                            {isSigning
                              ? t('contracts.signing', 'Sealing...')
                              : t('contracts.sign', 'Forge Covenant')}
                          </span>
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* TAB 3: ACCOUNT-WIDE PATRON COMPENDIUM */}
          {activeTab === 'compendium' && (
            compendium.length === 0 ? (
              <div className="p-6 rounded-xl bg-black/40 border border-dashed border-fantasy-border/60 text-center space-y-2">
                <BookOpen size={26} className="mx-auto text-gray-500" />
                <p className="text-xs text-gray-400">
                  {t('contracts.no_compendium', 'No Entity Patrons recorded in your account archive yet.')}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {compendium.map((entry) => {
                  const elemCls = ELEMENT_BADGE[String(entry.element || 'aether').toLowerCase()] || ELEMENT_BADGE.aether;
                  const maxTier = Number(entry.max_tier_reached || 1);
                  return (
                    <div
                      key={entry.patron_id}
                      className="p-3 rounded-xl bg-black/50 border border-fantasy-border/60 space-y-1.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-rpg font-bold text-sm text-gray-100 truncate">
                          {entry.display_name}
                        </span>
                        {entry.is_currently_contracted ? (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-950/80 text-rose-200 border border-rose-600/60 font-bold shrink-0">
                            🩸 {t('contracts.currently_bound', 'Active Pact')}
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-700/50 shrink-0 flex items-center gap-0.5">
                            <CheckCircle2 size={10} /> {t('contracts.contracted_badge', 'Contracted')}
                          </span>
                        )}
                      </div>
                      {entry.display_title && (
                        <p className="text-[11px] italic text-amber-200/80 truncate">{entry.display_title}</p>
                      )}
                      <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono text-gray-300 pt-1">
                        <span className={`px-1.5 py-0.5 rounded border uppercase ${elemCls}`}>
                          {entry.element}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-black/60 border border-fantasy-border/50">
                          Max {TIER_ROMAN[maxTier] || maxTier}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-black/60 border border-fantasy-border/50">
                          {t('contracts.times_signed', { count: entry.times_signed || 1, defaultValue: `Signed: ${entry.times_signed || 1}x` })}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-black/60 border border-fantasy-border/50">
                          {t('contracts.times_invoked', { count: entry.times_invoked || 0, defaultValue: `Invoked: ${entry.times_invoked || 0}x` })}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          )}
        </div>
      </div>
    </dialog>
  );
};

export default EntityContractsModal;
