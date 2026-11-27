import { lazy, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Archive,
  ArrowRight,
  Award,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Coins,
  Compass,
  FileSearch,
  MapPin,
  ShieldAlert,
  Sparkles,
  Trash2,
  User,
} from 'lucide-react';
import {
  cleanProseLocations,
  formatCleanLocation,
  formatFullLocationPath,
} from '../../utils/locationFormat';
import { LazyMount } from '../Common/MotionPrimitives';
import {
  FogOfWarDossierSection,
  LegacySubObjectives,
  StructuredObjectives,
} from './quests/QuestObjectivesSection';
import BountiesTab from './quests/BountiesTab';
import CaseboardTab from './quests/CaseboardTab';
import CampaignTab from './quests/CampaignTab';
import ArchiveTab from './quests/ArchiveTab';
import { formatScenarioCurrency } from '../../utils/currency';

const ChronicleTapestryModal = lazy(() => import('../Modals/ChronicleTapestryModal'));

const QuestLogPanel = ({
  codexHook,
  onRefreshCharacter,
  character = null,
  session = null,
  playerProfile = null,
  scenario = null,
  onOpenWorldMap,
}) => {
  const { t } = useTranslation();
  const effScenario = scenario || session?.scenario || character?.scenario || 'fantasy';
  const {
    quests = [],
    availableBounties = [],
    activeStoryQuest,
    clues = [],
    noticeBoardLabel = 'Bounty Board',
    playerProfile: codexPlayerProfile = null,
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

  const isStudentOrigin = Boolean(
    (playerProfile || codexPlayerProfile || session?.player_profile)?.is_student
  );

  const [subTab, setSubTab] = useState('story'); // 'story' | 'bounties' | 'caseboard' | 'campaign' | 'history'
  const [bountyScopeFilter, setBountyScopeFilter] = useState('all'); // 'all' | 'generic' | 'faction' | 'school'
  const [historyFilter, setHistoryFilter] = useState('all'); // 'all' | 'Completed' | 'Failed' | 'Abandoned'
  const [busyAction, setBusyAction] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [isStoryExpanded, setIsStoryExpanded] = useState(true);
  const [expandedSideQuests, setExpandedSideQuests] = useState({});
  const [expandedBounties, setExpandedBounties] = useState({});
  const [tapestryModalOpen, setTapestryModalOpen] = useState(false);

  // Caseboard states
  const [selectedSuspect, setSelectedSuspect] = useState('__all__');
  const [clueAId, setClueAId] = useState('');
  const [clueBId, setClueBId] = useState('');

  useEffect(() => {
    setSelectedSuspect('__all__');
    setClueAId('');
    setClueBId('');
    setBountyScopeFilter('all');
    setFeedback(null);
  }, [session?.id]);

  const tabRefs = useRef({});

  const toggleSideQuest = (id) => {
    setExpandedSideQuests((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleBounty = (id) => {
    setExpandedBounties((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Group quests by type/status
  const sideQuests = (quests || []).filter((q) => {
    const qType = (q.quest_type || '').toLowerCase();
    const isStory =
      Boolean(q.is_story_quest) ||
      qType === 'story' ||
      qType === 'story quest' ||
      (activeStoryQuest && q.quest_id === activeStoryQuest.quest_id);
    return !isStory && q.status === 'Active';
  });

  const archivedQuests = (quests || []).filter((q) =>
    ['Completed', 'Failed', 'Abandoned'].includes(q.status)
  );

  // Sub-objectives / stages for active story quest
  const storyMainObjective =
    activeStoryQuest?.main_objective || activeStoryQuest?.fow_dossier?.main_objective || null;
  const storyOptionalObjectives = (
    activeStoryQuest?.optional_objectives ||
    activeStoryQuest?.fow_dossier?.optional_objectives ||
    []
  ).filter((o) => o && o.is_discovered !== false);
  const hasStructuredStory = Boolean(
    (activeStoryQuest?.has_structured_objectives ||
      activeStoryQuest?.fow_dossier?.has_structured_objectives) &&
      storyMainObjective
  );
  const completedStoryOptionals = storyOptionalObjectives.filter(
    (o) => o.completed || o.status === 'completed'
  ).length;
  const subObjectives = activeStoryQuest?.sub_objectives || activeStoryQuest?.stages || [];
  const completedSubs = subObjectives.filter((so) => so.completed || so.done).length;

  // Extract unique linked suspects from clues + compiled QuestDossier suspect pools
  const suspectPoolFromDossiers = [
    ...(activeStoryQuest?.fow_dossier?.suspect_pool || []),
    ...sideQuests.flatMap((q) => q?.fow_dossier?.suspect_pool || []),
  ];
  const suspects = Array.from(
    new Set([
      ...(clues || [])
        .map((c) => (typeof c === 'object' && c.linked_npc ? c.linked_npc.trim() : ''))
        .filter(Boolean),
      ...suspectPoolFromDossiers.map((s) => String(s || '').trim()).filter(Boolean),
    ])
  ).sort();

  const sidebarAvailableBounties = (availableBounties || []).filter((b) => {
    const isSchoolB = Boolean(b?.bounty_scope === 'school' || b?.is_school_bounty);
    if (!isStudentOrigin && isSchoolB) return false;
    const isFactionB = Boolean(
      b?.bounty_scope === 'faction' ||
        b?.faction_id ||
        b?.faction_name ||
        (b?.board_source && String(b.board_source).toLowerCase() !== 'general') ||
        String(b?.quest_id || '').startsWith('FBNT-')
    );
    if (bountyScopeFilter === 'school') return isSchoolB;
    if (bountyScopeFilter === 'generic') return !isSchoolB && !isFactionB;
    if (bountyScopeFilter === 'faction') return !isSchoolB && isFactionB;
    return true;
  });

  const handleGenerateBoard = async (forceRefresh = true) => {
    if (!generateBounties || busyAction) return;
    setBusyAction('generate_board');
    setFeedback(null);
    try {
      const boardScope = bountyScopeFilter !== 'all' ? bountyScopeFilter : null;
      await generateBounties(forceRefresh, null, boardScope);
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
          ? `Resolved (${disposition.replace('_', ' ')}) — +${formatScenarioCurrency(res.gold_awarded, effScenario)} awarded!`
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
      (q) => q?.quest_id && q?.fow_dossier?.dossier_stage === 'compiled'
    );
    const suspectClues = (clues || []).filter(
      (c) =>
        c?.linked_npc &&
        c.linked_npc.trim().toLowerCase() === selectedSuspect.toLowerCase() &&
        c.quest_id
    );
    const matchedQuestIds = new Set(suspectClues.map((c) => c.quest_id));
    let targetQuest = activeCompiledQuests.find((q) => matchedQuestIds.has(q.quest_id));
    if (!targetQuest) {
      targetQuest = activeCompiledQuests.find((q) =>
        (q.fow_dossier?.suspect_pool || []).some(
          (s) => String(s).toLowerCase() === selectedSuspect.toLowerCase()
        )
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
        type: res?.correct ? 'ok' : mode === 'formal' ? 'error' : 'warn',
        title: res?.correct
          ? 'Culprit Confirmed!'
          : mode === 'formal'
            ? 'False Public Accusation!'
            : 'Private Confrontation',
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
        text:
          choiceId === 'archive'
            ? 'Campaign archived to Hall of Legends!'
            : 'Endless Living World unlocked!',
      });
    } catch (err) {
      setFeedback({ type: 'error', text: err.message || 'Could not resolve epilogue.' });
    } finally {
      setBusyAction(null);
    }
  };

  const handleSynthesizeDeduction = async () => {
    if (!deduceClues || !clueAId || busyAction) return;
    setBusyAction('deduce');
    setFeedback(null);
    try {
      const res = await deduceClues(clueAId, clueBId || null);
      if (res?.is_valid) {
        if (res.partial_corroboration) {
          setFeedback({
            type: 'info',
            title: `🔎 ${res.title || t('quests.corroboration_confirmed', 'Trail Corroborated')}`,
            text:
              res.detail_text ||
              t(
                'quests.partial_corroboration_hint',
                'Both Key Clues align. Pair one with an Optional or Bonus Lead to unlock the Breakthrough.'
              ),
          });
        } else {
          setFeedback({
            type: 'ok',
            title: `⚡ ${res.title || 'Breakthrough Synthesized!'} (+${res.xp_awarded || 50} XP)`,
            text: res.detail_text,
          });
          setClueAId('');
          setClueBId('');
        }
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

  const questTabs = [
    {
      id: 'story',
      icon: Compass,
      label: t('quests.tab_active', 'Active'),
      fullLabel: t('quests.active', 'Active'),
    },
    {
      id: 'bounties',
      icon: ShieldAlert,
      label: t('quests.tab_bounties', 'Bounties'),
      fullLabel: t('quests.bounties', 'Side Bounties'),
      badge: availableBounties.length > 0 ? availableBounties.length : null,
      badgeTone: 'bg-amber-500/25 text-amber-200',
    },
    {
      id: 'caseboard',
      icon: FileSearch,
      label: t('quests.tab_caseboard', 'Caseboard'),
      fullLabel: t('quests.caseboard', 'Caseboard'),
      badge: clues.length > 0 ? clues.length : null,
      badgeTone: 'bg-cyan-500/25 text-cyan-200',
    },
    {
      id: 'campaign',
      icon: Award,
      label: t('quests.tab_campaign', 'Campaign'),
      fullLabel: t('quests.campaign', 'Campaign'),
    },
    {
      id: 'history',
      icon: Archive,
      label: t('quests.tab_archive', 'Archive'),
      fullLabel: t('quests.history_tab', 'Archive'),
    },
  ];

  const selectQuestTab = (tabId, focusTarget = false) => {
    setSubTab(tabId);
    setFeedback(null);
    const targetEl = tabRefs.current[tabId];
    if (targetEl) {
      if (focusTarget) targetEl.focus();
      targetEl.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
  };

  const handleTabKeyDown = (e, idx) => {
    let nextIdx = null;
    if (e.key === 'ArrowRight') nextIdx = (idx + 1) % questTabs.length;
    else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + questTabs.length) % questTabs.length;
    else if (e.key === 'Home') nextIdx = 0;
    else if (e.key === 'End') nextIdx = questTabs.length - 1;
    if (nextIdx !== null) {
      e.preventDefault();
      selectQuestTab(questTabs[nextIdx].id, true);
    }
  };

  return (
    <div className="flex flex-col gap-3 min-w-0">
      <LazyMount open={tapestryModalOpen}>
        <ChronicleTapestryModal
          isOpen={tapestryModalOpen}
          onClose={() => setTapestryModalOpen(false)}
          tapestry={campaignSpine?.chronicle_tapestry}
          epilogueReady={Boolean(campaignSpine?.epilogue_ready)}
          busyAction={busyAction}
          onChooseEpilogue={handleEpilogueDecision}
        />
      </LazyMount>

      {/* Header & Single-Row 5-Tab Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Compass size={16} className="text-fantasy-accent shrink-0" />
            <h3 className="font-rpg font-bold text-xs sm:text-sm text-gray-100 uppercase tracking-wider truncate">
              {t('quests.journal', 'Quest Journal')}
            </h3>
          </div>
          <span className="text-[10.5px] font-mono font-bold text-fantasy-accent bg-black/50 px-2 py-0.5 rounded-full border border-fantasy-border/70 shrink-0">
            {(activeStoryQuest ? 1 : 0) + sideQuests.length} {t('quests.active', 'Active')}
          </span>
        </div>

        <div
          role="tablist"
          aria-label={t('quests.journal', 'Quest Journal')}
          className="hk-quest-tabs"
        >
          {questTabs.map((tab, idx) => {
            const Icon = tab.icon;
            const isSelected = subTab === tab.id;
            return (
              <button
                key={tab.id}
                ref={(el) => {
                  tabRefs.current[tab.id] = el;
                }}
                type="button"
                role="tab"
                id={`quest-tab-${tab.id}`}
                aria-selected={isSelected}
                tabIndex={isSelected ? 0 : -1}
                onClick={() => selectQuestTab(tab.id, false)}
                onKeyDown={(e) => handleTabKeyDown(e, idx)}
                title={tab.fullLabel}
                className="hk-quest-tab"
              >
                <span className="relative inline-flex items-center justify-center">
                  <Icon size={14} className="shrink-0" />
                  {tab.badge && (
                    <span
                      className={`absolute -top-1.5 -right-2.5 min-w-[0.95rem] h-[0.95rem] px-1 rounded-full text-[9px] font-mono font-bold leading-[0.95rem] text-center ${tab.badgeTone}`}
                    >
                      {tab.badge}
                    </span>
                  )}
                </span>
                <span className="block max-w-full truncate">{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div
          className={`p-2.5 rounded-xl text-xs border space-y-1 ${
            feedback.type === 'error'
              ? 'bg-red-950/60 border-red-800/60 text-red-200'
              : feedback.type === 'warn'
                ? 'bg-amber-950/60 border-amber-700/60 text-amber-200'
                : feedback.type === 'info'
                  ? 'bg-sky-950/60 border-sky-700/60 text-sky-200'
                  : 'bg-emerald-950/60 border-emerald-700/60 text-emerald-200'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-bold">{feedback.title || (feedback.type === 'error' ? 'Alert' : 'Update')}</span>
            <button
              type="button"
              onClick={() => setFeedback(null)}
              className="text-[11px] opacity-75 hover:opacity-100 px-1"
              aria-label={t('common.close', 'Close')}
            >
              ✕
            </button>
          </div>
          <p className="text-[12px] leading-snug hk-quest-prose">{feedback.text}</p>
        </div>
      )}

      {loading && !activeStoryQuest && quests.length === 0 ? (
        <p className="text-xs text-gray-400 italic text-center py-8">
          {t('quests.loading_journal', 'Consulting journal...')}
        </p>
      ) : (
        <div role="tabpanel" aria-labelledby={`quest-tab-${subTab}`} className="space-y-3 min-w-0">
          {/* TAB 1: ACTIVE STORY & CONTRACTS */}
          {subTab === 'story' && (
            <>
              {activeStoryQuest ? (
                <div className="bg-gray-500/5 border border-fantasy-accent/35 rounded-xl overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setIsStoryExpanded((prev) => !prev)}
                    aria-expanded={isStoryExpanded}
                    className="w-full px-3 py-2.5 text-left flex justify-between items-start gap-2 group cursor-pointer"
                    title={isStoryExpanded ? 'Tap to collapse details' : 'Tap to expand details'}
                  >
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[10px] px-1.5 py-0.5 bg-fantasy-accent/20 text-fantasy-accent font-bold uppercase rounded border border-fantasy-accent/35 tracking-wider">
                          {t('quests.main_story_badge', 'Main Story')}
                        </span>
                        {(activeStoryQuest.chapter || currentChapter) && (
                          <span className="text-[10.5px] text-gray-300 font-mono">
                            {t('quests.chapter_n', {
                              chapter: activeStoryQuest.chapter || currentChapter,
                              defaultValue: `Chapter ${activeStoryQuest.chapter || currentChapter}`,
                            })}
                          </span>
                        )}
                        {activeStoryQuest.climax_ready && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-rose-950/80 text-rose-300 font-bold uppercase rounded border border-rose-600/60 animate-pulse">
                            🔥 {t('quests.climax_ready', 'Climax Ready!')}
                          </span>
                        )}
                        {(activeStoryQuest.is_peak_chapter || activeStoryQuest?.fow_dossier?.is_peak_chapter) && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-rose-950/75 text-rose-300 font-bold uppercase rounded border border-rose-600/50">
                            ⚡ {t('quests.peak_chapter', 'Peak Set-Piece')}
                          </span>
                        )}
                        {hasStructuredStory ? (
                          <>
                            <span className="text-[10px] font-mono text-fantasy-accent bg-black/50 px-1.5 py-0.5 rounded border border-fantasy-border/50">
                              ★{' '}
                              {storyMainObjective.completed
                                ? `✓ ${storyMainObjective.total_stages || 2}/${storyMainObjective.total_stages || 2}`
                                : `${t('quests.stage_label_short', 'Stage')} ${storyMainObjective.current_stage || 1}/${storyMainObjective.total_stages || 2}`}
                            </span>
                            {storyOptionalObjectives.length > 0 && (
                              <span className="text-[10px] font-mono text-cyan-300 bg-black/50 px-1.5 py-0.5 rounded border border-cyan-800/45">
                                {completedStoryOptionals}/{storyOptionalObjectives.length}{' '}
                                {t('quests.optional_short', 'Optional')}
                              </span>
                            )}
                          </>
                        ) : (
                          subObjectives.length > 0 && (
                            <span className="text-[10px] font-mono text-fantasy-accent bg-black/50 px-1.5 py-0.5 rounded border border-fantasy-border/50">
                              {completedSubs}/{subObjectives.length} {t('quests.completed_label', 'Completed')}
                            </span>
                          )
                        )}
                      </div>
                      <h4 className="font-rpg font-bold text-[14px] leading-snug text-gray-50 group-hover:text-fantasy-accent transition-colors">
                        {cleanProseLocations(activeStoryQuest.title || 'The Unfolding Journey')}
                      </h4>
                    </div>

                    <span className="p-1 rounded-md text-gray-400 group-hover:text-fantasy-accent transition-colors shrink-0 mt-0.5">
                      {isStoryExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </span>
                  </button>

                  {!isStoryExpanded && (
                    <button
                      type="button"
                      onClick={() => setIsStoryExpanded(true)}
                      className="w-full px-3 py-2 flex items-center justify-between text-[11.5px] text-gray-400 italic border-t border-white/[0.06] text-left cursor-pointer"
                    >
                      <span className="truncate">
                        {cleanProseLocations(
                          activeStoryQuest.objective || 'Tap to view objectives, locations, and rewards.'
                        )}
                      </span>
                      <span className="text-[10.5px] text-fantasy-accent not-italic font-semibold shrink-0 ml-2">
                        {t('quests.expand', 'Expand ▾')}
                      </span>
                    </button>
                  )}

                  {isStoryExpanded && (
                    <div>
                      {!hasStructuredStory && activeStoryQuest.objective && (
                        <p className="px-3 py-2.5 border-t border-white/[0.07] text-[12.5px] text-gray-200 leading-[1.5] hk-quest-prose">
                          {cleanProseLocations(activeStoryQuest.objective)}
                        </p>
                      )}

                      {activeStoryQuest.climax_ready &&
                        (activeStoryQuest.climax_location || activeStoryQuest.target_location) && (
                          <div className="border-t border-white/[0.07] border-l-2 border-l-rose-500 bg-rose-950/30 px-3 py-2 flex items-start justify-between gap-2 text-[12px] text-rose-100">
                            <div className="flex items-start gap-1.5 min-w-0 flex-1">
                              <MapPin size={13} className="shrink-0 text-rose-400 mt-0.5" />
                              <div className="min-w-0 leading-snug">
                                <span className="text-rose-200/90">
                                  {t('quests.final_showdown_location', '⚡ Final Showdown Location:')}
                                </span>{' '}
                                <strong className="break-words">
                                  {formatCleanLocation(
                                    activeStoryQuest.climax_location || activeStoryQuest.target_location
                                  )}
                                </strong>
                              </div>
                            </div>
                            {onOpenWorldMap &&
                              (activeStoryQuest.climax_location || activeStoryQuest.target_location) !==
                                'Hidden Lair' && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    onOpenWorldMap(
                                      activeStoryQuest.climax_location || activeStoryQuest.target_location
                                    )
                                  }
                                  className="px-2 py-0.5 rounded bg-rose-500/20 hover:bg-rose-500/35 text-rose-200 border border-rose-500/50 text-[10.5px] font-bold shrink-0 transition-colors"
                                >
                                  {t('quests.locate_btn', 'Map')}
                                </button>
                              )}
                          </div>
                        )}

                      {!activeStoryQuest.climax_ready &&
                        subObjectives.length === 0 &&
                        !hasStructuredStory &&
                        activeStoryQuest.target_location &&
                        activeStoryQuest.target_location !== 'Hidden Lair' && (
                          <div className="border-t border-white/[0.07] border-l-2 border-l-amber-400 bg-amber-950/20 px-3 py-2 flex items-start justify-between gap-2 text-[12px] text-amber-200">
                            <div className="flex items-start gap-1.5 min-w-0 flex-1">
                              <MapPin size={13} className="text-amber-400 shrink-0 mt-0.5" />
                              <div className="min-w-0 leading-snug">
                                <span className="text-amber-300/85">
                                  {String(t('quests.waypoint_lead', 'Waypoint Lead:')).replace(/^📍\s*/, '')}
                                </span>{' '}
                                <strong className="break-words">
                                  {formatCleanLocation(activeStoryQuest.target_location)}
                                </strong>
                              </div>
                            </div>
                            {onOpenWorldMap && (
                              <button
                                type="button"
                                onClick={() => onOpenWorldMap(activeStoryQuest.target_location)}
                                className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10.5px] font-bold shrink-0 transition-colors"
                              >
                                {t('quests.locate_btn', 'Map')}
                              </button>
                            )}
                          </div>
                        )}

                      {Boolean(
                        (activeStoryQuest.required_count ||
                          activeStoryQuest.required_item_count ||
                          activeStoryQuest.clues_required) > 0
                      ) && (
                        <div className="px-3 py-2 border-t border-white/[0.07] space-y-1">
                          <div className="flex justify-between text-[10.5px] font-mono text-gray-400">
                            <span>{t('quests.progress', 'Progress')}</span>
                            <span className="text-fantasy-accent font-bold">
                              {activeStoryQuest.current_count ?? activeStoryQuest.current_item_count ?? 0} /{' '}
                              {activeStoryQuest.required_count ||
                                activeStoryQuest.required_item_count ||
                                activeStoryQuest.clues_required}
                            </span>
                          </div>
                          <div className="h-1.5 w-full bg-black/70 rounded-full overflow-hidden border border-fantasy-border/40">
                            <div
                              className="h-full bg-fantasy-accent transition-all duration-300"
                              style={{
                                width: `${Math.min(
                                  100,
                                  ((activeStoryQuest.current_count ??
                                    activeStoryQuest.current_item_count ??
                                    0) /
                                    (activeStoryQuest.required_count ||
                                      activeStoryQuest.required_item_count ||
                                      activeStoryQuest.clues_required)) *
                                    100
                                )}%`,
                              }}
                            />
                          </div>
                        </div>
                      )}

                      {hasStructuredStory ? (
                        <StructuredObjectives
                          questObj={activeStoryQuest}
                          onOpenWorldMap={onOpenWorldMap}
                          scenario={effScenario}
                          t={t}
                          showStageBadge={false}
                        />
                      ) : (
                        <LegacySubObjectives
                          subObjectives={subObjectives}
                          onOpenWorldMap={onOpenWorldMap}
                          t={t}
                        />
                      )}

                      <FogOfWarDossierSection
                        questObj={activeStoryQuest}
                        allowTurnIn={false}
                        busyAction={busyAction}
                        onTurnIn={handleTurnIn}
                        scenario={effScenario}
                        t={t}
                      />

                      {(activeStoryQuest.reward_xp ||
                        activeStoryQuest.reward_gold ||
                        activeStoryQuest.reward_item) && (
                        <div className="px-3 py-2 border-t border-white/[0.07] bg-black/20 flex items-center gap-3 text-[11px] font-mono text-gray-300 flex-wrap">
                          <span className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">
                            {t('quests.rewards', 'Rewards:')}
                          </span>
                          {activeStoryQuest.reward_gold && (
                            <span className="flex items-center gap-1 text-amber-300 tabular-nums">
                              <Coins size={12} className="text-amber-400" />+{formatScenarioCurrency(activeStoryQuest.reward_gold, effScenario)}
                            </span>
                          )}
                          {activeStoryQuest.reward_xp && (
                            <span className="flex items-center gap-1 text-purple-300">
                              <Sparkles size={12} className="text-purple-400" />+{activeStoryQuest.reward_xp} XP
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-4 bg-black/25 rounded-xl border border-dashed border-fantasy-border text-center text-gray-400 text-xs italic">
                  {t('quests.no_quests', 'No active quests recorded.')}
                </div>
              )}

              {/* Active Side Bounties & Contracts */}
              {sideQuests.length > 0 && (
                <div className="space-y-2.5 pt-1">
                  <div className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5 px-0.5">
                    <ShieldAlert size={12} className="text-fantasy-accent" />
                    <span>
                      {t('quests.active_contracts_header', {
                        count: sideQuests.length,
                        defaultValue: `Active Contracts & Bounties (${sideQuests.length})`,
                      })}
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    {sideQuests.map((q, idx) => {
                      const qId = q.quest_id || `side-${idx}`;
                      const isExpanded = expandedSideQuests[qId] ?? false;
                      const qStages = q.stages || q.sub_objectives || [];
                      const qStructured = Boolean(
                        (q.has_structured_objectives || q.fow_dossier?.has_structured_objectives) &&
                          (q.main_objective || q.fow_dossier?.main_objective)
                      );

                      return (
                        <div
                          key={qId}
                          className="bg-gray-500/5 border border-fantasy-border/35 hover:border-fantasy-border/60 rounded-xl overflow-hidden transition-colors"
                        >
                          <button
                            type="button"
                            onClick={() => toggleSideQuest(qId)}
                            aria-expanded={isExpanded}
                            className="w-full px-3 py-2.5 flex justify-between items-start gap-2 text-left cursor-pointer group"
                            title={
                              isExpanded ? t('quests.collapse', 'Collapse ▴') : t('quests.expand', 'Expand ▾')
                            }
                          >
                            <div className="min-w-0 flex-1 space-y-1">
                              <h5 className="font-semibold text-[13px] leading-snug text-gray-100 flex items-center gap-1.5 flex-wrap group-hover:text-fantasy-accent transition-colors">
                                <span>{cleanProseLocations(q.title)}</span>
                                {q.climax_ready && (
                                  <span className="text-[9.5px] px-1.5 py-0.5 bg-rose-950/80 text-rose-300 rounded font-bold uppercase border border-rose-600/60">
                                    🔥 {t('quests.climax_ready', 'Climax Ready!')}
                                  </span>
                                )}
                              </h5>
                              {!isExpanded && (
                                <p className="text-[11px] text-gray-400 truncate">
                                  {cleanProseLocations(q.stage_label) ||
                                    (q.target_location
                                      ? formatCleanLocation(q.target_location)
                                      : cleanProseLocations(
                                          q.objective || q.description || t('quests.expand', 'Expand ▾')
                                        ))}
                                </p>
                              )}
                            </div>
                            <div className="flex items-center gap-1 shrink-0 mt-0.5">
                              <span className="text-[9.5px] px-1.5 py-0.5 bg-amber-950/60 text-amber-300 rounded font-bold uppercase border border-amber-800/45">
                                {q.quest_type || t('quests.bounty_fallback', 'Bounty')}
                              </span>
                              <span className="text-gray-400 group-hover:text-fantasy-accent">
                                {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                              </span>
                            </div>
                          </button>

                          {isExpanded && (
                            <div className="border-t border-white/[0.06]">
                              {(q.objective || q.description) && (
                                <p className="px-3 py-2.5 text-[12px] text-gray-200 leading-[1.45] hk-quest-prose">
                                  {cleanProseLocations(q.objective || q.description)}
                                </p>
                              )}

                              {!qStructured &&
                                (q.target_location || q.stage_label || q.target_npc) && (
                                  <div className="border-t border-white/[0.06] border-l-2 border-l-fantasy-accent bg-fantasy-accent/[0.06] px-3 py-2 space-y-1.5">
                                    {q.stage_label && (
                                      <div className="text-[12px] text-gray-100 font-semibold leading-snug hk-quest-prose">
                                        {cleanProseLocations(q.stage_label)}
                                      </div>
                                    )}
                                    {q.target_location && q.target_location !== 'Hidden Lair' && (
                                      <div className="flex items-start justify-between gap-2">
                                        <div
                                          className="flex items-start gap-1.5 text-[11.5px] text-amber-200 min-w-0 flex-1"
                                          title={formatFullLocationPath(q.target_location)}
                                        >
                                          <MapPin size={12} className="text-amber-400 shrink-0 mt-0.5" />
                                          <span className="break-words">
                                            <strong>{formatCleanLocation(q.target_location)}</strong>
                                          </span>
                                        </div>
                                        {onOpenWorldMap && (
                                          <button
                                            type="button"
                                            onClick={() => onOpenWorldMap(q.target_location)}
                                            className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/35 text-amber-200 border border-amber-500/50 text-[10px] font-bold shrink-0 transition-colors"
                                          >
                                            {t('quests.locate_btn', 'Map')}
                                          </button>
                                        )}
                                      </div>
                                    )}
                                    {q.target_npc && (
                                      <div className="flex items-center gap-1.5 text-[11px] text-cyan-200">
                                        <User size={12} className="text-cyan-400 shrink-0" />
                                        <span>
                                          {String(t('quests.key_contact', 'Key Contact:')).replace(/^👤\s*/, '')}{' '}
                                          <strong>{q.target_npc}</strong>
                                        </span>
                                      </div>
                                    )}
                                  </div>
                                )}

                              {Boolean(
                                (q.required_count || q.required_item_count || q.clues_required) > 0
                              ) && (
                                <div className="px-3 py-2 border-t border-white/[0.06] flex items-center justify-between text-[11px] font-mono text-gray-300">
                                  <span>{t('quests.checklist_progress', 'Checklist Progress')}</span>
                                  <span className="text-fantasy-accent font-bold">
                                    {q.current_count ?? q.current_item_count ?? 0} /{' '}
                                    {q.required_count || q.required_item_count || q.clues_required}
                                  </span>
                                </div>
                              )}

                              {qStructured ? (
                                <StructuredObjectives
                                  questObj={q}
                                  onOpenWorldMap={onOpenWorldMap}
                                  scenario={effScenario}
                                  t={t}
                                  showStageBadge={true}
                                />
                              ) : (
                                qStages.length > 0 && (
                                  <div className="px-3 py-2 border-t border-white/[0.06] space-y-1.5">
                                    {qStages.map((st, sIdx) => {
                                      const done = Boolean(
                                        st.completed || st.done || st.status === 'completed'
                                      );
                                      const isActive = st.status === 'active';
                                      const stLoc = typeof st === 'object' ? st.target_location : '';
                                      const stNpc = typeof st === 'object' ? st.target_npc : '';
                                      return (
                                        <div key={sIdx} className="flex items-start gap-1.5 text-[11.5px]">
                                          {done ? (
                                            <CheckCircle2
                                              size={12}
                                              className="text-emerald-400 shrink-0 mt-0.5"
                                            />
                                          ) : (
                                            <Circle
                                              size={12}
                                              className={`${
                                                isActive ? 'text-amber-400' : 'text-gray-500'
                                              } shrink-0 mt-0.5`}
                                            />
                                          )}
                                          <div className="min-w-0 flex-1">
                                            <span
                                              className={
                                                done
                                                  ? 'text-gray-500 line-through hk-quest-prose'
                                                  : isActive
                                                    ? 'text-amber-200 font-semibold hk-quest-prose'
                                                    : 'text-gray-300 hk-quest-prose'
                                              }
                                            >
                                              {cleanProseLocations(
                                                typeof st === 'string'
                                                  ? st
                                                  : st.text || st.stage_label || st.label || st.title
                                              )}
                                            </span>
                                            {stLoc && !done && (
                                              <span
                                                className={`block text-[10.5px] break-words ${
                                                  isActive ? 'text-amber-300/90' : 'text-gray-400'
                                                }`}
                                              >
                                                {formatCleanLocation(stLoc)}
                                                {stNpc ? ` · ${stNpc}` : ''}
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                )
                              )}

                              <FogOfWarDossierSection
                                questObj={q}
                                allowTurnIn={true}
                                busyAction={busyAction}
                                onTurnIn={handleTurnIn}
                                scenario={effScenario}
                                t={t}
                              />

                              <div className="px-3 py-2 border-t border-white/[0.06] bg-black/20 flex items-center justify-between gap-2">
                                <div className="flex items-center gap-2.5 text-[11px] font-mono tabular-nums text-gray-400">
                                  {q.reward_gold ? (
                                    <span className="text-amber-300">
                                      +{formatScenarioCurrency(q.reward_gold, effScenario)}
                                    </span>
                                  ) : null}
                                  {q.reward_xp ? (
                                    <span className="text-purple-300">+{q.reward_xp} XP</span>
                                  ) : null}
                                </div>
                                {q.quest_id && (
                                  <button
                                    type="button"
                                    disabled={Boolean(busyAction)}
                                    onClick={() => handleBountyContract(q.quest_id, 'abandon')}
                                    className="flex items-center gap-1 px-2 py-0.5 rounded bg-red-950/40 hover:bg-red-900/50 text-red-300 border border-red-800/50 text-[10.5px] font-bold transition-colors"
                                  >
                                    <Trash2 size={10} />
                                    <span>{t('quests.abandon', 'Abandon')}</span>
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

              {/* Compact Archive Jump Row */}
              {archivedQuests.length > 0 && (
                <button
                  type="button"
                  onClick={() => selectQuestTab('history', false)}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-black/25 hover:bg-black/40 border border-fantasy-border/45 text-xs text-gray-300 hover:text-fantasy-accent transition-colors"
                >
                  <span className="flex items-center gap-1.5 font-semibold">
                    <Award size={14} className="text-emerald-400 shrink-0" />
                    <span>
                      {t('quests.history_tab', 'Archive')} ({archivedQuests.length})
                    </span>
                  </span>
                  <ArrowRight size={14} className="shrink-0" />
                </button>
              )}
            </>
          )}

          {/* TAB 2: BOUNTIES */}
          {subTab === 'bounties' && (
            <BountiesTab
              noticeBoardLabel={noticeBoardLabel}
              availableBounties={sidebarAvailableBounties}
              expandedBounties={expandedBounties}
              onToggleBounty={toggleBounty}
              onGenerateBoard={handleGenerateBoard}
              onBountyContract={handleBountyContract}
              bountyScopeFilter={bountyScopeFilter}
              onChangeBountyScopeFilter={setBountyScopeFilter}
              isStudentOrigin={isStudentOrigin}
              busyAction={busyAction}
              scenario={effScenario}
              t={t}
            />
          )}

          {/* TAB 3: CASEBOARD */}
          {subTab === 'caseboard' && (
            <CaseboardTab
              clues={clues}
              suspects={suspects}
              selectedSuspect={selectedSuspect}
              onSelectSuspect={setSelectedSuspect}
              clueAId={clueAId}
              setClueAId={setClueAId}
              clueBId={clueBId}
              setClueBId={setClueBId}
              onSynthesizeDeduction={handleSynthesizeDeduction}
              onAccuseSuspect={handleAccuseSuspect}
              busyAction={busyAction}
              t={t}
            />
          )}

          {/* TAB 4: CAMPAIGN */}
          {subTab === 'campaign' && (
            <CampaignTab
              currentChapter={currentChapter}
              maxChapters={maxChapters}
              campaignSpine={campaignSpine}
              campaignEndGoals={campaignEndGoals}
              chapterDigest={chapterDigest}
              busyAction={busyAction}
              onOpenTapestry={() => setTapestryModalOpen(true)}
              onChooseEpilogue={handleEpilogueDecision}
              t={t}
            />
          )}

          {/* TAB 5: ARCHIVE */}
          {subTab === 'history' && (
            <ArchiveTab
              archivedQuests={archivedQuests}
              chapterDigest={chapterDigest}
              historyFilter={historyFilter}
              onChangeFilter={setHistoryFilter}
              t={t}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default QuestLogPanel;
