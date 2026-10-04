import { useState, useCallback, useEffect } from 'react';
import { apiCall } from '../api/client';

export const useCodex = (sessionId, user) => {
  const [contacts, setContacts] = useState([]);
  const [factions, setFactions] = useState([]);
  const [factionMembership, setFactionMembership] = useState({ joined_faction_id: '', faction_rank: 0, faction_title: '' });
  const [lorebook, setLorebook] = useState({ categories: {}, entities: [] });
  const [commitments, setCommitments] = useState([]);
  const [quests, setQuests] = useState([]);
  const [availableBounties, setAvailableBounties] = useState([]);
  const [activeStoryQuest, setActiveStoryQuest] = useState(null);
  const [clues, setClues] = useState([]);
  const [currentChapter, setCurrentChapter] = useState(1);
  const [campaignEndGoals, setCampaignEndGoals] = useState([]);
  const [chapterDigest, setChapterDigest] = useState([]);
  const [hasBountyBoard, setHasBountyBoard] = useState(false);
  const [noticeBoardLabel, setNoticeBoardLabel] = useState('Bounty Board');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchCodexData = useCallback(async () => {
    if (!sessionId || !user) return;
    try {
      setLoading(true);
      setError(null);

      const [contactsRes, factionsRes, lorebookRes, questsRes] = await Promise.allSettled([
        apiCall(`/api/contacts/${sessionId}?user_id=${user.user_id}`),
        apiCall(`/api/factions/${sessionId}?user_id=${user.user_id}`),
        apiCall(`/api/lorebook/${sessionId}`),
        apiCall(`/api/quests/${sessionId}`)
      ]);

      if (contactsRes.status === 'fulfilled') {
        setContacts(contactsRes.value.contacts || []);
      }
      if (factionsRes.status === 'fulfilled') {
        const fData = factionsRes.value || {};
        setFactions(fData.factions || []);
        if (fData.membership) {
          setFactionMembership(fData.membership);
        }
      }
      if (lorebookRes.status === 'fulfilled') {
        const loreVal = lorebookRes.value || { categories: {}, entities: [] };
        setLorebook(loreVal);
        setCommitments(loreVal.commitments || []);
      }
      if (questsRes.status === 'fulfilled') {
        const qData = questsRes.value || {};
        setQuests(qData.quests || []);
        setAvailableBounties(qData.available_bounties || []);
        setActiveStoryQuest(qData.active_story_quest || null);
        setClues(qData.clues || []);
        setCurrentChapter(qData.current_chapter || 1);
        setCampaignEndGoals(qData.campaign_end_goals || []);
        setChapterDigest(qData.chapter_digest || []);
        setHasBountyBoard(Boolean(qData.has_bounty_board));
        if (qData.notice_board_label) {
          setNoticeBoardLabel(qData.notice_board_label);
        }
      }
    } catch (err) {
      console.error("Failed to load codex data:", err);
      setError(err.message || "Failed to load codex data");
    } finally {
      setLoading(false);
    }
  }, [sessionId, user]);

  useEffect(() => {
    fetchCodexData();
  }, [fetchCodexData]);

  const factionHqAction = async (factionId, action) => {
    if (!sessionId || !user?.user_id) return null;
    const data = await apiCall(`/api/factions/${sessionId}/hq-action`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        faction_id: factionId,
        action,
      }),
    });
    if (data?.factions) setFactions(data.factions);
    if (data?.membership) setFactionMembership(data.membership);
    return data;
  };

  const generateBounties = async (forceRefresh = false) => {
    if (!sessionId) return null;
    const data = await apiCall(`/api/quests/${sessionId}/bounties/generate`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        force_refresh: forceRefresh,
      }),
    });
    if (data?.quests) setQuests(data.quests);
    if (data?.available_bounties) setAvailableBounties(data.available_bounties);
    return data;
  };

  const bountyAction = async (questId, action = 'accept') => {
    if (!sessionId || !questId) return null;
    const data = await apiCall(`/api/quests/${sessionId}/bounties/action`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        quest_id: questId,
        action,
      }),
    });
    if (data?.quests) setQuests(data.quests);
    if (data?.available_bounties) setAvailableBounties(data.available_bounties);
    return data;
  };

  const deduceClues = async (clueAId, clueBId) => {
    if (!sessionId || !clueAId || !clueBId) return null;
    const data = await apiCall(`/api/quests/${sessionId}/clues/deduce`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        clue_a_id: Number(clueAId),
        clue_b_id: Number(clueBId),
      }),
    });
    if (data?.clues) setClues(data.clues);
    return data;
  };

  return {
    contacts,
    factions,
    factionMembership,
    lorebook,
    commitments,
    quests,
    availableBounties,
    activeStoryQuest,
    clues,
    currentChapter,
    campaignEndGoals,
    chapterDigest,
    hasBountyBoard,
    noticeBoardLabel,
    loading,
    error,
    refreshCodex: fetchCodexData,
    factionHqAction,
    generateBounties,
    bountyAction,
    deduceClues,
  };
};

