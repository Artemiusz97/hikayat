import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { apiCall } from '../api/client';
import { isValidSessionId, isAnomalousScenarioKey } from '../utils/session';

export const useCodex = (sessionId, user, session = null, onSessionRefresh = null) => {
  const [contacts, setContacts] = useState([]);
  const [acquaintances, setAcquaintances] = useState([]);
  const [factions, setFactions] = useState([]);
  const [agentDossier, setAgentDossier] = useState(null);
  const [lorebook, setLorebook] = useState({ categories: {}, entities: [] });
  const [worldPulse, setWorldPulse] = useState(null);
  const [commitments, setCommitments] = useState([]);
  const [quests, setQuests] = useState([]);
  const [availableBounties, setAvailableBounties] = useState([]);
  const [activeStoryQuest, setActiveStoryQuest] = useState(null);
  const [clues, setClues] = useState([]);
  const [currentChapter, setCurrentChapter] = useState(1);
  const [maxChapters, setMaxChapters] = useState(11);
  const [campaignSpine, setCampaignSpine] = useState(null);
  const [campaignEndGoals, setCampaignEndGoals] = useState([]);
  const [chapterDigest, setChapterDigest] = useState([]);
  const [noticeBoardLabel, setNoticeBoardLabel] = useState('Bounty Board');
  const [encyclopedia, setEncyclopedia] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const { i18n } = useTranslation();
  const activeUiLang = (i18n.resolvedLanguage || i18n.language || 'en').slice(0, 2);
  const isAnomalousScenario = isAnomalousScenarioKey(session?.scenario);

  const fetchSeqRef = useRef(0);
  const abortRef = useRef(null);

  const fetchCodexData = useCallback(async () => {
    if (!isValidSessionId(sessionId) || !user) {
      if (!isValidSessionId(sessionId)) {
        setContacts([]);
        setAcquaintances([]);
      }
      setLoading(false);
      return;
    }
    const seq = ++fetchSeqRef.current;
    if (abortRef.current) {
      try {
        abortRef.current.abort();
      } catch {}
    }
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      setLoading(true);
      setError(null);

      const reqOpts = { signal: controller.signal };
      const requests = [
        apiCall(`/api/contacts/${sessionId}?user_id=${user.user_id}`, reqOpts),
        apiCall(`/api/factions/${sessionId}?user_id=${user.user_id}`, reqOpts),
        apiCall(`/api/lorebook/${sessionId}?user_id=${user.user_id}`, reqOpts),
        apiCall(`/api/quests/${sessionId}?user_id=${user.user_id}`, reqOpts),
      ];
      if (isAnomalousScenario) {
        requests.push(apiCall(`/api/codex/encyclopedia?session_id=${sessionId}&user_id=${user.user_id}&lang=${encodeURIComponent(activeUiLang)}`, reqOpts));
      }

      const [contactsRes, factionsRes, lorebookRes, questsRes, encyclopediaRes] = await Promise.allSettled(requests);
      if (fetchSeqRef.current !== seq || controller.signal.aborted) {
        return;
      }

      if (contactsRes.status === 'fulfilled') {
        const contactsData = contactsRes.value || {};
        setContacts(contactsData.contacts || []);
        if (contactsData?.acquaintances) {
          setAcquaintances(contactsData.acquaintances);
        } else {
          setAcquaintances([]);
        }
      }
      if (factionsRes.status === 'fulfilled') {
        const fData = factionsRes.value || {};
        setFactions(fData.factions || []);
        setAgentDossier(fData.agent_dossier || null);
      }
      if (lorebookRes.status === 'fulfilled') {
        const loreVal = lorebookRes.value || { categories: {}, entities: [] };
        setLorebook(loreVal);
        setCommitments(loreVal.commitments || []);
        if (loreVal.world_pulse) {
          setWorldPulse(loreVal.world_pulse);
        }
      }
      if (questsRes.status === 'fulfilled') {
        const qData = questsRes.value || {};
        setQuests(qData.quests || []);
        setAvailableBounties(qData.available_bounties || []);
        setActiveStoryQuest(qData.active_story_quest || null);
        setClues(qData.clues || []);
        setCurrentChapter(qData.current_chapter || 1);
        setMaxChapters(qData.max_chapters || 11);
        setCampaignSpine(qData.campaign_spine || null);
        setCampaignEndGoals(qData.campaign_end_goals || []);
        setChapterDigest(qData.chapter_digest || []);
        if (qData.notice_board_label) {
          setNoticeBoardLabel(qData.notice_board_label);
        }
      }
      if (encyclopediaRes && encyclopediaRes.status === 'fulfilled') {
        setEncyclopedia(encyclopediaRes.value || null);
      } else if (!isAnomalousScenario) {
        setEncyclopedia(null);
      }
    } catch (err) {
      if (controller.signal.aborted || fetchSeqRef.current !== seq) return;
      console.error("Failed to load codex data:", err);
      setError(err.message || "Failed to load codex data");
    } finally {
      if (fetchSeqRef.current === seq) {
        setLoading(false);
      }
    }
  }, [sessionId, user, isAnomalousScenario, activeUiLang]);

  useEffect(() => {
    fetchCodexData();
    return () => {
      if (abortRef.current) {
        try {
          abortRef.current.abort();
        } catch {}
      }
    };
  }, [fetchCodexData]);

  useEffect(() => {
    if (session?.world_pulse) {
      setWorldPulse(session.world_pulse);
    }
  }, [session?.world_pulse]);

  const factionHqAction = async (factionId, action, extraPayload = {}) => {
    if (!isValidSessionId(sessionId) || !user?.user_id) return null;
    const data = await apiCall(`/api/factions/${sessionId}/hq-action`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        faction_id: factionId,
        action,
        ...extraPayload,
      }),
    });
    if (data?.factions) setFactions(data.factions);
    if (data?.agent_dossier) setAgentDossier(data.agent_dossier);
    return data;
  };

  const generateBounties = async (forceRefresh = false, factionId = null) => {
    if (!isValidSessionId(sessionId)) return null;
    const data = await apiCall(`/api/quests/${sessionId}/bounties/generate`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        force_refresh: forceRefresh,
        faction_id: factionId || undefined,
      }),
    });
    syncQuestPayload(data);
    return data;
  };

  const syncQuestPayload = (data) => {
    if (!data) return;
    if (data.quests) setQuests(data.quests);
    if (data.available_bounties) setAvailableBounties(data.available_bounties);
    if ('active_story_quest' in data) setActiveStoryQuest(data.active_story_quest || null);
    if (data.clues) setClues(data.clues);
    if (data.current_chapter) setCurrentChapter(data.current_chapter);
    if (data.max_chapters) setMaxChapters(data.max_chapters);
    if (data.campaign_spine) setCampaignSpine(data.campaign_spine);
    if (data.chapter_digest) setChapterDigest(data.chapter_digest);
    if (data.campaign_end_goals) setCampaignEndGoals(data.campaign_end_goals);
    if (data.notice_board_label) setNoticeBoardLabel(data.notice_board_label);
  };

  const bountyAction = async (questId, action = 'accept', haggleAdvance = false) => {
    if (!isValidSessionId(sessionId) || !questId) return null;
    const data = await apiCall(`/api/quests/${sessionId}/bounties/action`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        quest_id: questId,
        action,
        haggle_advance: Boolean(haggleAdvance),
      }),
    });
    syncQuestPayload(data);
    return data;
  };

  const refreshEncyclopediaIfActive = useCallback(async () => {
    if (!isAnomalousScenario || !isValidSessionId(sessionId) || !user?.user_id) return;
    try {
      const encData = await apiCall(`/api/codex/encyclopedia?session_id=${sessionId}&user_id=${user.user_id}&lang=${encodeURIComponent(activeUiLang)}`);
      if (encData) setEncyclopedia(encData);
    } catch {
      // Non-fatal background refresh
    }
  }, [isAnomalousScenario, sessionId, user?.user_id, activeUiLang]);

  const deduceClues = async (clueAId, clueBId = null) => {
    if (!isValidSessionId(sessionId) || !clueAId) return null;
    const body = {
      user_id: user?.user_id,
      clue_a_id: Number(clueAId),
    };
    if (clueBId !== null && clueBId !== undefined && clueBId !== '') {
      body.clue_b_id = Number(clueBId);
    }
    const data = await apiCall(`/api/quests/${sessionId}/clues/deduce`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    syncQuestPayload(data);
    await refreshEncyclopediaIfActive();
    await onSessionRefresh?.();
    return data;
  };

  const accuseSuspect = async (questId, suspectName, mode = 'private') => {
    if (!isValidSessionId(sessionId) || !questId || !suspectName) return null;
    const data = await apiCall(`/api/quests/${sessionId}/caseboard/accuse`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        quest_id: questId,
        suspect_name: suspectName,
        mode,
      }),
    });
    syncQuestPayload(data);
    await onSessionRefresh?.();
    return data;
  };

  const turnInQuest = async (questId, disposition = 'deliver') => {
    if (!isValidSessionId(sessionId) || !questId || !user?.user_id) return null;
    const data = await apiCall(`/api/quests/${sessionId}/turn-in`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        quest_id: questId,
        disposition,
      }),
    });
    syncQuestPayload(data);
    await refreshEncyclopediaIfActive();
    await onSessionRefresh?.();
    return data;
  };

  const chooseEpilogue = async (choiceId = 'endless') => {
    if (!isValidSessionId(sessionId)) return null;
    const data = await apiCall(`/api/quests/${sessionId}/epilogue`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        choice_id: choiceId,
      }),
    });
    syncQuestPayload(data);
    await onSessionRefresh?.();
    return data;
  };

  const cancelCommitment = async (commitmentId, reason = 'player_cancelled') => {
    if (!isValidSessionId(sessionId) || !commitmentId) return null;
    const data = await apiCall(`/api/commitments/${sessionId}/${commitmentId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        reason,
      }),
    });
    if (data?.commitments) {
      setCommitments(data.commitments);
    } else {
      setCommitments(prev => prev.filter(c => (c.commitment_id || c.id) !== commitmentId));
    }
    return data;
  };

  const trackRumor = async (eventKey) => {
    if (!isValidSessionId(sessionId) || !eventKey) return null;
    const data = await apiCall(`/api/adventure/${sessionId}/rumors/${encodeURIComponent(eventKey)}/track`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
      }),
    });
    if (data?.world_pulse) {
      setWorldPulse(data.world_pulse);
    }
    if (Array.isArray(data?.quests)) {
      setQuests(data.quests);
    }
    return data;
  };

  return {
    contacts,
    acquaintances,
    factions,
    agentDossier,
    lorebook,
    worldPulse,
    commitments,
    quests,
    availableBounties,
    activeStoryQuest,
    clues,
    currentChapter,
    maxChapters,
    campaignSpine,
    campaignEndGoals,
    chapterDigest,
    noticeBoardLabel,
    encyclopedia,
    loading,
    error,
    refreshCodex: fetchCodexData,
    factionHqAction,
    generateBounties,
    bountyAction,
    deduceClues,
    accuseSuspect,
    turnInQuest,
    chooseEpilogue,
    cancelCommitment,
    trackRumor,
  };
};
