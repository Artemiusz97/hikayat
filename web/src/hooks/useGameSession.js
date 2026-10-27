import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../api/client';

export const useGameSession = (user, character) => {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processingTurn, setProcessingTurn] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingNarrative, setStreamingNarrative] = useState(null);
  const [streamingState, setStreamingState] = useState(null);
  const [waitingForParty, setWaitingForParty] = useState(false);
  const [partyStatus, setPartyStatus] = useState(null);
  const [lastSyncTimestamp, setLastSyncTimestamp] = useState(0);
  const [partyChatMessages, setPartyChatMessages] = useState([]);
  const [onlineUserIds, setOnlineUserIds] = useState([]);
  const [pausedOnDashboard, setPausedOnDashboard] = useState(false);
  const [actionError, setActionError] = useState(null);

  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  const isInitialLoadRef = useRef(true);
  const pollForSceneImage = useCallback((sessionId, maxAttempts = 15) => {
    if (!sessionId) return;
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await apiCall(`/api/adventure/session-image/${sessionId}`);
        if (res && res.scene_image_url) {
          clearInterval(interval);
          setSession(prev => {
            if (!prev || (prev.id !== sessionId && String(prev.id) !== String(sessionId))) return prev;
            const hist = Array.isArray(prev.history) ? [...prev.history] : [];
            if (hist.length > 0 && typeof hist[hist.length - 1] === 'object') {
              hist[hist.length - 1] = {
                ...hist[hist.length - 1],
                scene_image_url: res.scene_image_url,
              };
            }
            return {
              ...prev,
              scene_image_url: res.scene_image_url,
              history: hist
            };
          });
        } else if (attempts >= maxAttempts) {
          clearInterval(interval);
        }
      } catch (e) {
        if (attempts >= maxAttempts) {
          clearInterval(interval);
        }
      }
    }, 2000);
  }, []);


  const fetchActiveSession = useCallback(async (options = {}) => {
    const isInitial = isInitialLoadRef.current;
    const silent = options?.silent ?? !isInitial;
    if (!user) {
      setSession(null);
      setLoading(false);
      isInitialLoadRef.current = false;
      return;
    }
    try {
      if (!silent) {
        setLoading(true);
      }
      const data = await apiCall(`/api/adventure/active-session/${user.user_id}`);
      if (data && data.session) {
        setSession(data.session);
        connectWebSocket(data.session.id);
      } else {
        setSession(null);
      }
    } catch (e) {
      setSession(null);
    } finally {
      isInitialLoadRef.current = false;
      if (!silent) {
        setLoading(false);
      }
    }
  }, [user?.user_id, character?.id]);

  useEffect(() => {
    fetchActiveSession();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [fetchActiveSession]);

  const connectWebSocket = useCallback((sessionId) => {
    if (!sessionId || !user?.user_id) return;
    if (
      socketRef.current &&
      socketRef.current._sessionId === sessionId &&
      (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    if (socketRef.current) {
      try {
        socketRef.current.close();
      } catch (e) {}
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/session/${sessionId}?user_id=${user.user_id}`;

    const ws = new WebSocket(wsUrl);
    ws._sessionId = sessionId;
    socketRef.current = ws;

    ws.onopen = () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'STREAM_START') {
        setIsStreaming(true);
        setStreamingNarrative('');
        setStreamingState({
          action: data.action || null,
          outcomeText: '',
          nextText: '',
        });
      } else if (data.type === 'STREAM_CHUNK') {
        const chunkText = data.text || '';
        const field = data.field || 'outcome_narrative';
        setIsStreaming(true);
        setStreamingNarrative(prev => (prev || '') + chunkText);
        setStreamingState(prev => {
          const base = prev || { action: null, outcomeText: '', nextText: '' };
          if (field === 'next_narrative') {
            return { ...base, nextText: base.nextText + chunkText };
          }
          return { ...base, outcomeText: base.outcomeText + chunkText };
        });
      } else if (data.type === 'STREAM_END') {
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        setSession(data.session);
        setWaitingForParty(false);
        setProcessingTurn(false);
        setLastSyncTimestamp(data.sync_timestamp || Date.now());
      } else if (data.type === 'STREAM_ERROR') {
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        setProcessingTurn(false);
      } else if (data.type === 'NEW_SCENE') {
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        setSession(data.session);
        setWaitingForParty(false);
        setProcessingTurn(false);
        setLastSyncTimestamp(data.sync_timestamp || Date.now());
        if (data.session?.image_gen_enabled && !data.session?.scene_image_url) {
          pollForSceneImage(data.session.id);
        }
      } else if (data.type === 'HEARTBEAT') {
        // Keepalive acknowledged from backend turn engine
      } else if (data.type === 'UPDATE_SCENE') {
        setSession(prev => ({
          ...data.session,
          scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null
        }));
        setLastSyncTimestamp(data.sync_timestamp || Date.now());
      } else if (data.type === 'PICK_LOCKED') {
        setPartyStatus({
          lockedCount: data.locked_picks || 0,
          total: data.total || 0,
          waitingCount: data.waiting_count
        });
      } else if (data.type === 'SCENE_IMAGE') {
        setSession(prev => {
          if (!prev) return prev;
          const hist = Array.isArray(prev.history) ? [...prev.history] : [];
          if (hist.length > 0 && typeof hist[hist.length - 1] === 'object') {
            hist[hist.length - 1] = {
              ...hist[hist.length - 1],
              scene_image_url: data.image_url,
              scene_image_orientation: data.orientation || 'portrait'
            };
          }
          return {
            ...prev,
            scene_image_url: data.image_url,
            history: hist
          };
        });
      } else if (data.type === 'CHAT_MESSAGE') {
        setPartyChatMessages(prev => [
          ...prev.slice(-49),
          {
            id: `${Date.now()}-${Math.random()}`,
            user_id: data.user_id,
            sender: data.sender || 'Party Member',
            message: data.message || '',
            timestamp: Date.now()
          }
        ]);
      } else if (data.type === 'PRESENCE_UPDATE') {
        const online = (data.members || [])
          .filter(m => m && m.online)
          .map(m => m.user_id);
        setOnlineUserIds(online);
      } else if (data.type === 'STEALTH_STATE_UPDATED') {
        setSession(prev => {
          if (!prev) return prev;
          const isSameUser = !data.user_id || String(data.user_id) === String(user?.user_id);
          if (isSameUser) {
            return {
              ...prev,
              stealth_state: data.stealth_state,
              stealth_badge: data.stealth_badge || prev.stealth_badge
            };
          }
          const prevSt = prev.stealth_state || {};
          const incomingSt = data.stealth_state || {};
          return {
            ...prev,
            stealth_state: {
              ...prevSt,
              detection_meter: incomingSt.detection_meter ?? prevSt.detection_meter ?? 0,
              alert_level: incomingSt.alert_level ?? prevSt.alert_level ?? 'unaware',
              actors: incomingSt.actors || prevSt.actors || {}
            }
          };
        });
      }
    };

    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'PING' }));
      }
    }, 15000);

    ws.onclose = (event) => {
      clearInterval(interval);
      if (socketRef.current === ws) {
        socketRef.current = null;
      }
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      // Auto-reconnect unconditionally so server restarts or hot-reloads heal seamlessly
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocket(sessionId);
      }, 2000);
    };

    ws.onerror = () => {
      try {
        ws.close();
      } catch (e) {}
    };
  }, [user?.user_id]);

  const sendPartyChat = useCallback((messageText, senderName) => {
    const clean = (messageText || '').trim();
    if (!clean) return;
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(
        JSON.stringify({
          type: 'CHAT',
          sender: senderName || user?.display_name || 'Adventurer',
          message: clean
        })
      );
    } else {
      // Fallback local echo if WS is reconnecting
      setPartyChatMessages(prev => [
        ...prev.slice(-49),
        {
          id: `${Date.now()}-${Math.random()}`,
          user_id: user?.user_id,
          sender: senderName || user?.display_name || 'Adventurer',
          message: clean,
          timestamp: Date.now()
        }
      ]);
    }
  }, [user]);

  const startSession = async (scenarioKey, mode = 'solo', options = {}) => {
    // Immediately transition to narration UI with active processing banner
    setPausedOnDashboard(false);
    setProcessingTurn(true);
    setPendingAction({ label: 'Embarking on new journey...' });
    setSession({
      id: 'embarking',
      scenario: scenarioKey,
      scenario_display_name: options.scenario_display_name || scenarioKey,
      current_location: 'Beginning Journey...',
      narrative: '',
      history: [],
      choices: [],
      party_members: user ? [user] : [],
      party_npcs: [],
      nearby_enemies: [],
    });

    try {
      const data = await apiCall('/api/adventure/start', {
        timeout: 180000,
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          scenario: scenarioKey,
          mode: mode,
          capacity: options.capacity,
          tags: options.tags,
          ...options
        })
      });

      setSession(data.session);
      setPartyChatMessages([]);
      connectWebSocket(data.session.id);
      setLastSyncTimestamp(Date.now());
      return data;
    } catch (err) {
      setSession(null);
      setPausedOnDashboard(true);
      setActionError(err.message || 'Failed to embark on adventure.');
      throw err;
    } finally {
      setProcessingTurn(false);
      setPendingAction(null);
    }
  };

  const joinSession = async (joinCode) => {
    const data = await apiCall('/api/adventure/join', {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.user_id,
        join_code: joinCode
      })
    });
    setSession(data.session);
    setPausedOnDashboard(false);
    setPartyChatMessages([]);
    connectWebSocket(data.session.id);
    setLastSyncTimestamp(Date.now());
    return data;
  };

  const submitAction = async (actionData) => {
    if (processingTurn) return;
    setProcessingTurn(true);
    setPendingAction(actionData);
    setActionError(null);

    const safetyTimer = setTimeout(() => {
      console.warn('Action processing exceeded safety window (60s), releasing lock.');
      setProcessingTurn(false);
      setPendingAction(null);
    }, 60000);

    try {
      const payload = {
        session_id: session.id,
        user_id: user.user_id,
        choice_index: actionData?.choice_index !== undefined ? actionData.choice_index : null,
        custom_action_text: actionData?.custom_action_text || actionData?.custom_text || null,
        direct_choice: actionData?.direct_choice || null,
        combat_target: actionData?.combat_target || null,
        intent: actionData?.intent || null,
        skip_minutes: actionData?.skip_minutes !== undefined ? actionData.skip_minutes : null,
        sleep_mode: actionData?.sleep_mode || null,
        is_stealth: Boolean(actionData?.is_stealth),
        stance: actionData?.stance || null,
        action: actionData
      };
      const data = await apiCall('/api/adventure/action', {
        timeout: 180000,
        method: 'POST',
        body: JSON.stringify(payload)
      });

      if (data.status === 'waiting_for_party') {
        setWaitingForParty(true);
        setPartyStatus({
          lockedCount: data.locked_picks,
          total: data.total
        });
      } else {
        setSession(prev => ({
          ...data.session,
          scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null
        }));
        setWaitingForParty(false);
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        setLastSyncTimestamp(Date.now());
        if (data.session?.image_gen_enabled && !data.session?.scene_image_url) {
          pollForSceneImage(data.session.id);
        }
      }
      return data;
    } catch (e) {
      console.warn('Action API error or timeout, checking active session recovery...', e);
      const errMsg = e?.detail || e?.message || 'The action could not be completed. Please try again.';
      setActionError(errMsg);
      try {
        const recoveryData = await apiCall(`/api/adventure/active-session/${user.user_id}`);
        if (recoveryData && recoveryData.session) {
          setSession(prev => ({
            ...recoveryData.session,
            scene_image_url: recoveryData.session?.scene_image_url || prev?.scene_image_url || null
          }));
          setWaitingForParty(false);
          setIsStreaming(false);
          setStreamingNarrative(null);
          setStreamingState(null);
          setLastSyncTimestamp(Date.now());
          return;
        }
      } catch (recErr) {
        console.error('State recovery check failed:', recErr);
      }
      setIsStreaming(false);
      setStreamingNarrative(null);
      setStreamingState(null);
      throw e;
    } finally {
      clearTimeout(safetyTimer);
      setProcessingTurn(false);
      setPendingAction(null);
    }
  };

  const exitToDashboard = useCallback(() => {
    setPausedOnDashboard(true);
  }, []);

  const resumeSession = useCallback(() => {
    setPausedOnDashboard(false);
  }, []);

  const resumeSessionSlot = useCallback(async (sessionObj) => {
    if (!sessionObj?.id || !user?.user_id) return;
    try {
      const res = await apiCall('/api/adventure/resume', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: sessionObj.id,
          character_id: character?.id
        })
      });
      const activeSess = res?.session || sessionObj;
      setSession(activeSess);
      setPausedOnDashboard(false);
      connectWebSocket(activeSess.id);
      setLastSyncTimestamp(Date.now());
    } catch (e) {
      console.error("Failed to resume session slot", e);
      setSession(sessionObj);
      setPausedOnDashboard(false);
      connectWebSocket(sessionObj.id);
    }
  }, [user?.user_id, character?.id, connectWebSocket]);

  const endSessionById = useCallback(async (sessionId) => {
    if (!sessionId || !user?.user_id) return;
    try {
      await apiCall('/api/adventure/end', {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          user_id: user.user_id
        })
      });
      setSession(prev => (prev?.id === sessionId ? null : prev));
      fetchActiveSession({ silent: true });
    } catch (e) {
      console.error("Failed to end session slot", e);
    }
  }, [user?.user_id, fetchActiveSession]);

  const endSession = async () => {
    if (session?.id && user?.user_id) {
      try {
        await apiCall('/api/adventure/end', {
          method: 'POST',
          body: JSON.stringify({
            session_id: session.id,
            user_id: user.user_id
          })
        });
      } catch (e) {
        console.warn("Failed to end session:", e);
      }
    }
    if (socketRef.current) {
      socketRef.current.close();
    }
    setSession(null);
    setPausedOnDashboard(false);
    setWaitingForParty(false);
    setProcessingTurn(false);
  };

  const retryGeneration = async () => {
    if (!session?.id || !user?.user_id || processingTurn) return null;
    setProcessingTurn(true);
    try {
      const data = await apiCall('/api/adventure/retry', {
        timeout: 180000,
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id
        })
      });
      if (data?.session) {
        setSession(data.session);
        setLastSyncTimestamp(Date.now());
      }
      return data;
    } finally {
      setProcessingTurn(false);
    }
  };

  const [rerollingImage, setRerollingImage] = useState(false);

  const rerollImage = async () => {
    if (!session?.id || !user?.user_id || rerollingImage) return null;
    setRerollingImage(true);
    try {
      const data = await apiCall('/api/adventure/reroll_image', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id
        })
      });
      if (data?.image_url) {
        setSession(prev => {
          if (!prev) return prev;
          const hist = Array.isArray(prev.history) ? [...prev.history] : [];
          if (hist.length > 0 && typeof hist[hist.length - 1] === 'object') {
            hist[hist.length - 1] = {
              ...hist[hist.length - 1],
              scene_image_url: data.image_url
            };
          }
          return {
            ...prev,
            scene_image_url: data.image_url,
            history: hist
          };
        });
      }
      return data;
    } catch (err) {
      console.error('Reroll image failed:', err);
      throw err;
    } finally {
      setRerollingImage(false);
    }
  };

  return {
    session,
    setSession,
    pausedOnDashboard,
    loading,
    processingTurn,
    pendingAction,
    isStreaming,
    streamingNarrative,
    streamingState,
    waitingForParty,
    partyStatus,
    lastSyncTimestamp,
    partyChatMessages,
    onlineUserIds,
    sendPartyChat,
    startSession,
    joinSession,
    submitAction,
    exitToDashboard,
    resumeSession,
    resumeSessionSlot,
    endSession,
    endSessionById,
    retryGeneration,
    rerollImage,
    rerollingImage,
    actionError,
    clearActionError: () => setActionError(null),
    refreshSession: useCallback(() => fetchActiveSession({ silent: true }), [fetchActiveSession])
  };
};
