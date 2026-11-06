import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Compass, CheckCircle2, Circle, Search, Award, 
  MapPin, Coins, Sparkles, ChevronDown, ChevronRight, ShieldAlert,
  FileSearch, RefreshCw, PlusCircle, Trash2, Zap
} from 'lucide-react';
import { formatCleanLocation, cleanProseLocations } from '../../utils/locationFormat';

const CATEGORY_META = {
  physical: { icon: '🔍', label: 'Physical', color: 'text-amber-300 bg-amber-950/50 border-amber-700/50' },
  testimonial: { icon: '🗣️', label: 'Testimonial', color: 'text-cyan-300 bg-cyan-950/50 border-cyan-700/50' },
  digital: { icon: '💾', label: 'Digital', color: 'text-purple-300 bg-purple-950/50 border-purple-700/50' },
  document: { icon: '📄', label: 'Document', color: 'text-blue-300 bg-blue-950/50 border-blue-700/50' },
  deduction: { icon: '⚡', label: 'Breakthrough', color: 'text-emerald-300 bg-emerald-950/60 border-emerald-600/60' },
};

const QuestLogPanel = ({ codexHook, onRefreshCharacter, character, onOpenWorldMap }) => {
  const { t } = useTranslation();
  const {
    quests,
    availableBounties = [],
    activeStoryQuest,
    clues = [],
    noticeBoardLabel = 'Bounty Board',
    currentChapter = 1,
    maxChapters = 11,
    campaignSpine = null,
    campaignEndGoals = [],
    chapterDigest = [],
    loading,
    generateBounties,
    bountyAction,
    deduceClues,
    accuseSuspect,
    turnInQuest,
    chooseEpilogue,
  } = codexHook;

  const [subTab, setSubTab] = useState('story'); // 'story' | 'bounties' | 'caseboard' | 'campaign' | 'history'
  const [historyFilter, setHistoryFilter] = useState('all'); // 'all' | 'Completed' | 'Failed' | 'Abandoned'
  const [showCompleted, setShowCompleted] = useState(false);
  const [busyAction, setBusyAction] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [isStoryExpanded, setIsStoryExpanded] = useState(true);
  const [expandedSideQuests, setExpandedSideQuests] = useState({});
  const [expandedBounties, setExpandedBounties] = useState({});

  const toggleSideQuest = (id) => {
    setExpandedSideQuests(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleBounty = (id) => {
    setExpandedBounties(prev => ({ ...prev, [id]: !prev[id] }));
  };

  // Caseboard states
  const [selectedSuspect, setSelectedSuspect] = useState('__all__');
  const [clueAId, setClueAId] = useState('');
  const [clueBId, setClueBId] = useState('');

  // Group quests by type/status
  const sideQuests = (quests || []).filter(q => {
    const qType = (q.quest_type || '').toLowerCase();
    const isStory = Boolean(q.is_story_quest) || qType === 'story' || qType === 'story quest' || (activeStoryQuest && q.quest_id === activeStoryQuest.quest_id);
    return !isStory && q.status === 'Active';
  });

  const archivedQuests = (quests || []).filter(q => ['Completed', 'Failed', 'Abandoned'].includes(q.status));
  const filteredArchivedQuests = archivedQuests.filter(q => historyFilter === 'all' || q.status === historyFilter);
  const completedQuests = archivedQuests;

  // Sub-objectives / stages for active story quest
  const subObjectives = activeStoryQuest?.sub_objectives || activeStoryQuest?.stages || [];
  const completedSubs = subObjectives.filter(so => so.completed || so.done).length;

  // Extract unique linked suspects from clues + compiled QuestDossier suspect pools
  const suspectPoolFromDossiers = [
    ...(activeStoryQuest?.fow_dossier?.suspect_pool || []),
    ...sideQuests.flatMap(q => q?.fow_dossier?.suspect_pool || []),
  ];
  const suspects = Array.from(
    new Set([
      ...(clues || [])
        .map(c => (typeof c === 'object' && c.linked_npc ? c.linked_npc.trim() : ''))
        .filter(Boolean),
      ...suspectPoolFromDossiers.map(s => String(s || '').trim()).filter(Boolean),
    ])
  ).sort();

  const filteredClues = (clues || []).filter(c => {
    if (selectedSuspect === '__all__') return true;
    return (c.linked_npc || '').trim().toLowerCase() === selectedSuspect.toLowerCase();
  });

  const handleGenerateBoard = async (forceRefresh = true) => {
    if (!generateBounties || busyAction) return;
    setBusyAction('generate_board');
    setFeedback(null);
    try {
      await generateBounties(forceRefresh);
      setFeedback({ type: 'ok', text: `Refreshed ${noticeBoardLabel} postings!` });
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Could not generate bounties.' });
    } finally {
      setBusyAction(null);
    }
  };

  const handleBountyContract = async (questId, action, haggleAdvance = false) => {
    if (!bountyAction || busyAction) return;
    setBusyAction(`${action}:${questId}`);
    setFeedback(null);
    try {
      const res = await bountyAction(questId, action, haggleAdvance);
      if (onRefreshCharacter && (haggleAdvance || res?.status === 'Failed')) {
        onRefreshCharacter();
      }
      setFeedback({
        type: res?.status === 'Failed' ? 'warn' : 'ok',
        text: res?.message || (action === 'accept' ? 'Bounty accepted!' : 'Bounty updated.'),
      });
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Failed to update contract.' });
    } finally {
      setBusyAction(null);
    }
  };

  const handleTurnIn = async (questId, disposition = 'deliver') => {
    if (!turnInQuest || !questId || busyAction) return;
    setBusyAction(`turnin:${questId}:${disposition}`);
    setFeedback(null);
    try {
      const res = await turnInQuest(questId, disposition);
      if (onRefreshCharacter) onRefreshCharacter();
      setFeedback({
        type: res?.quest_status === 'Failed' ? 'warn' : 'ok',
        title: `Contract ${res?.quest_status || 'Resolved'}`,
        text: res?.gold_awarded
          ? `Resolved (${disposition.replace('_', ' ')}) — +${res.gold_awarded} G awarded!`
          : `Resolved (${disposition.replace('_', ' ')}).`,
      });
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Could not resolve contract.' });
    } finally {
      setBusyAction(null);
    }
  };

  const handleAccuseSuspect = async (mode = 'private') => {
    if (!accuseSuspect || selectedSuspect === '__all__' || busyAction) return;
    const activeCompiledQuests = [activeStoryQuest, ...sideQuests].filter(
      q => q?.quest_id && q?.fow_dossier?.dossier_stage === 'compiled'
    );
    const suspectClues = (clues || []).filter(
      c => c?.linked_npc && c.linked_npc.trim().toLowerCase() === selectedSuspect.toLowerCase() && c.quest_id
    );
    const matchedQuestIds = new Set(suspectClues.map(c => c.quest_id));
    let targetQuest = activeCompiledQuests.find(q => matchedQuestIds.has(q.quest_id));
    if (!targetQuest) {
      targetQuest = activeCompiledQuests.find(q =>
        (q.fow_dossier?.suspect_pool || []).some(s => String(s).toLowerCase() === selectedSuspect.toLowerCase())
      );
    }
    if (!targetQuest) targetQuest = activeCompiledQuests[0];
    if (!targetQuest) {
      setFeedback({ type: 'error', text: 'No active compiled investigation dossier found.' });
      return;
    }
    setBusyAction(`accuse:${mode}`);
    setFeedback(null);
    try {
      const res = await accuseSuspect(targetQuest.quest_id, selectedSuspect, mode);
      if (onRefreshCharacter) onRefreshCharacter();
      setFeedback({
        type: res?.correct ? 'ok' : (mode === 'formal' ? 'error' : 'warn'),
        title: res?.correct ? 'Culprit Confirmed!' : (mode === 'formal' ? 'False Public Accusation!' : 'Private Confrontation'),
        text: res?.message || 'Accusation resolved.',
      });
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Could not resolve accusation.' });
    } finally {
      setBusyAction(null);
    }
  };

  const handleEpilogueDecision = async (choiceId) => {
    if (!chooseEpilogue || busyAction) return;
    setBusyAction(`epilogue:${choiceId}`);
    setFeedback(null);
    try {
      await chooseEpilogue(choiceId);
      setFeedback({
        type: 'ok',
        text: choiceId === 'archive' ? 'Campaign archived to Hall of Legends!' : 'Endless Living World unlocked!',
      });
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Could not resolve epilogue.' });
    } finally {
      setBusyAction(null);
    }
  };

  const renderFogOfWarDossier = (questObj, allowTurnIn = true) => {
    const fow = questObj?.fow_dossier;
    if (!fow || fow.dossier_stage !== 'compiled') return null;
    const maxAl = Math.max(2, fow.max_alert || 4);
    const curAl = Math.min(maxAl, fow.alert_level || 0);
    const leads = Array.isArray(fow.leads) ? fow.leads : [];
    const twist = fow.twist || {};
    const tItem = fow.tangible_item || {};

    return (
      <div className="space-y-2 pt-1.5 border-t border-fantasy-border/30">
        <div className="flex items-center justify-between text-[10px] bg-black/50 px-2 py-1 rounded border border-fantasy-border/40">
          <span className="font-bold uppercase tracking-wider text-gray-400">
            {t('quests.alert_meter', 'Alert')}: <span className={curAl >= maxAl - 1 ? 'text-red-400' : 'text-amber-300'}>{curAl}/{maxAl}</span>
          </span>
          <div className="flex items-center gap-1">
            {Array.from({ length: maxAl }).map((_, i) => (
              <span
                key={i}
                className={`w-2 h-2 rounded-full ${i < curAl ? 'bg-red-500 shadow-[0_0_4px_rgba(239,68,68,0.8)]' : 'bg-neutral-700'}`}
              />
            ))}
          </div>
        </div>

        {leads.length > 0 && (
          <div className="space-y-1.5 bg-black/35 p-2 rounded border border-fantasy-border/40">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
              {t('quests.known_leads', 'Known Leads')}
            </span>
            {leads.map((ld, lIdx) => {
              const isDone = ld.status === 'completed';
              const isBypassed = ld.status === 'bypassed';
              return (
                <div key={ld.lead_id || lIdx} className="text-[10px] space-y-1 border-b border-white/5 last:border-0 pb-1 last:pb-0">
                  <div className="flex items-center justify-between gap-1.5 flex-wrap">
                    <span className={isDone ? 'text-emerald-400/80 line-through' : isBypassed ? 'text-gray-500 italic' : 'text-gray-200 font-semibold'}>
                      {isDone ? '☑️ ' : isBypassed ? '⏭️ ' : '📍 '}{cleanProseLocations(ld.title)}
                    </span>
                    {isBypassed && (
                      <span className="text-[9px] px-1.5 py-0.2 rounded bg-neutral-800 text-amber-300 border border-amber-700/40 uppercase font-mono">
                        {t('quests.bypassed', 'Bypassed')}
                      </span>
                    )}
                  </div>
                  {Array.isArray(ld.approaches) && ld.approaches.length > 0 && !isDone && !isBypassed && (
                    <div className="flex flex-wrap gap-1">
                      {ld.approaches.map((ap, aIdx) => (
                        <span
                          key={aIdx}
                          className={`text-[9px] font-mono px-1.5 py-0.2 rounded border ${
                            ap.burned
                              ? 'bg-red-950/40 text-red-400/70 border-red-800/40 line-through'
                              : 'bg-white/5 text-gray-300 border-fantasy-border/50'
                          }`}
                        >
                          {ap.stat || ap.approach_id}{ap.gold_cost ? ` (${ap.gold_cost}G)` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                  {Array.isArray(ld.scouted_enemies) && ld.scouted_enemies.length > 0 && (
                    <div className="text-[9px] text-rose-300 font-mono">
                      👁️ {t('quests.scouted_pack', 'Scouted Pack')}: {ld.scouted_enemies.map(e => e.name).join(', ')}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {twist.is_discovered && twist.summary && (
          <div className="bg-purple-950/40 border border-purple-600/50 rounded p-2 text-[10px] text-purple-200">
            <strong className="uppercase text-purple-300 block mb-0.5">⚡ {t('quests.uncovered_twist', 'Uncovered Twist')}</strong>
            <span>{twist.summary}</span>
          </div>
        )}

        {allowTurnIn && questObj?.quest_id && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            <button
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => handleTurnIn(questObj.quest_id, 'deliver')}
              className="px-2 py-0.5 rounded bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-300 border border-emerald-700/60 text-[10px] font-bold transition-colors"
            >
              📦 {t('quests.deliver_contract', 'Deliver')}
            </button>
            {twist.is_discovered && twist.side_switch_available && (
              <button
                type="button"
                disabled={Boolean(busyAction)}
                onClick={() => handleTurnIn(questObj.quest_id, 'side_switch')}
                className="px-2 py-0.5 rounded bg-purple-950/60 hover:bg-purple-900/70 text-purple-200 border border-purple-600/60 text-[10px] font-bold transition-colors"
              >
                🤝 {t('quests.side_switch', 'Side-Switch (1.25x)')}
              </button>
            )}
            {twist.is_discovered && twist.blackmail_available && (
              <button
                type="button"
                disabled={Boolean(busyAction)}
                onClick={() => handleTurnIn(questObj.quest_id, 'blackmail_client')}
                className="px-2 py-0.5 rounded bg-amber-950/60 hover:bg-amber-900/70 text-amber-200 border border-amber-600/60 text-[10px] font-bold transition-colors"
              >
                🕵️ {t('quests.blackmail_client', 'Blackmail (2x)')}
              </button>
            )}
            {tItem.has_item && (
              <>
                <button
                  type="button"
                  disabled={Boolean(busyAction)}
                  onClick={() => handleTurnIn(questObj.quest_id, 'keep')}
                  className="px-2 py-0.5 rounded bg-cyan-950/50 hover:bg-cyan-900/60 text-cyan-200 border border-cyan-700/50 text-[10px] font-bold transition-colors"
                >
                  🎒 {t('quests.keep_item', 'Keep Item')}
                </button>
                <button
                  type="button"
                  disabled={Boolean(busyAction)}
                  onClick={() => handleTurnIn(questObj.quest_id, 'fence')}
                  className="px-2 py-0.5 rounded bg-amber-950/50 hover:bg-amber-900/60 text-amber-300 border border-amber-700/50 text-[10px] font-bold transition-colors"
                >
                  💰 {t('quests.fence_item', 'Fence (1.5x)')}
                </button>
                <button
                  type="button"
                  disabled={Boolean(busyAction)}
                  onClick={() => handleTurnIn(questObj.quest_id, 'destroy')}
                  className="px-2 py-0.5 rounded bg-red-950/50 hover:bg-red-900/60 text-red-300 border border-red-800/50 text-[10px] font-bold transition-colors"
                >
                  🔥 {t('quests.destroy_item', 'Destroy')}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    );
  };

  const handleSynthesizeDeduction = async () => {
    if (!deduceClues || !clueAId || busyAction) return;
    setBusyAction('deduce');
    setFeedback(null);
    try {
      const res = await deduceClues(clueAId, clueBId || null);
      if (res?.is_valid) {
        setFeedback({
          type: 'ok',
          title: `⚡ ${res.title || 'Breakthrough Synthesized!'} (+${res.xp_awarded || 50} XP)`,
          text: res.detail_text,
        });
        setClueAId('');
        setClueBId('');
        if (onRefreshCharacter) onRefreshCharacter();
      } else {
        setFeedback({
          type: 'warn',
          title: '🔍 No Logical Connection Found',
          text: res?.detail_text || 'These two leads do not share a corroborating link yet.',
        });
      }
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Deduction check failed.' });
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-2.5 sm:p-3 space-y-3">
      
      {/* Header & Subtabs */}
      <div className="space-y-2.5 border-b border-fantasy-border pb-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Compass size={16} className="text-fantasy-accent" />
            <h3 className="font-rpg font-bold text-xs sm:text-sm text-gray-100 uppercase tracking-wider">{t('quests.journal', 'Quest Journal')}</h3>
          </div>
          <span className="text-[10px] font-mono font-bold text-fantasy-accent bg-black/60 px-2 py-0.5 rounded border border-fantasy-border">
            {(activeStoryQuest ? 1 : 0) + sideQuests.length} {t('quests.active', 'Active')}
          </span>
        </div>

        {/* 5-Tab Switcher: Active | Bounties | Caseboard | Campaign | History */}
        <div className="flex bg-black/70 p-1 rounded-lg border border-fantasy-border/60 gap-1.5 overflow-x-auto no-scrollbar scroll-smooth">
          <button
            type="button"
            onClick={() => { setSubTab('story'); setFeedback(null); }}
            className={`shrink-0 flex items-center justify-center gap-1.5 py-1 px-2.5 rounded-md text-[11px] font-semibold whitespace-nowrap transition-all ${
              subTab === 'story'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <Compass size={12} className="shrink-0" />
            <span>{t('quests.active', 'Active')}</span>
          </button>

          <button
            type="button"
            onClick={() => { setSubTab('bounties'); setFeedback(null); }}
            className={`shrink-0 flex items-center justify-center gap-1.5 py-1 px-2.5 rounded-md text-[11px] font-semibold whitespace-nowrap transition-all ${
              subTab === 'bounties'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <ShieldAlert size={12} className="shrink-0" />
            <span>{t('quests.bounties', 'Bounties')}</span>
            {availableBounties.length > 0 && (
              <span className="text-[9px] px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-300 font-mono shrink-0">
                {availableBounties.length}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => { setSubTab('caseboard'); setFeedback(null); }}
            className={`shrink-0 flex items-center justify-center gap-1.5 py-1 px-2.5 rounded-md text-[11px] font-semibold whitespace-nowrap transition-all ${
              subTab === 'caseboard'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <FileSearch size={12} className="shrink-0" />
            <span>{t('quests.caseboard', 'Caseboard')}</span>
            {clues.length > 0 && (
              <span className="text-[9px] px-1.5 py-0.2 rounded-full bg-cyan-500/20 text-cyan-300 font-mono shrink-0">
                {clues.length}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => { setSubTab('campaign'); setFeedback(null); }}
            className={`shrink-0 flex items-center justify-center gap-1.5 py-1 px-2.5 rounded-md text-[11px] font-semibold whitespace-nowrap transition-all ${
              subTab === 'campaign'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <Award size={12} className="shrink-0" />
            <span>{t('quests.campaign', 'Campaign')}</span>
          </button>

          <button
            type="button"
            onClick={() => { setSubTab('history'); setFeedback(null); }}
            className={`shrink-0 flex items-center justify-center gap-1.5 py-1 px-2.5 rounded-md text-[11px] font-semibold whitespace-nowrap transition-all ${
              subTab === 'history'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <Circle size={12} className="shrink-0" />
            <span>{t('quests.completed', 'Completed')}</span>
          </button>
        </div>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div className={`p-2.5 rounded-lg text-xs border space-y-1 ${
          feedback.type === 'error'
            ? 'bg-red-950/60 border-red-800/60 text-red-200'
            : feedback.type === 'warn'
              ? 'bg-amber-950/60 border-amber-700/60 text-amber-200'
              : 'bg-emerald-950/60 border-emerald-700/60 text-emerald-200'
        }`}>
          <div className="flex items-center justify-between">
            <span className="font-bold">{feedback.title || (feedback.type === 'error' ? 'Alert' : 'Update')}</span>
            <button onClick={() => setFeedback(null)} className="text-[10px] opacity-70 hover:opacity-100">✕</button>
          </div>
          <p className="text-[11px] leading-snug">{feedback.text}</p>
        </div>
      )}

      {loading && !activeStoryQuest && quests.length === 0 ? (
        <p className="text-xs text-gray-500 italic text-center py-8">Consulting journal...</p>
      ) : (
        <div className="space-y-4">
          
          {/* ================================================================
              TAB 5: HISTORY & ARCHIVED QUESTS (Completed / Failed / Abandoned)
             ================================================================ */}
          {subTab === 'history' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap border-b border-fantasy-accent/30 pb-1.5">
                <h4 className="font-bold text-xs text-fantasy-accent uppercase flex items-center gap-1.5">
                  <Compass size={14} /> {t('quests.history_tab', 'Archive')} ({archivedQuests.length})
                </h4>
                <div className="flex items-center gap-1 flex-wrap">
                  {[
                    { id: 'all', label: t('quests.filter_all', 'All') },
                    { id: 'Completed', label: t('quests.completed', 'Completed') },
                    { id: 'Failed', label: t('quests.failed', 'Failed') },
                    { id: 'Abandoned', label: t('quests.abandoned', 'Abandoned') },
                  ].map(f => (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setHistoryFilter(f.id)}
                      className={`px-2 py-0.5 rounded text-[10px] font-semibold border transition-colors ${
                        historyFilter === f.id
                          ? 'bg-fantasy-accent/20 text-fantasy-accent border-fantasy-accent/50'
                          : 'bg-black/50 text-gray-400 border-fantasy-border/50 hover:text-gray-200'
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {filteredArchivedQuests.length > 0 && (
                <div className="space-y-1.5 max-h-56 overflow-y-auto custom-scrollbar pr-1">
                  {filteredArchivedQuests.map((aq, idx) => {
                    const st = aq.status || 'Completed';
                    const badgeStyle =
                      st === 'Completed'
                        ? 'text-emerald-300 bg-emerald-950/60 border-emerald-700/50'
                        : st === 'Failed'
                          ? 'text-red-300 bg-red-950/60 border-red-700/50'
                          : 'text-gray-300 bg-neutral-900 border-neutral-700/60';
                    return (
                      <div key={aq.quest_id || idx} className="bg-black/45 border border-fantasy-border/50 rounded p-2 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-gray-200 truncate">{cleanProseLocations(aq.title)}</span>
                          <span className={`text-[9px] px-1.5 py-0.2 rounded border uppercase font-mono shrink-0 ${badgeStyle}`}>
                            {st}
                          </span>
                        </div>
                        {aq.objective && (
                          <p className="text-[10px] text-gray-400 line-clamp-2">{cleanProseLocations(aq.objective)}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {chapterDigest.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-fantasy-border/40">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                    Chapter Digest
                  </span>
                  {chapterDigest.map((digest, idx) => {
                    const isStr = typeof digest === 'string';
                    const turnMatch = isStr ? digest.match(/\[?Turn\s*(\d+)\]?/i) : null;
                    const turnNum = !isStr && digest?.turn ? digest.turn : (turnMatch ? turnMatch[1] : null);
                    const digestText = isStr
                      ? digest.replace(/^\[?Turn\s*\d+\]?:?\s*/i, '').trim() || digest
                      : (digest?.summary || digest?.narrative || '');
                    return (
                      <div key={idx} className="bg-black/40 border border-fantasy-border/60 rounded p-2.5 space-y-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] font-mono text-gray-400">
                            {turnNum ? `Turn ${turnNum}` : `${t('quests.chapter_note', 'Chapter Note')} #${idx + 1}`}
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-300 leading-snug">
                          {digestText}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}

              {filteredArchivedQuests.length === 0 && chapterDigest.length === 0 && (
                <p className="text-xs text-gray-500 italic text-center py-6 border border-dashed border-neutral-800 rounded-lg">
                  No history recorded yet.
                </p>
              )}
            </div>
          )}
          
          {/* ================================================================
              TAB 1: STORY & ACTIVE QUESTS
             ================================================================ */}
          {subTab === 'story' && (
            <>
              {/* Active Story Quest Card */}
              {activeStoryQuest ? (
                <div className="bg-gradient-to-br from-fantasy-dark via-black/60 to-fantasy-panel border border-fantasy-accent/50 rounded-lg p-3 space-y-2.5 shadow-md relative overflow-hidden transition-all">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-fantasy-accent/5 rounded-full blur-xl pointer-events-none" />

                  {/* Tappable Card Header */}
                  <div 
                    onClick={() => setIsStoryExpanded(prev => !prev)}
                    className="flex justify-between items-start gap-2 cursor-pointer select-none group"
                    title={isStoryExpanded ? "Tap to collapse details" : "Tap to expand details"}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] px-1.5 py-0.2 bg-fantasy-accent/20 text-fantasy-accent font-bold uppercase rounded border border-fantasy-accent/30 tracking-wider">
                          Main Story
                        </span>
                        {(activeStoryQuest.chapter || currentChapter) && (
                          <span className="text-[10px] text-gray-400 font-mono">
                            Chapter {activeStoryQuest.chapter || currentChapter}
                          </span>
                        )}
                        {activeStoryQuest.climax_ready && (
                          <span className="text-[10px] px-1.5 py-0.2 bg-rose-950/80 text-rose-300 font-bold uppercase rounded border border-rose-600/60 animate-pulse">
                            🔥 Climax Ready!
                          </span>
                        )}
                        {subObjectives.length > 0 && (
                          <span className="text-[10px] font-mono text-fantasy-accent bg-black/50 px-1.5 py-0.2 rounded border border-fantasy-border/40">
                            {completedSubs}/{subObjectives.length} Completed
                          </span>
                        )}
                      </div>
                      <h4 className="font-rpg font-bold text-sm text-gray-100 mt-1 leading-snug group-hover:text-fantasy-accent transition-colors">
                        {cleanProseLocations(activeStoryQuest.title || 'The Unfolding Journey')}
                      </h4>
                    </div>

                    <div className="p-1 rounded-md text-gray-400 group-hover:text-fantasy-accent hover:bg-white/5 transition-colors shrink-0 mt-0.5">
                      {isStoryExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </div>
                  </div>

                  {/* Collapsed Compact Preview */}
                  {!isStoryExpanded && (
                    <div 
                      onClick={() => setIsStoryExpanded(true)}
                      className="flex items-center justify-between text-[11px] text-gray-400 italic pt-1 border-t border-fantasy-border/20 cursor-pointer"
                    >
                      <span className="truncate">{cleanProseLocations(activeStoryQuest.objective || 'Tap to view objectives, locations, and rewards.')}</span>
                      <span className="text-[10px] text-fantasy-accent not-italic font-semibold shrink-0 ml-2">Expand ▾</span>
                    </div>
                  )}

                  {/* Expanded Full Details */}
                  {isStoryExpanded && (
                    <div className="space-y-2.5 pt-1 border-t border-fantasy-border/30">
                      {activeStoryQuest.objective && (
                        <p className="text-xs text-gray-300 leading-relaxed bg-black/40 p-2.5 rounded border border-fantasy-border/50">
                          {cleanProseLocations(activeStoryQuest.objective)}
                        </p>
                      )}

                      {activeStoryQuest.climax_ready && (activeStoryQuest.climax_location || activeStoryQuest.target_location) && (
                        <div className="flex items-center justify-between gap-2 text-[11px] text-rose-200 bg-rose-950/50 px-2.5 py-2 rounded border border-rose-600/60">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <MapPin size={13} className="shrink-0 text-rose-400" />
                            <span className="truncate">⚡ Final Showdown Location: <strong>{formatCleanLocation(activeStoryQuest.climax_location || activeStoryQuest.target_location)}</strong></span>
                          </div>
                          {onOpenWorldMap && (
                            <button
                              type="button"
                              onClick={() => onOpenWorldMap(activeStoryQuest.climax_location || activeStoryQuest.target_location)}
                              className="px-2 py-0.5 rounded bg-rose-500/20 hover:bg-rose-500/35 text-rose-200 border border-rose-500/50 text-[10px] font-bold shrink-0 transition-colors"
                            >
                              Locate
                            </button>
                          )}
                        </div>
                      )}

                      {!activeStoryQuest.climax_ready && subObjectives.length === 0 && activeStoryQuest.target_location && (
                        <div className="flex items-center justify-between gap-2 text-[11px] text-amber-300 bg-amber-950/30 px-2.5 py-1.5 rounded border border-amber-700/40">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <MapPin size={12} className="shrink-0" />
                            <span className="truncate">📍 Waypoint Lead: <strong>{formatCleanLocation(activeStoryQuest.target_location)}</strong></span>
                          </div>
                          {onOpenWorldMap && (
                            <button
                              type="button"
                              onClick={() => onOpenWorldMap(activeStoryQuest.target_location)}
                              className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10px] font-bold shrink-0 transition-colors"
                            >
                              Map
                            </button>
                          )}
                        </div>
                      )}

                      {Boolean((activeStoryQuest.required_count || activeStoryQuest.required_item_count || activeStoryQuest.clues_required) > 0) && (
                        <div className="space-y-1">
                          <div className="flex justify-between text-[10px] font-mono text-gray-400">
                            <span>{t('quests.progress', 'Progress')}</span>
                            <span className="text-fantasy-accent">{activeStoryQuest.current_count ?? activeStoryQuest.current_item_count ?? 0} / {activeStoryQuest.required_count || activeStoryQuest.required_item_count || activeStoryQuest.clues_required}</span>
                          </div>
                          <div className="h-1.5 w-full bg-black/70 rounded-full overflow-hidden border border-fantasy-border/40">
                            <div
                              className="h-full bg-fantasy-accent transition-all duration-300"
                              style={{ width: `${Math.min(100, (((activeStoryQuest.current_count ?? activeStoryQuest.current_item_count ?? 0) / (activeStoryQuest.required_count || activeStoryQuest.required_item_count || activeStoryQuest.clues_required)) * 100))}%` }}
                            />
                          </div>
                        </div>
                      )}

                      {subObjectives.length > 0 && (
                        <div className="space-y-2 pt-1">
                          <div className="flex justify-between items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                            <span>Objectives & Waypoint Locations</span>
                            <span className="font-mono text-fantasy-accent">{completedSubs} / {subObjectives.length} Completed</span>
                          </div>
                          <div className="space-y-2">
                            {subObjectives.map((so, idx) => {
                              const isDone = Boolean(so.completed || so.done);
                              const isObj = typeof so === 'object' && so !== null;
                              const soText = typeof so === 'string' ? so : (so.text || so.label || so.title || so.description);
                              const soArch = isObj ? so.archetype : '';
                              const soWps = isObj && Array.isArray(so.waypoints) ? so.waypoints : [];
                              const activeWp = isObj ? so.active_waypoint : null;
                              const targetLoc = isObj ? (so.target_location || activeWp?.target_location || '') : '';
                              const targetNpc = isObj ? (so.target_npc || activeWp?.target_npc || '') : '';
                              const stageLabel = isObj ? (so.stage_label || activeWp?.stage_label || '') : '';
                              const stageIdx = isObj ? (so.stage_index || activeWp?.stage_index || 1) : 1;
                              const totalStages = isObj ? (so.total_stages || soWps.length || 0) : 0;

                              return (
                                <div
                                  key={idx}
                                  className={`p-2 sm:p-2.5 rounded-lg border space-y-1.5 transition-all ${
                                    isDone
                                      ? 'bg-emerald-950/15 border-emerald-800/40'
                                      : 'bg-black/45 border-fantasy-border/70'
                                  }`}
                                >
                                  {/* Sub-Objective Header & Text */}
                                  <div className="flex items-start gap-2 text-xs">
                                    {isDone ? (
                                      <CheckCircle2 size={13} className="text-emerald-400 shrink-0 mt-0.5" />
                                    ) : (
                                      <Circle size={13} className="text-amber-400 shrink-0 mt-0.5" />
                                    )}
                                    <div className="flex-1 min-w-0 space-y-1">
                                      <div className="flex items-center justify-between gap-1.5 flex-wrap">
                                        <div className="flex items-center gap-1.5 flex-wrap">
                                          <span className="text-[10px] font-mono font-bold text-fantasy-accent">
                                            Objective #{isObj && so.id ? so.id : idx + 1}
                                          </span>
                                          {soArch && (
                                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-white/5 text-gray-300 border border-fantasy-border/60 uppercase font-semibold">
                                              {soArch}
                                            </span>
                                          )}
                                        </div>
                                        {totalStages > 0 && (
                                          <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded border ${
                                            isDone
                                              ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                                              : 'bg-amber-950/60 text-amber-300 border-amber-700/50 font-bold'
                                          }`}>
                                            {isDone ? `✓ ${totalStages}/${totalStages} Stages` : `Stage ${stageIdx}/${totalStages}`}
                                          </span>
                                        )}
                                      </div>
                                      <p className={`text-[11px] leading-snug ${
                                        isDone ? 'text-gray-500 line-through' : 'text-gray-200 font-medium'
                                      }`}>
                                        {cleanProseLocations(soText)}
                                      </p>
                                    </div>
                                  </div>

                                  {/* Active Waypoint Destination Callout */}
                                  {!isDone && (targetLoc || stageLabel || targetNpc) && (
                                    <div className="ml-5 bg-amber-950/35 border border-amber-600/50 rounded-md p-2 space-y-1">
                                      {stageLabel && (
                                        <div className="text-[11px] text-amber-100 font-semibold leading-snug flex items-start gap-1.5">
                                          <span className="text-amber-400 shrink-0">🎯 Current Step:</span>
                                          <span>{cleanProseLocations(stageLabel)}</span>
                                        </div>
                                      )}
                                      {targetLoc && (
                                        <div className="flex items-center justify-between gap-2 pt-0.5">
                                          <div className="flex items-center gap-1 text-[11px] text-amber-300 min-w-0">
                                            <MapPin size={12} className="text-amber-400 shrink-0" />
                                            <span className="truncate" title={formatCleanLocation(targetLoc)}>📍 <strong>{formatCleanLocation(targetLoc)}</strong></span>
                                          </div>
                                          {onOpenWorldMap && (
                                            <button
                                              type="button"
                                              onClick={() => onOpenWorldMap(targetLoc)}
                                              className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10px] font-bold shrink-0 transition-colors"
                                              title="View on World Atlas"
                                            >
                                              View on Map
                                            </button>
                                          )}
                                        </div>
                                      )}
                                      {targetNpc && (
                                        <div className="text-[10px] text-cyan-300 flex items-center gap-1">
                                          <span>👤 Key Contact: <strong>{targetNpc}</strong></span>
                                        </div>
                                      )}
                                    </div>
                                  )}

                                  {/* Multi-Stage Roadmap (All Stages & Locations) */}
                                  {soWps.length > 1 && !isDone && (
                                    <div className="ml-5 pt-1 border-t border-fantasy-border/30 space-y-1">
                                      {soWps.map((wp, wIdx) => {
                                        const wpStatus = wp.status || 'locked';
                                        const wpDone = wpStatus === 'completed';
                                        const wpActive = wpStatus === 'active';
                                        return (
                                          <div
                                            key={wIdx}
                                            className={`text-[10px] flex items-start gap-1.5 leading-tight ${
                                              wpDone
                                                ? 'text-emerald-400/70 line-through'
                                                : wpActive
                                                  ? 'text-amber-200 font-semibold'
                                                  : 'text-gray-500'
                                            }`}
                                          >
                                            <span className="shrink-0 mt-0.5">
                                              {wpDone ? '☑️' : wpActive ? '📍' : '🔒'}
                                            </span>
                                            <div className="min-w-0 flex-1">
                                              <span>Stage {wp.stage_index || wIdx + 1}: {cleanProseLocations(wp.stage_label)}</span>
                                              {wp.target_location && (
                                                <span className={`block text-[9px] font-mono ${wpActive ? 'text-amber-300' : 'text-gray-500'}`}>
                                                  ↳ 📍 {formatCleanLocation(wp.target_location)}{wp.target_npc ? ` • 👤 ${wp.target_npc}` : ''}
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
                      )}

                      {renderFogOfWarDossier(activeStoryQuest, false)}

                      {(activeStoryQuest.reward_xp || activeStoryQuest.reward_gold || activeStoryQuest.reward_item) && (
                        <div className="flex items-center gap-3 pt-1 text-[11px] font-mono text-gray-400 border-t border-fantasy-border/30">
                          <span className="text-[10px] uppercase font-bold text-gray-500 tracking-wider">Rewards:</span>
                          {activeStoryQuest.reward_gold && (
                            <span className="flex items-center gap-1 text-amber-300">
                              <Coins size={12} className="text-amber-400" />
                              +{activeStoryQuest.reward_gold} G
                            </span>
                          )}
                          {activeStoryQuest.reward_xp && (
                            <span className="flex items-center gap-1 text-purple-300">
                              <Sparkles size={12} className="text-purple-400" />
                              +{activeStoryQuest.reward_xp} XP
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-4 bg-black/40 rounded border border-dashed border-fantasy-border text-center text-gray-500 text-xs italic">
                  No active main story quest currently assigned.
                </div>
              )}

              {/* Active Side Bounties */}
              {sideQuests.length > 0 && (
                <div className="space-y-2 pt-1">
                  <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldAlert size={12} className="text-fantasy-accent" />
                    <span>Active Contracts & Bounties ({sideQuests.length})</span>
                  </div>
                  <div className="space-y-2">
                    {sideQuests.map((q, idx) => {
                      const qId = q.quest_id || `side-${idx}`;
                      const isExpanded = expandedSideQuests[qId] ?? false;
                      const qStages = q.stages || q.sub_objectives || [];
                      return (
                        <div 
                          key={qId}
                          className="bg-black/50 border border-fantasy-border/60 hover:border-fantasy-border rounded-lg p-2.5 space-y-2 transition-all"
                        >
                          <div 
                            onClick={() => toggleSideQuest(qId)}
                            className="flex justify-between items-start gap-1.5 cursor-pointer select-none group"
                            title={isExpanded ? "Tap to collapse" : "Tap to expand details"}
                          >
                            <div className="min-w-0 flex-1">
                              <h5 className="font-semibold text-xs text-gray-200 flex items-center gap-1.5 flex-wrap group-hover:text-fantasy-accent transition-colors">
                                <span>{cleanProseLocations(q.title)}</span>
                                {q.climax_ready && (
                                  <span className="text-[9px] px-1.5 py-0.2 bg-rose-950/80 text-rose-300 rounded font-bold uppercase border border-rose-600/60">
                                    🔥 Climax Ready!
                                  </span>
                                )}
                              </h5>
                              {!isExpanded && (
                                <p className="text-[10px] text-gray-400 truncate mt-0.5">
                                  {cleanProseLocations(q.stage_label) || (q.target_location ? `📍 ${formatCleanLocation(q.target_location)}` : cleanProseLocations(q.objective || q.description || 'Tap to view details'))}
                                </p>
                              )}
                            </div>
                            <div className="flex items-center gap-1 shrink-0 mt-0.5">
                              <span className="text-[9px] px-1.5 py-0.2 bg-amber-950/60 text-amber-300 rounded font-bold uppercase border border-amber-800/40">
                                {q.quest_type || 'Bounty'}
                              </span>
                              <span className="text-gray-400 group-hover:text-fantasy-accent">
                                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                              </span>
                            </div>
                          </div>

                          {isExpanded && (
                            <div className="space-y-2 pt-1 border-t border-fantasy-border/30">
                              {(q.objective || q.description) && (
                                <p className="text-[11px] text-gray-400 leading-snug">{cleanProseLocations(q.objective || q.description)}</p>
                              )}

                              {(q.target_location || q.stage_label || q.target_npc) && (
                                <div className="bg-amber-950/35 border border-amber-600/50 rounded-md p-2 space-y-1">
                                  {q.stage_label && (
                                    <div className="text-[11px] text-amber-100 font-semibold leading-snug">
                                      🎯 Current Task: {cleanProseLocations(q.stage_label)}
                                    </div>
                                  )}
                                  {q.target_location && (
                                    <div className="flex items-center justify-between gap-2">
                                      <div className="flex items-center gap-1 text-[11px] text-amber-300 min-w-0">
                                        <MapPin size={12} className="text-amber-400 shrink-0" />
                                        <span className="truncate" title={formatCleanLocation(q.target_location)}>📍 <strong>{formatCleanLocation(q.target_location)}</strong></span>
                                      </div>
                                      {onOpenWorldMap && (
                                        <button
                                          type="button"
                                          onClick={() => onOpenWorldMap(q.target_location)}
                                          className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10px] font-bold shrink-0 transition-colors"
                                        >
                                          View on Map
                                        </button>
                                      )}
                                    </div>
                                  )}
                                  {q.target_npc && (
                                    <div className="text-[10px] text-cyan-300">
                                      👤 Contact: <strong>{q.target_npc}</strong>
                                    </div>
                                  )}
                                </div>
                              )}

                              {Boolean((q.required_count || q.required_item_count || q.clues_required) > 0) && (
                                <div className="flex items-center justify-between text-[10px] font-mono text-gray-400 bg-black/40 px-2 py-1 rounded border border-fantasy-border/30">
                                  <span>{t('quests.checklist_progress', 'Checklist Progress')}</span>
                                  <span className="text-fantasy-accent font-bold">{q.current_count ?? q.current_item_count ?? 0} / {q.required_count || q.required_item_count || q.clues_required}</span>
                                </div>
                              )}

                              {qStages.length > 0 && (
                                <div className="space-y-1 bg-black/30 p-2 rounded border border-fantasy-border/30">
                                  {qStages.map((st, sIdx) => {
                                    const done = Boolean(st.completed || st.done || st.status === 'completed');
                                    const isActive = st.status === 'active';
                                    const stLoc = typeof st === 'object' ? st.target_location : '';
                                    const stNpc = typeof st === 'object' ? st.target_npc : '';
                                    return (
                                      <div key={sIdx} className="flex items-start gap-1.5 text-[10px]">
                                        {done ? (
                                          <CheckCircle2 size={11} className="text-emerald-400 shrink-0 mt-0.5" />
                                        ) : (
                                          <Circle size={11} className={`${isActive ? 'text-amber-400' : 'text-gray-500'} shrink-0 mt-0.5`} />
                                        )}
                                        <div className="min-w-0 flex-1">
                                          <span className={done ? 'text-gray-500 line-through' : isActive ? 'text-amber-200 font-semibold' : 'text-gray-400'}>
                                            {cleanProseLocations(typeof st === 'string' ? st : (st.text || st.stage_label || st.label || st.title))}
                                          </span>
                                          {stLoc && !done && (
                                            <span className={`block text-[9px] font-mono ${isActive ? 'text-amber-300' : 'text-gray-500'}`}>
                                              ↳ 📍 {formatCleanLocation(stLoc)}{stNpc ? ` • 👤 ${stNpc}` : ''}
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              )}

                              {renderFogOfWarDossier(q, true)}

                              <div className="flex items-center justify-between pt-1.5 border-t border-fantasy-border/30">
                                <div className="flex items-center gap-2.5 text-[10px] font-mono text-gray-400">
                                  {q.reward_gold ? <span className="text-amber-300">+{q.reward_gold} G</span> : null}
                                  {q.reward_xp ? <span className="text-purple-300">+{q.reward_xp} XP</span> : null}
                                </div>
                                {q.quest_id && (
                                  <button
                                    disabled={Boolean(busyAction)}
                                    onClick={() => handleBountyContract(q.quest_id, 'abandon')}
                                    className="flex items-center gap-1 px-2 py-0.5 rounded bg-red-950/40 hover:bg-red-900/50 text-red-300 border border-red-800/50 text-[10px] font-bold transition-colors"
                                  >
                                    <Trash2 size={10} />
                                    <span>Abandon</span>
                                  </button>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Completed Quests Archive */}
              {completedQuests.length > 0 && (
                <div className="pt-2 border-t border-fantasy-border/40">
                  <button
                    onClick={() => setShowCompleted(!showCompleted)}
                    className="flex items-center justify-between w-full py-1 text-xs text-gray-400 hover:text-gray-200 font-semibold uppercase tracking-wider transition-colors"
                  >
                    <div className="flex items-center gap-1.5">
                      <Award size={13} className="text-emerald-400" />
                      <span>Completed Quests ({completedQuests.length})</span>
                    </div>
                    {showCompleted ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>

                  {showCompleted && (
                    <div className="space-y-1.5 mt-2 max-h-48 overflow-y-auto custom-scrollbar pr-1">
                      {completedQuests.map((cq, i) => (
                        <div 
                          key={cq.quest_id || i}
                          className="bg-black/40 border border-fantasy-border/40 rounded p-2 flex items-center justify-between text-xs"
                        >
                          <div className="flex items-center gap-1.5 min-w-0">
                            <CheckCircle2 size={12} className="text-emerald-400 shrink-0" />
                            <span className="text-gray-300 font-medium truncate">{cleanProseLocations(cq.title)}</span>
                          </div>
                          <span className="text-[10px] text-emerald-400/80 font-mono shrink-0">Claimed</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* ================================================================
              TAB 2: INTERACTIVE BOUNTY BOARD
             ================================================================ */}
          {subTab === 'bounties' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between bg-black/40 p-2.5 rounded-lg border border-fantasy-border/60">
                <div>
                  <h4 className="font-bold text-xs text-gray-200">{noticeBoardLabel}</h4>
                  <p className="text-[10px] text-gray-400">Accept local side contracts for extra Gold & XP.</p>
                </div>
                <button
                  disabled={Boolean(busyAction)}
                  onClick={() => handleGenerateBoard(true)}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/40 text-[11px] font-bold transition-all shrink-0"
                >
                  <RefreshCw size={12} className={busyAction === 'generate_board' ? 'animate-spin' : ''} />
                  <span>{availableBounties.length === 0 ? 'Post Bounties' : 'Refresh Board'}</span>
                </button>
              </div>

              {availableBounties.length === 0 ? (
                <div className="text-center py-8 px-4 text-gray-500 border border-dashed border-fantasy-border/50 rounded-lg space-y-2">
                  <ShieldAlert size={24} className="mx-auto opacity-40 text-amber-400" />
                  <p className="text-xs text-gray-400">No unclaimed postings on the board right now.</p>
                  <p className="text-[11px]">Click "Post Bounties" above to generate fresh local contracts!</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto custom-scrollbar pr-1">
                  {availableBounties.map((b, idx) => {
                    const bId = b.quest_id || `bounty-${idx}`;
                    const isExpanded = expandedBounties[bId] ?? false;
                    return (
                      <div
                        key={bId}
                        className="bg-black/50 border border-fantasy-border/60 hover:border-amber-600/50 rounded-lg p-2.5 space-y-2 transition-all"
                      >
                        <div 
                          onClick={() => toggleBounty(bId)}
                          className="flex justify-between items-start gap-2 cursor-pointer select-none group"
                          title={isExpanded ? "Tap to collapse" : "Tap to view details & accept"}
                        >
                          <div className="min-w-0 flex-1">
                            <h5 className="font-bold text-xs text-gray-100 group-hover:text-amber-300 transition-colors">
                              {cleanProseLocations(b.title)}
                            </h5>
                            {!isExpanded && (
                              <p className="text-[10px] text-gray-400 truncate mt-0.5">
                                {b.target_location ? `📍 ${formatCleanLocation(b.target_location)}` : cleanProseLocations(b.objective || b.description)}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-1 shrink-0 mt-0.5">
                            <span className="text-[9px] px-1.5 py-0.5 bg-amber-950/60 text-amber-300 rounded font-bold uppercase border border-amber-800/50">
                              {b.quest_type || 'Contract'}
                            </span>
                            <span className="text-gray-400 group-hover:text-amber-300">
                              {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </span>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className="space-y-2 pt-1 border-t border-fantasy-border/30">
                            <p className="text-[11px] text-gray-300 leading-snug">{cleanProseLocations(b.objective || b.description)}</p>

                            {b.target_location && (
                              <div className="flex items-center justify-between gap-2 bg-amber-950/30 border border-amber-700/40 rounded px-2 py-1 text-[10px] text-amber-300">
                                <div className="flex items-center gap-1 min-w-0">
                                  <MapPin size={11} className="text-amber-400 shrink-0" />
                                  <span className="truncate" title={formatCleanLocation(b.target_location)}>📍 <strong>{formatCleanLocation(b.target_location)}</strong>{b.target_npc ? ` • 👤 ${b.target_npc}` : ''}</span>
                                </div>
                              </div>
                            )}

                            <div className="flex items-center justify-between pt-1.5 border-t border-fantasy-border/30">
                              <div className="flex items-center gap-2.5 text-[10px] font-mono">
                                {b.reward_gold ? <span className="text-amber-300">+{b.reward_gold} G</span> : null}
                                {b.reward_xp ? <span className="text-purple-300">+{b.reward_xp} XP</span> : null}
                                {b.reward_item ? <span className="text-cyan-300">🎁 {b.reward_item}</span> : null}
                              </div>

                              <div className="flex items-center gap-1.5 flex-wrap">
                                <button
                                  type="button"
                                  disabled={Boolean(busyAction)}
                                  onClick={() => handleBountyContract(b.quest_id, 'accept', false)}
                                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-300 border border-emerald-700/60 text-[11px] font-bold transition-colors cursor-pointer"
                                >
                                  <PlusCircle size={12} />
                                  <span>Accept</span>
                                </button>
                                <button
                                  type="button"
                                  disabled={Boolean(busyAction)}
                                  onClick={() => handleBountyContract(b.quest_id, 'accept', true)}
                                  className="flex items-center gap-1 px-2 py-1 rounded bg-amber-950/60 hover:bg-amber-900/70 text-amber-200 border border-amber-700/60 text-[10px] font-bold transition-colors cursor-pointer"
                                  title="Attempt a CHA check to haggle an upfront Gold advance"
                                >
                                  <Coins size={11} />
                                  <span>{t('quests.accept_advance', 'Accept + Advance (CHA)')}</span>
                                </button>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ================================================================
              TAB 3: DETECTIVE CASEBOARD & 2-CLUE DEDUCTION SYNTHESIZER
             ================================================================ */}
          {subTab === 'caseboard' && (
            <div className="space-y-3">
              {/* 2-Clue Deduction Synthesizer Box */}
              {clues.length >= 2 && (
                <div className="bg-purple-950/20 border border-purple-700/50 rounded-lg p-3 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-purple-300 uppercase tracking-wider flex items-center gap-1.5">
                      <Zap size={13} className="text-amber-400" />
                      <span>Deduction Synthesizer (+50 XP)</span>
                    </span>
                    <span className="text-[10px] font-mono text-gray-400">Pair 2 Leads</span>
                  </div>

                  <div className="grid grid-cols-1 gap-1.5">
                    <select
                      value={clueAId}
                      onChange={e => setClueAId(e.target.value)}
                      className="w-full bg-black/70 border border-fantasy-border rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500"
                    >
                      <option value="">Select Primary Evidence A...</option>
                      {clues.filter(c => !c.is_consumed && c.category !== 'deduction').map((c, idx) => (
                        <option key={c.id || idx} value={c.id}>
                          {c.title || (c.lead_text || c.clue_text || '').slice(0, 50)}
                        </option>
                      ))}
                    </select>

                    <select
                      value={clueBId}
                      onChange={e => setClueBId(e.target.value)}
                      className="w-full bg-black/70 border border-fantasy-border rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-purple-500"
                    >
                      <option value="">Select Corroborating Evidence B...</option>
                      {clues.filter(c => !c.is_consumed && c.category !== 'deduction').map((c, idx) => (
                        <option key={c.id || idx} value={c.id}>
                          {c.title || (c.lead_text || c.clue_text || '').slice(0, 50)}
                        </option>
                      ))}
                    </select>
                  </div>

                  {clueAId && (
                    <div className="text-[10px] text-purple-200 bg-black/50 px-2 py-1.5 rounded border border-purple-500/30">
                      {clueBId
                        ? `🧩 ${t('quests.logic_caseboard_hint', 'Deterministic Logic Caseboard — Corroborating pairs unlock Climax / Twist')}`
                        : `🔮 ${t('quests.single_clue_hint', 'Single-Clue Folklore Recognition — Verified Codex knowledge can identify entities immediately')}`}
                    </div>
                  )}

                  <button
                    disabled={!clueAId || Boolean(busyAction)}
                    onClick={handleSynthesizeDeduction}
                    className={`w-full py-1.5 px-3 rounded text-xs font-bold flex items-center justify-center gap-1.5 border transition-all ${
                      clueAId
                        ? 'bg-purple-600/30 hover:bg-purple-600/45 text-purple-200 border-purple-500/60'
                        : 'bg-black/40 text-gray-600 border-neutral-800 cursor-not-allowed'
                    }`}
                  >
                    <Sparkles size={12} />
                    <span>{busyAction === 'deduce' ? 'Cross-Referencing...' : (clueBId ? '🧩 Synthesize Breakthrough' : '🔮 Deduce with Single Clue')}</span>
                  </button>
                </div>
              )}

              {/* Suspect Filter & Private vs. Formal Accusation */}
              {suspects.length > 0 && (
                <div className="space-y-2 bg-black/35 p-2 rounded border border-fantasy-border/50">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Filter Suspect:</span>
                    <select
                      value={selectedSuspect}
                      onChange={e => setSelectedSuspect(e.target.value)}
                      className="bg-black/60 border border-fantasy-border rounded px-2 py-1 text-xs text-gray-200 focus:outline-none"
                    >
                      <option value="__all__">All Evidence ({clues.length})</option>
                      {suspects.map(s => (
                        <option key={s} value={s}>👤 {s}</option>
                      ))}
                    </select>
                  </div>
                  {selectedSuspect !== '__all__' && (
                    <div className="flex items-center gap-1.5 pt-1 border-t border-white/5">
                      <button
                        type="button"
                        disabled={Boolean(busyAction)}
                        onClick={() => handleAccuseSuspect('private')}
                        className="flex-1 py-1 px-2 rounded bg-cyan-950/50 hover:bg-cyan-900/60 text-cyan-200 border border-cyan-700/50 text-[10px] font-bold transition-colors"
                      >
                        🗣️ {t('quests.confront_privately', 'Confront Privately')}
                      </button>
                      <button
                        type="button"
                        disabled={Boolean(busyAction)}
                        onClick={() => handleAccuseSuspect('formal')}
                        className="flex-1 py-1 px-2 rounded bg-red-950/60 hover:bg-red-900/70 text-red-200 border border-red-700/60 text-[10px] font-bold transition-colors"
                      >
                        ⚖️ {t('quests.accuse_publicly', 'Accuse Publicly')}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Evidence Cards */}
              {filteredClues.length === 0 ? (
                <div className="text-center py-8 px-4 text-gray-500 border border-dashed border-fantasy-border/50 rounded-lg space-y-1.5">
                  <Search size={24} className="mx-auto opacity-40 text-cyan-400" />
                  <p className="text-xs text-gray-400">No investigation leads recorded yet.</p>
                  <p className="text-[11px]">Inspect scenes, question witnesses, or scour NetWire rumors to gather evidence.</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto custom-scrollbar pr-1">
                  {filteredClues.map((c, idx) => {
                    const isObj = typeof c === 'object' && c !== null;
                    const catKey = isObj ? (c.category || 'physical') : 'physical';
                    const cat = CATEGORY_META[catKey] || CATEGORY_META.physical;
                    const title = isObj ? (c.title || 'Evidence Lead') : 'Discovered Clue';
                    const body = isObj ? (c.lead_text || c.clue_text || c.text) : String(c);
                    const isVerified = isObj && Boolean(c.is_verified);

                    return (
                      <div
                        key={(isObj && c.id) || idx}
                        className={`p-3 rounded-lg border space-y-1.5 transition-all ${
                          isVerified
                            ? 'bg-emerald-950/20 border-emerald-700/50'
                            : 'bg-black/50 border-fantasy-border/60'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className={`text-[9px] px-1.5 py-0.5 rounded border font-bold uppercase ${cat.color}`}>
                              {cat.icon} {cat.label}
                            </span>
                            {isVerified && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-600/50 font-bold uppercase">
                                ✓ Verified
                              </span>
                            )}
                          </div>

                          {isObj && c.id && clues.length >= 2 && (
                            <div className="flex items-center gap-1 shrink-0">
                              <button
                                onClick={() => setClueAId(String(c.id))}
                                className={`text-[9px] px-1.5 py-0.5 rounded font-mono border ${
                                  String(clueAId) === String(c.id)
                                    ? 'bg-purple-600 text-white border-purple-400'
                                    : 'bg-black/60 text-gray-400 border-fantasy-border hover:text-gray-200'
                                }`}
                              >
                                Lead A
                              </button>
                              <button
                                onClick={() => setClueBId(String(c.id))}
                                className={`text-[9px] px-1.5 py-0.5 rounded font-mono border ${
                                  String(clueBId) === String(c.id)
                                    ? 'bg-purple-600 text-white border-purple-400'
                                    : 'bg-black/60 text-gray-400 border-fantasy-border hover:text-gray-200'
                                }`}
                              >
                                Lead B
                              </button>
                            </div>
                          )}
                        </div>

                        <h5 className="font-bold text-xs text-gray-100">{cleanProseLocations(title)}</h5>
                        <p className="text-[11px] text-gray-300 leading-snug">{cleanProseLocations(body)}</p>

                        {isObj && (c.linked_npc || c.source_location) && (
                          <div className="flex flex-wrap gap-2 pt-1 text-[10px] text-gray-400 border-t border-fantasy-border/30">
                            {c.linked_npc && (
                              <span className="text-amber-300">👤 Suspect: <strong>{c.linked_npc}</strong></span>
                            )}
                            {c.source_location && (
                              <span className="text-gray-400">📍 {formatCleanLocation(c.source_location)}</span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ================================================================
              TAB 4: CAMPAIGN PROGRESS, END GOALS & CHAPTER DIGEST
             ================================================================ */}
          {subTab === 'campaign' && (
            <div className="space-y-3">
              {/* Chapter Progress Bar */}
              <div className="bg-black/50 border border-fantasy-border/70 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-fantasy-accent uppercase tracking-wider">
                    Campaign Arc Progress
                  </span>
                  <span className="font-mono text-xs font-bold text-gray-200">
                    Chapter {currentChapter || 1} / {maxChapters || 11}
                  </span>
                </div>
                <div className="h-2 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/50">
                  <div
                    className="h-full bg-gradient-to-r from-fantasy-accent to-amber-400 transition-all duration-500"
                    style={{ width: `${Math.max(8, Math.min(100, ((currentChapter || 1) / (maxChapters || 11)) * 100))}%` }}
                  />
                </div>
              </div>

              {/* Ch.10 Hard Game Over / Fallen World Banner */}
              {campaignSpine?.campaign_game_over && (
                <div className="bg-red-950/60 border border-red-600/60 rounded-lg p-3 space-y-1 text-xs text-red-200">
                  <strong className="uppercase tracking-wider text-red-300 block">💀 {t('quests.fallen_world', 'Fallen World — Chapter 10 Climax Defeat')}</strong>
                  <p className="text-[11px] leading-snug">
                    The campaign mastermind triumphed in the Chapter 10 finale. Load a prior checkpoint or begin a new legend.
                  </p>
                </div>
              )}

              {/* Ch.11 Universal Epilogue Decision Banner */}
              {campaignSpine?.epilogue_ready && (
                <div className="bg-amber-950/45 border border-amber-500/60 rounded-lg p-3 space-y-2 text-xs text-amber-100">
                  <strong className="uppercase tracking-wider text-amber-300 block">🌅 {t('quests.epilogue_ready', 'Chapter 11 Playable Epilogue Ready')}</strong>
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      disabled={Boolean(busyAction)}
                      onClick={() => handleEpilogueDecision('archive')}
                      className="flex-1 py-1.5 px-2.5 rounded bg-fantasy-accent/25 hover:bg-fantasy-accent/40 text-amber-200 border border-fantasy-accent/60 text-[11px] font-bold transition-colors"
                    >
                      🏛️ {t('quests.epilogue_archive', 'Archive Campaign')}
                    </button>
                    <button
                      type="button"
                      disabled={Boolean(busyAction)}
                      onClick={() => handleEpilogueDecision('endless')}
                      className="flex-1 py-1.5 px-2.5 rounded bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-200 border border-emerald-600/60 text-[11px] font-bold transition-colors"
                    >
                      ♾️ {t('quests.epilogue_endless', 'Continue in Endless World')}
                    </button>
                  </div>
                </div>
              )}

              {/* Active World Scars */}
              {Array.isArray(campaignSpine?.world_scars) && campaignSpine.world_scars.length > 0 && (
                <div className="bg-rose-950/25 border border-rose-700/50 rounded-lg p-3 space-y-2">
                  <span className="text-[10px] font-bold text-rose-300 uppercase tracking-wider block">
                    🔥 {t('quests.world_scars', 'Active World Scars')} ({campaignSpine.world_scars.length})
                  </span>
                  <div className="space-y-1.5">
                    {campaignSpine.world_scars.map((sc, sIdx) => (
                      <div key={sc.event_key || sIdx} className="bg-black/45 border border-rose-800/40 rounded p-2 text-[11px]">
                        <div className="font-bold text-rose-200">{sc.title}</div>
                        {sc.location_name && (
                          <div className="text-[10px] text-amber-300 font-mono">📍 {formatCleanLocation(sc.location_name)}</div>
                        )}
                        {sc.description && <p className="text-[10px] text-gray-300 mt-0.5">{sc.description}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Campaign End Goals */}
              <div className="bg-black/40 border border-fantasy-border/60 rounded-lg p-3 space-y-2">
                <span className="text-[10px] font-bold text-amber-300 uppercase tracking-wider block">
                  🏆 Campaign End Goals
                </span>
                {campaignEndGoals.length === 0 ? (
                  <p className="text-xs text-gray-500 italic">Long-term victory milestones will crystallize as your adventure unfolds.</p>
                ) : (
                  <div className="space-y-1.5">
                    {campaignEndGoals.map((goal, idx) => {
                      const isDone = typeof goal === 'object' && Boolean(goal.completed || goal.done);
                      const text = typeof goal === 'string' ? goal : (goal.text || goal.title || goal.goal || goal.description);
                      return (
                        <div key={idx} className="flex items-start gap-2 text-xs">
                          {isDone ? (
                            <CheckCircle2 size={13} className="text-emerald-400 shrink-0 mt-0.5" />
                          ) : (
                            <Circle size={13} className="text-fantasy-accent shrink-0 mt-0.5" />
                          )}
                          <span className={isDone ? 'text-gray-500 line-through' : 'text-gray-200'}>
                            {cleanProseLocations(text)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Rolling Chapter Digest */}
              <div className="bg-black/40 border border-fantasy-border/60 rounded-lg p-3 space-y-2">
                <span className="text-[10px] font-bold text-purple-300 uppercase tracking-wider block">
                  📜 Chronicle Digest (Story So Far)
                </span>
                {chapterDigest.length === 0 ? (
                  <p className="text-xs text-gray-500 italic">Completed chapters and major turning points will be summarized here.</p>
                ) : (
                  <div className="space-y-1.5 max-h-60 overflow-y-auto custom-scrollbar pr-1">
                    {chapterDigest.map((entry, idx) => (
                      <div key={idx} className="text-[11px] text-gray-300 leading-snug bg-black/50 p-2 rounded border border-fantasy-border/30">
                        • {typeof entry === 'string' ? entry : (entry.summary || entry.text || entry.event)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      )}

    </div>
  );
};

export default QuestLogPanel;
