import { useState, useCallback, useEffect } from 'react';
import { apiCall } from '../api/client';

export const usePhone = (sessionId, user) => {
  const [phoneData, setPhoneData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeChatNpc, setActiveChatNpc] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [dailyLimits, setDailyLimits] = useState(null);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sendingChat, setSendingChat] = useState(false);

  const fetchPhoneState = useCallback(async () => {
    if (!sessionId || !user) return;
    try {
      setLoading(true);
      const data = await apiCall(`/api/phone/${sessionId}?user_id=${user.user_id}`);
      setPhoneData(data);
    } catch (err) {
      console.error("Failed to load phone state:", err);
    } finally {
      setLoading(false);
    }
  }, [sessionId, user]);

  useEffect(() => {
    fetchPhoneState();
  }, [fetchPhoneState]);

  const loadChatMessages = async (npcId) => {
    if (!sessionId || !npcId) return;
    setActiveChatNpc(npcId);
    setLoadingChat(true);
    try {
      const data = await apiCall(`/api/phone/${sessionId}/messages/${encodeURIComponent(npcId)}`);
      setChatMessages(data.messages || []);
      if (data.daily_limits) {
        setDailyLimits(data.daily_limits);
      }
    } catch (err) {
      console.error("Failed to fetch NPC chat messages:", err);
      setChatMessages([]);
    } finally {
      setLoadingChat(false);
    }
  };

  const sendMessage = async (npcId, messageText, intent = 'chat') => {
    const cleanText = (messageText || '__auto__').trim();
    if (!sessionId || !npcId || !user || !cleanText || sendingChat) return null;
    setSendingChat(true);
    try {
      const data = await apiCall(`/api/phone/${sessionId}/messages/${encodeURIComponent(npcId)}`, {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          message: cleanText,
          intent: intent || 'chat'
        })
      });
      if (data?.messages) {
        setChatMessages(data.messages);
      }
      if (data?.daily_limits) {
        setDailyLimits(data.daily_limits);
      } else if (data?.reply?.daily_limits) {
        setDailyLimits(data.reply.daily_limits);
      }
      await fetchPhoneState();
      return data;
    } catch (err) {
      console.error("Failed to send NPC message:", err);
      throw err;
    } finally {
      setSendingChat(false);
    }
  };

  const refreshFeed = async () => {
    if (!sessionId || !user) return null;
    const data = await apiCall(`/api/phone/${sessionId}/feed/refresh`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        force_refresh: true,
      }),
    });
    if (data) {
      setPhoneData(prev => ({
        ...(prev || {}),
        gossip_feed: data.gossip_feed || data.posts || prev?.gossip_feed || [],
        social_state: data.social_state || prev?.social_state,
      }));
    }
    return data;
  };

  const scourFeed = async () => {
    if (!sessionId || !user) return null;
    const data = await apiCall(`/api/phone/${sessionId}/feed/scour`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
      }),
    });
    if (data) {
      setPhoneData(prev => ({
        ...(prev || {}),
        social_state: data.social_state || prev?.social_state,
        gossip_feed: data.gossip_feed || prev?.gossip_feed || [],
      }));
    }
    return data;
  };

  const discoverPeer = async (queryName = '') => {
    if (!sessionId || !user) return null;
    return await apiCall(`/api/phone/${sessionId}/peerpulse/discover`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        query_name: queryName || null,
      }),
    });
  };

  const sendFriendRequest = async (profile) => {
    if (!sessionId || !user || !profile) return null;
    const data = await apiCall(`/api/phone/${sessionId}/peerpulse/friend-request`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        profile,
      }),
    });
    if (data?.accepted) {
      setPhoneData(prev => ({
        ...(prev || {}),
        contacts: data.contacts || prev?.contacts,
        suggested_peers: (prev?.suggested_peers || []).map(p =>
          (p.name === profile.name || p.handle === profile.handle)
            ? { ...p, is_already_contact: true }
            : p
        )
      }));
    } else if (data?.cooldown_turns) {
      setPhoneData(prev => ({
        ...(prev || {}),
        suggested_peers: (prev?.suggested_peers || []).map(p =>
          (p.name === profile.name || p.handle === profile.handle)
            ? { ...p, cooldown_turns_left: data.cooldown_turns }
            : p
        )
      }));
    } else if (data?.contacts) {
      setPhoneData(prev => ({
        ...(prev || {}),
        contacts: data.contacts,
      }));
    }
    return data;
  };

  const cancelCommitment = async (commitmentId, reason = 'player_cancelled') => {
    if (!sessionId || !commitmentId) return null;
    const data = await apiCall(`/api/commitments/${sessionId}/${commitmentId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        reason,
      }),
    });
    if (data) {
      setPhoneData(prev => ({
        ...(prev || {}),
        commitments: data.commitments || [],
        appointments: data.appointments || [],
      }));
    }
    return data;
  };

  return {
    phoneData,
    isSupported: true,
    branding: phoneData?.branding || {
      device_name: '📱 Smartphone',
      os_name: 'Mobile OS',
      gallery_app_name: 'Photos',
      dm_app_name: 'Messages',
      feed_app_name: 'Feed',
      emoji: '📱'
    },
    appointments: phoneData?.appointments || [],
    commitments: phoneData?.commitments || phoneData?.appointments || [],
    gossipFeed: phoneData?.gossip_feed || [],
    mediaGallery: phoneData?.media_gallery || [],
    contacts: phoneData?.contacts || [],
    dispatchChannels: phoneData?.dispatch_channels || [],
    suggestedPeers: phoneData?.suggested_peers || [],
    socialState: phoneData?.social_state || { charges: 3, turn_count: 0 },
    loading,
    refreshPhone: fetchPhoneState,
    refreshPhoneData: fetchPhoneState,
    refreshFeed,
    scourFeed,
    discoverPeer,
    sendFriendRequest,
    cancelCommitment,
    activeChatNpc,
    chatMessages,
    dailyLimits,
    loadingChat,
    sendingChat,
    loadChatMessages,
    sendMessage,
    closeChat: () => { setActiveChatNpc(null); setChatMessages([]); setDailyLimits(null); }
  };
};

