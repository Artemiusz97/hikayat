import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../api/client';
import { isValidSessionId } from '../utils/session';

export const usePhone = (sessionId, user) => {
  const [phoneData, setPhoneData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeChatNpc, setActiveChatNpc] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [dailyLimits, setDailyLimits] = useState(null);
  const [loadingChat, setLoadingChat] = useState(false);
  const [sendingChat, setSendingChat] = useState(false);
  const chatSeqRef = useRef(0);
  const chatAbortRef = useRef(null);
  const stateSeqRef = useRef(0);
  const stateAbortRef = useRef(null);
  const activeSessionIdRef = useRef(sessionId);
  activeSessionIdRef.current = sessionId;
  const pendingMediaEventsRef = useRef(new Map());
  const wsEventSeqRef = useRef(0);
  const mediaWsStateRef = useRef(new Map());

  const mergeGalleryMonotonic = (prevGallery = [], nextGallery = [], fetchStartWsSeq = 0) => {
    const pendingMap = pendingMediaEventsRef.current;
    const wsStateMap = mediaWsStateRef.current;
    const prevById = new Map();
    for (const pm of prevGallery || []) {
      if (pm?.id != null) prevById.set(String(pm.id), pm);
    }
    return (nextGallery || []).map((inc) => {
      if (!inc || inc.id == null) return inc;
      const key = String(inc.id);
      const prevItem = prevById.get(key);
      const pending = pendingMap.get(key);
      const wsSnap = wsStateMap.get(key);
      if (pending) {
        pendingMap.delete(key);
      }

      if (wsSnap && wsSnap.seq > fetchStartWsSeq) {
        if (wsSnap.image_status === 'ready' && wsSnap.image_url) {
          return {
            ...inc,
            image_url: wsSnap.image_url,
            image_status: 'ready',
          };
        }
        if (wsSnap.image_status === 'error') {
          return {
            ...inc,
            image_url: wsSnap.image_url || inc.image_url || '',
            image_status: 'error',
          };
        }
        if (wsSnap.image_status === 'generating' && inc.image_status !== 'ready') {
          return {
            ...inc,
            image_status: 'generating',
          };
        }
      }

      if (pending) {
        if (pending.image_status === 'ready' && pending.image_url) {
          return {
            ...inc,
            image_url: pending.image_url,
            image_status: 'ready',
          };
        }
        if (pending.image_url && !inc.image_url) {
          return {
            ...inc,
            image_url: pending.image_url,
            image_status: pending.image_status || 'ready',
          };
        }
        if (pending.image_status === 'error' && inc.image_status === 'generating') {
          return {
            ...inc,
            image_status: 'error',
          };
        }
      }

      if (prevItem?.image_url && !inc.image_url) {
        return {
          ...inc,
          image_url: prevItem.image_url,
          image_status: prevItem.image_status || 'ready',
        };
      }
      if (prevItem?.image_status === 'error' && inc.image_status === 'generating' && !inc.image_url) {
        return {
          ...inc,
          image_status: 'error',
        };
      }
      return inc;
    });
  };

  const fetchPhoneState = useCallback(async () => {
    if (!isValidSessionId(sessionId) || !user) {
      stateSeqRef.current += 1;
      if (stateAbortRef.current) {
        try {
          stateAbortRef.current.abort();
        } catch {}
        stateAbortRef.current = null;
      }
      setPhoneData(null);
      setLoading(false);
      return;
    }
    if (stateAbortRef.current) {
      try {
        stateAbortRef.current.abort();
      } catch {}
    }
    const seq = ++stateSeqRef.current;
    const fetchStartWsSeq = wsEventSeqRef.current;
    const controller = new AbortController();
    stateAbortRef.current = controller;
    try {
      setLoading(true);
      const data = await apiCall(`/api/phone/${sessionId}?user_id=${user.user_id}`, {
        signal: controller.signal,
      });
      if (seq !== stateSeqRef.current) return;
      setPhoneData((prev) => ({
        ...data,
        media_gallery: mergeGalleryMonotonic(prev?.media_gallery, data?.media_gallery, fetchStartWsSeq),
      }));
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || seq !== stateSeqRef.current) return;
      console.error("Failed to load phone state:", err);
    } finally {
      if (seq === stateSeqRef.current) {
        setLoading(false);
        if (stateAbortRef.current === controller) {
          stateAbortRef.current = null;
        }
      }
    }
  }, [sessionId, user]);

  useEffect(() => {
    fetchPhoneState();
    return () => {
      stateSeqRef.current += 1;
      if (stateAbortRef.current) {
        try {
          stateAbortRef.current.abort();
        } catch {}
        stateAbortRef.current = null;
      }
    };
  }, [fetchPhoneState]);

  useEffect(() => {
    chatSeqRef.current += 1;
    if (chatAbortRef.current) {
      try {
        chatAbortRef.current.abort();
      } catch {}
      chatAbortRef.current = null;
    }
    pendingMediaEventsRef.current.clear();
    mediaWsStateRef.current.clear();
    setPhoneData(null);
    setLoading(true);
    setActiveChatNpc(null);
    setChatMessages([]);
    setDailyLimits(null);
    setLoadingChat(false);
    setSendingChat(false);
    return () => {
      if (chatAbortRef.current) {
        try {
          chatAbortRef.current.abort();
        } catch {}
      }
    };
  }, [sessionId]);

  useEffect(() => {
    const handleMediaImageEvent = (event) => {
      const detail = event?.detail;
      if (!detail || detail.item_id == null) return;
      if (detail.session_id != null && String(detail.session_id) !== String(sessionId)) return;
      const targetId = String(detail.item_id);
      const evSeq = ++wsEventSeqRef.current;
      const resolvedStatus = detail.image_status || (detail.image_url ? 'ready' : undefined);
      mediaWsStateRef.current.set(targetId, {
        seq: evSeq,
        image_url: detail.image_url || '',
        image_status: resolvedStatus,
      });
      setPhoneData((prev) => {
        if (!prev || !Array.isArray(prev.media_gallery)) {
          pendingMediaEventsRef.current.set(targetId, detail);
          return prev;
        }
        let touched = false;
        const nextGallery = prev.media_gallery.map((m) => {
          if (String(m?.id) !== targetId) return m;
          touched = true;
          if (m.image_url && detail.image_status === 'generating' && !detail.image_url) {
            return m;
          }
          return {
            ...m,
            image_url: detail.image_url !== undefined && detail.image_url !== ''
              ? detail.image_url
              : m.image_url,
            image_status:
              resolvedStatus || m.image_status,
          };
        });
        if (!touched) {
          pendingMediaEventsRef.current.set(targetId, detail);
          return prev;
        }
        return { ...prev, media_gallery: nextGallery };
      });
    };
    window.addEventListener('hikayat:phone-media-image', handleMediaImageEvent);
    return () => window.removeEventListener('hikayat:phone-media-image', handleMediaImageEvent);
  }, [sessionId]);

  const loadChatMessages = async (npcId) => {
    if (!isValidSessionId(sessionId) || !npcId) return;
    if (chatAbortRef.current) {
      try {
        chatAbortRef.current.abort();
      } catch {}
    }
    const reqSid = String(sessionId);
    const seq = ++chatSeqRef.current;
    const controller = new AbortController();
    chatAbortRef.current = controller;
    setActiveChatNpc(npcId);
    setLoadingChat(true);
    try {
      const uidQuery = user?.user_id != null ? `?user_id=${encodeURIComponent(user.user_id)}` : '';
      const data = await apiCall(
        `/api/phone/${sessionId}/messages/${encodeURIComponent(npcId)}${uidQuery}`,
        { signal: controller.signal }
      );
      if (seq !== chatSeqRef.current || String(activeSessionIdRef.current) !== reqSid) return;
      setChatMessages(data.messages || []);
      if (data.daily_limits) {
        setDailyLimits(data.daily_limits);
      }
    } catch (err) {
      if (
        err?.isUserAbort ||
        err?.name === 'AbortError' ||
        seq !== chatSeqRef.current ||
        String(activeSessionIdRef.current) !== reqSid
      ) {
        return;
      }
      console.error("Failed to fetch NPC chat messages:", err);
      setChatMessages([]);
    } finally {
      if (seq === chatSeqRef.current && String(activeSessionIdRef.current) === reqSid) {
        setLoadingChat(false);
        if (chatAbortRef.current === controller) {
          chatAbortRef.current = null;
        }
      }
    }
  };

  const sendMessage = async (npcId, messageText, intent = 'chat') => {
    const cleanText = (messageText || '__auto__').trim();
    if (!isValidSessionId(sessionId) || !npcId || !user || !cleanText || sendingChat) return null;
    const reqSid = String(sessionId);
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
      if (String(activeSessionIdRef.current) !== reqSid) return null;
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
      if (String(activeSessionIdRef.current) === reqSid) {
        setSendingChat(false);
      }
    }
  };

  const refreshFeed = async () => {
    if (!isValidSessionId(sessionId) || !user) return null;
    const reqSid = String(sessionId);
    const data = await apiCall(`/api/phone/${sessionId}/feed/refresh`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        force_refresh: true,
      }),
    });
    if (data && String(activeSessionIdRef.current) === reqSid) {
      setPhoneData(prev => ({
        ...(prev || {}),
        gossip_feed: data.gossip_feed || data.posts || prev?.gossip_feed || [],
        social_state: data.social_state || prev?.social_state,
      }));
    }
    return data;
  };

  const scourFeed = async () => {
    if (!isValidSessionId(sessionId) || !user) return null;
    const reqSid = String(sessionId);
    const data = await apiCall(`/api/phone/${sessionId}/feed/scour`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
      }),
    });
    if (data && String(activeSessionIdRef.current) === reqSid) {
      setPhoneData(prev => ({
        ...(prev || {}),
        social_state: data.social_state || prev?.social_state,
        gossip_feed: data.gossip_feed || prev?.gossip_feed || [],
      }));
    }
    return data;
  };

  const discoverPeer = async (queryName = '') => {
    if (!isValidSessionId(sessionId) || !user) return null;
    return await apiCall(`/api/phone/${sessionId}/peerpulse/discover`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        query_name: queryName || null,
      }),
    });
  };

  const sendFriendRequest = async (profile) => {
    if (!isValidSessionId(sessionId) || !user || !profile) return null;
    const reqSid = String(sessionId);
    const data = await apiCall(`/api/phone/${sessionId}/peerpulse/friend-request`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        profile,
      }),
    });
    if (String(activeSessionIdRef.current) !== reqSid) return data;
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
    if (!isValidSessionId(sessionId) || !commitmentId) return null;
    const reqSid = String(sessionId);
    const data = await apiCall(`/api/commitments/${sessionId}/${commitmentId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user?.user_id,
        reason,
      }),
    });
    if (data && String(activeSessionIdRef.current) === reqSid) {
      setPhoneData(prev => ({
        ...(prev || {}),
        commitments: data.commitments || [],
        appointments: data.appointments || [],
      }));
    }
    return data;
  };

  const generateMediaPhoto = async (itemId, { forceRegenerate = false } = {}) => {
    if (!isValidSessionId(sessionId) || !itemId || !user?.user_id) return null;
    const reqSid = String(sessionId);
    const targetId = String(itemId);
    setPhoneData((prev) => {
      if (!prev || !Array.isArray(prev.media_gallery)) return prev;
      return {
        ...prev,
        media_gallery: prev.media_gallery.map((m) =>
          String(m?.id) === targetId ? { ...m, image_status: 'generating' } : m
        ),
      };
    });
    try {
      const data = await apiCall(`/api/phone/${sessionId}/media/${itemId}/generate`, {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          force_regenerate: Boolean(forceRegenerate),
        }),
      });
      if (String(activeSessionIdRef.current) !== reqSid) return null;
      if (data?.media) {
        setPhoneData((prev) => {
          if (!prev || !Array.isArray(prev.media_gallery)) return prev;
          return {
            ...prev,
            media_gallery: prev.media_gallery.map((m) =>
              String(m?.id) === targetId ? { ...m, ...data.media } : m
            ),
          };
        });
      }
      return data?.media || null;
    } catch (err) {
      if (String(activeSessionIdRef.current) === reqSid) {
        setPhoneData((prev) => {
          if (!prev || !Array.isArray(prev.media_gallery)) return prev;
          return {
            ...prev,
            media_gallery: prev.media_gallery.map((m) =>
              String(m?.id) === targetId
                ? { ...m, image_status: 'error' }
                : m
            ),
          };
        });
      }
      throw err;
    }
  };

  return {
    phoneData,
    imageGenEnabled: phoneData?.image_gen_enabled ?? 0,
    playerProfile: phoneData?.player_profile || null,
    branding: phoneData?.branding || {
      device_name: '📱 Smartphone',
      gallery_app_name: 'Photos',
      dm_app_name: 'Messages',
      feed_app_name: 'Feed',
      shop_app_name: 'Online Store',
      shop_subtitle: 'Instant Delivery',
      bounty_app_name: 'Bounty Board',
      bounty_subtitle: 'Contracts & Guilds',
      people_tab_label: 'Network',
      show_general_bounties: true,
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
    commsStatus: phoneData?.comms_status || { available: true, reason: '' },
    spiritRelayStaticActive: Boolean(phoneData?.spirit_relay_static_active),
    spiritRelayStaticNote: phoneData?.spirit_relay_static_note || '',
    loading,
    refreshPhone: fetchPhoneState,
    refreshPhoneData: fetchPhoneState,
    refreshFeed,
    scourFeed,
    discoverPeer,
    sendFriendRequest,
    cancelCommitment,
    generateMediaPhoto,
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
