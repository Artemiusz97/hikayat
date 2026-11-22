import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../api/client';

export const useGameSession = (user, character) => {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processingTurn, setProcessingTurn] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [cancellingTurn, setCancellingTurn] = useState(false);
  const [streamingNarrative, setStreamingNarrative] = useState(null);
  const [streamingState, setStreamingState] = useState(null);
  const [waitingForParty, setWaitingForParty] = useState(false);
  const [partyStatus, setPartyStatus] = useState(null);
  const [lastSyncTimestamp, setLastSyncTimestamp] = useState(0);
  const [partyChatMessages, setPartyChatMessages] = useState([]);
  const [onlineUserIds, setOnlineUserIds] = useState([]);
  const [pausedOnDashboard, setPausedOnDashboard] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [wsStatus, setWsStatus] = useState('idle');

  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const activeSessionIdRef = useRef(null);
  const imagePollIntervalRef = useRef(null);
  const safetyTimerRef = useRef(null);
  const turnAbortControllerRef = useRef(null);
  const fetchSessionAbortRef = useRef(null);
  const syncTurnRequestRef = useRef(false);
  const processingTurnRef = useRef(false);
  const pendingAsyncPostRef = useRef(null);
  const activeTurnIdRef = useRef(null);
  const hasConnectedOnceRef = useRef(false);

  useEffect(() => {
    processingTurnRef.current = processingTurn;
  }, [processingTurn]);

  const setProcessingState = useCallback((next) => {
    processingTurnRef.current = next;
    setProcessingTurn(next);
  }, []);

  const clearImagePoll = useCallback(() => {
    if (imagePollIntervalRef.current) {
      clearInterval(imagePollIntervalRef.current);
      imagePollIntervalRef.current = null;
    }
  }, []);

  const clearSafetyTimer = useCallback(() => {
    if (safetyTimerRef.current) {
      clearTimeout(safetyTimerRef.current);
      safetyTimerRef.current = null;
    }
  }, []);

  const armSafetyTimer = useCallback((ms = 245000) => {
    clearSafetyTimer();
    safetyTimerRef.current = setTimeout(() => {
      console.warn(`Action processing exceeded safety window (${Math.round(ms / 1000)}s), releasing lock.`);
      setProcessingState(false);
      setPendingAction(null);
      setIsThinking(false);
      setCancellingTurn(false);
      setIsStreaming(false);
      setStreamingNarrative(null);
      setStreamingState(null);
      safetyTimerRef.current = null;
    }, ms);
  }, [clearSafetyTimer, setProcessingState]);

  const closeSocket = useCallback(() => {
    hasConnectedOnceRef.current = false;
    setWsStatus('idle');
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (socketRef.current) {
      const ws = socketRef.current;
      socketRef.current = null;
      ws._intentionalClose = true;
      ws.onclose = null;
      try {
        ws.close();
      } catch {}
    }
  }, []);

  const isInitialLoadRef = useRef(true);
  const pollForSceneImage = useCallback((sessionId, maxAttempts = 15) => {
    if (!sessionId) return;
    clearImagePoll();
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await apiCall(`/api/adventure/session-image/${sessionId}`);
        if (res && res.scene_image_url) {
          clearInterval(interval);
          if (imagePollIntervalRef.current === interval) {
            imagePollIntervalRef.current = null;
          }
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
          if (imagePollIntervalRef.current === interval) {
            imagePollIntervalRef.current = null;
          }
        }
      } catch {
        if (attempts >= maxAttempts) {
          clearInterval(interval);
          if (imagePollIntervalRef.current === interval) {
            imagePollIntervalRef.current = null;
          }
        }
      }
    }, 2000);
    imagePollIntervalRef.current = interval;
  }, [clearImagePoll]);


  const connectWebSocket = useCallback((sessionId) => {
    const userId = user?.user_id;
    if (!sessionId || sessionId === 'embarking' || !userId) return;
    if (activeSessionIdRef.current !== null && String(activeSessionIdRef.current) !== String(sessionId)) {
      hasConnectedOnceRef.current = false;
    }
    activeSessionIdRef.current = sessionId;
    if (
      socketRef.current &&
      String(socketRef.current._sessionId) === String(sessionId) &&
      (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    if (socketRef.current) {
      const prevWs = socketRef.current;
      socketRef.current = null;
      prevWs._intentionalClose = true;
      prevWs.onclose = null;
      try {
        prevWs.close();
      } catch {}
    }

    setWsStatus(hasConnectedOnceRef.current ? 'reconnecting' : 'connecting');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenParam = user?.auth_token ? `&token=${encodeURIComponent(user.auth_token)}` : '';
    const wsUrl = `${protocol}//${window.location.host}/ws/session/${sessionId}?user_id=${userId}${tokenParam}`;

    const ws = new WebSocket(wsUrl);
    ws._sessionId = sessionId;
    socketRef.current = ws;

    const applyCompletedScenePayload = (payload) => {
      clearSafetyTimer();
      activeTurnIdRef.current = null;
      setIsThinking(false);
      setCancellingTurn(false);
      setIsStreaming(false);
      setStreamingNarrative(null);
      setStreamingState(null);
      setActionError(null);
      setSession(payload.session);
      setWaitingForParty(false);
      setProcessingState(false);
      setPendingAction(null);
      setLastSyncTimestamp(payload.sync_timestamp || Date.now());
      if (payload.session?.image_gen_enabled && !payload.session?.scene_image_url) {
        pollForSceneImage(payload.session.id);
      }
    };

    ws.onopen = async () => {
      hasConnectedOnceRef.current = true;
      setWsStatus('connected');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      const expectedSid = String(sessionId);
      if (processingTurnRef.current && userId && String(activeSessionIdRef.current) === expectedSid) {
        try {
          const res = await apiCall(`/api/adventure/active-session/${userId}`);
          if (
            res?.session &&
            String(activeSessionIdRef.current) === expectedSid &&
            String(res.session.id) === expectedSid
          ) {
            if (res.session.in_flight_turn) {
              setPendingAction(res.session.in_flight_turn.action || { label: 'Resolving Action...' });
              setIsThinking(res.session.in_flight_turn.status === 'thinking');
            } else if (!syncTurnRequestRef.current) {
              clearSafetyTimer();
              setSession(prev => ({
                ...res.session,
                scene_image_url: res.session?.scene_image_url || prev?.scene_image_url || null
              }));
              setProcessingState(false);
              setPendingAction(null);
              setIsThinking(false);
              setCancellingTurn(false);
              setIsStreaming(false);
              setStreamingNarrative(null);
              setStreamingState(null);
              setLastSyncTimestamp(Date.now());
              const missedErr = res.session.last_turn_error;
              if (missedErr?.error && (!activeTurnIdRef.current || missedErr.turn_id === activeTurnIdRef.current)) {
                setActionError(missedErr.error);
              }
              activeTurnIdRef.current = null;
              if (res.session?.image_gen_enabled && !res.session?.scene_image_url) {
                pollForSceneImage(res.session.id);
              }
            }
          }
        } catch {}
      }
    };

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        console.warn('Ignoring malformed WebSocket message:', err);
        return;
      }
      if (!data || typeof data !== 'object') return;
      if (data.type === 'STREAM_THINKING') {
        setIsThinking(true);
        if (data.action) {
          setPendingAction(prev => prev || data.action);
        }
        armSafetyTimer(182000);
      } else if (data.type === 'STREAM_START') {
        setIsThinking(false);
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
        setIsThinking(false);
        setIsStreaming(true);
        armSafetyTimer(182000);
        setStreamingNarrative(prev => (prev || '') + chunkText);
        setStreamingState(prev => {
          const base = prev || { action: null, outcomeText: '', nextText: '' };
          if (field === 'next_narrative') {
            return { ...base, nextText: base.nextText + chunkText };
          }
          return { ...base, outcomeText: base.outcomeText + chunkText };
        });
      } else if (data.type === 'STREAM_END' || data.type === 'NEW_SCENE') {
        applyCompletedScenePayload(data);
      } else if (data.type === 'STREAM_RESET') {
        setIsThinking(false);
        setStreamingNarrative('');
        setStreamingState(prev => (prev ? { ...prev, outcomeText: '', nextText: '' } : null));
      } else if (data.type === 'STREAM_ERROR') {
        clearSafetyTimer();
        activeTurnIdRef.current = null;
        setIsThinking(false);
        setCancellingTurn(false);
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        setProcessingState(false);
        setPendingAction(null);
        if (data.session) {
          setSession(prev => ({
            ...data.session,
            scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null
          }));
          setLastSyncTimestamp(data.sync_timestamp || Date.now());
        }
        if (data.error) {
          setActionError(data.error);
        }
      } else if (data.type === 'TURN_CANCELLED') {
        clearSafetyTimer();
        activeTurnIdRef.current = null;
        setIsThinking(false);
        setCancellingTurn(false);
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        setWaitingForParty(false);
        setProcessingState(false);
        setPendingAction(null);
        setActionError(null);
        if (data.session) {
          setSession(prev => ({
            ...data.session,
            scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null
          }));
          setLastSyncTimestamp(data.sync_timestamp || Date.now());
        }
      } else if (data.type === 'HEARTBEAT') {
        if (safetyTimerRef.current) {
          armSafetyTimer(182000);
        }
      } else if (data.type === 'UPDATE_SCENE' || data.type === 'SESSION_UPDATED') {
        if (data.session) {
          setSession(prev => ({
            ...data.session,
            scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null,
            ...(data.non_lethal_mode !== undefined ? { non_lethal_mode: data.non_lethal_mode } : {})
          }));
          if (data.type === 'UPDATE_SCENE') {
            setLastSyncTimestamp(data.sync_timestamp || Date.now());
          }
        } else if (data.non_lethal_mode !== undefined) {
          setSession(prev => (prev ? { ...prev, non_lethal_mode: data.non_lethal_mode } : prev));
        }
      } else if (data.type === 'PICK_LOCKED') {
        setPartyStatus({
          lockedCount: data.locked_picks || 0,
          total: data.total || 0,
          waitingCount: data.waiting_count
        });
      } else if (data.type === 'SCENE_IMAGE') {
        clearImagePoll();
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
      } else if (data.type === 'WORLD_PULSE_SYNC') {
        setSession(prev => (prev ? { ...prev, world_pulse: data.world_pulse } : prev));
        setLastSyncTimestamp(data.sync_timestamp || Date.now());
      } else if (data.type === 'REALTY_STATE_SYNC') {
        setSession(prev => (prev ? { ...prev, realty: data.realty } : prev));
        setLastSyncTimestamp(Date.now());
      } else if (data.type === 'CONTRACTS_STATE_SYNC') {
        const ts = data.sync_timestamp || Date.now();
        setSession(prev => (
          prev
            ? {
                ...prev,
                contracts_sync_ts: ts,
                ...(data.overview ? { contracts_overview: data.overview } : {}),
                ...(data.contracts ? { contracts: data.contracts } : {}),
              }
            : prev
        ));
        setLastSyncTimestamp(ts);
      } else if (data.type === 'STEALTH_STATE_UPDATED') {
        setSession(prev => {
          if (!prev) return prev;
          const isSameUser = !data.user_id || String(data.user_id) === String(userId);
          const nextChoices = Array.isArray(data.choices)
            ? data.choices
            : (Array.isArray(data.session?.choices) ? data.session.choices : null);
          if (isSameUser) {
            return {
              ...prev,
              stealth_state: data.stealth_state,
              stealth_badge: data.stealth_badge || prev.stealth_badge,
              ...(nextChoices ? { choices: nextChoices } : {})
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
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (
        ws._intentionalClose ||
        event?.code === 1008 ||
        !activeSessionIdRef.current ||
        String(activeSessionIdRef.current) !== String(sessionId)
      ) {
        if (!ws._intentionalClose) {
          setWsStatus('idle');
        }
        return;
      }
      setWsStatus('reconnecting');
      // Auto-reconnect across server restarts / hot-reloads when session remains active
      reconnectTimeoutRef.current = setTimeout(() => {
        if (activeSessionIdRef.current && String(activeSessionIdRef.current) === String(sessionId)) {
          connectWebSocket(sessionId);
        }
      }, 2000);
    };

    ws.onerror = () => {
      try {
        ws.close();
      } catch {}
    };
  }, [user?.user_id, user?.auth_token, clearImagePoll, pollForSceneImage, armSafetyTimer, clearSafetyTimer, setProcessingState]);

  const userId = user?.user_id;
  const activeCharacterId = character?.id;

  const fetchActiveSession = useCallback(async (options = {}) => {
    const isInitial = isInitialLoadRef.current;
    const silent = options?.silent ?? !isInitial;
    if (!userId) {
      if (fetchSessionAbortRef.current) {
        try {
          fetchSessionAbortRef.current.abort();
        } catch {}
        fetchSessionAbortRef.current = null;
      }
      setSession(null);
      setLoading(false);
      isInitialLoadRef.current = false;
      return;
    }
    if (fetchSessionAbortRef.current) {
      try {
        fetchSessionAbortRef.current.abort();
      } catch {}
    }
    const controller = new AbortController();
    fetchSessionAbortRef.current = controller;
    let aborted = false;
    try {
      if (!silent) {
        setLoading(true);
      }
      const data = await apiCall(`/api/adventure/active-session/${userId}`, {
        signal: controller.signal,
      });
      if (fetchSessionAbortRef.current !== controller) return;
      if (data && data.session) {
        setSession(data.session);
        if (data.session.in_flight_turn) {
          setProcessingState(true);
          setPendingAction(data.session.in_flight_turn.action || { label: 'Resolving Action...' });
          setIsThinking(data.session.in_flight_turn.status === 'thinking');
          armSafetyTimer(245000);
        } else if (!syncTurnRequestRef.current) {
          clearSafetyTimer();
          setProcessingState(false);
          setPendingAction(null);
          setIsThinking(false);
          setCancellingTurn(false);
          setIsStreaming(false);
          setStreamingNarrative(null);
          setStreamingState(null);
        }
        connectWebSocket(data.session.id);
      } else {
        setSession(null);
      }
    } catch (e) {
      if (e?.isUserAbort || e?.name === 'AbortError') {
        aborted = true;
        return;
      }
      setSession(null);
    } finally {
      if (fetchSessionAbortRef.current === controller) {
        fetchSessionAbortRef.current = null;
      }
      if (!aborted) {
        isInitialLoadRef.current = false;
        if (!silent) {
          setLoading(false);
        }
      }
    }
  }, [userId, connectWebSocket, armSafetyTimer, clearSafetyTimer, setProcessingState]);

  useEffect(() => {
    void activeCharacterId;
    fetchActiveSession();
    return () => {
      if (fetchSessionAbortRef.current) {
        try {
          fetchSessionAbortRef.current.abort();
        } catch {}
        fetchSessionAbortRef.current = null;
      }
      clearImagePoll();
      clearSafetyTimer();
      closeSocket();
    };
  }, [fetchActiveSession, activeCharacterId, clearImagePoll, clearSafetyTimer, closeSocket]);

  useEffect(() => {
    if (session?.id && session.id !== 'embarking') {
      activeSessionIdRef.current = session.id;
      connectWebSocket(session.id);
    } else {
      activeSessionIdRef.current = null;
      clearImagePoll();
      closeSocket();
    }
  }, [session?.id, connectWebSocket, clearImagePoll, closeSocket]);

  useEffect(() => {
    if (!processingTurn || !session?.id || session.id === 'embarking' || !user?.user_id) {
      return;
    }
    const pollId = setInterval(async () => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        return;
      }
      try {
        const res = await apiCall(`/api/adventure/active-session/${user.user_id}`);
        if (res?.session) {
          if (res.session.in_flight_turn) {
            setIsThinking(res.session.in_flight_turn.status === 'thinking');
          } else {
            clearSafetyTimer();
            setSession(prev => ({
              ...res.session,
              scene_image_url: res.session?.scene_image_url || prev?.scene_image_url || null
            }));
            setProcessingState(false);
            setPendingAction(null);
            setIsThinking(false);
            setCancellingTurn(false);
            setIsStreaming(false);
            setStreamingNarrative(null);
            setStreamingState(null);
            setLastSyncTimestamp(Date.now());
            const missedErr = res.session.last_turn_error;
            if (missedErr?.error && (!activeTurnIdRef.current || missedErr.turn_id === activeTurnIdRef.current)) {
              setActionError(missedErr.error);
            }
            activeTurnIdRef.current = null;
            if (res.session?.image_gen_enabled && !res.session?.scene_image_url) {
              pollForSceneImage(res.session.id);
            }
          }
        }
      } catch {}
    }, 5000);
    return () => clearInterval(pollId);
  }, [processingTurn, session?.id, user?.user_id, clearSafetyTimer, pollForSceneImage, setProcessingState]);

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
    const safeScenario = (!scenarioKey || ['none', 'null', 'undefined'].includes(String(scenarioKey).trim().toLowerCase()))
      ? 'fantasy'
      : scenarioKey;
    // Immediately transition to narration UI with active processing banner
    setActionError(null);
    setPausedOnDashboard(false);
    setProcessingState(true);
    setPendingAction({ label: 'Embarking on new journey...' });
    setSession({
      id: 'embarking',
      scenario: safeScenario,
      scenario_display_name: options.scenario_display_name || safeScenario,
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
        timeout: 240000,
        method: 'POST',
        body: JSON.stringify({
          ...options,
          user_id: user.user_id,
          scenario: safeScenario,
          mode: mode,
          capacity: options.capacity,
          tags: options.tags,
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
      setProcessingState(false);
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
    if (processingTurnRef.current) return;
    setProcessingState(true);
    setPendingAction(actionData);
    setIsThinking(false);
    setActionError(null);

    armSafetyTimer(245000);

    const prevTurnCount = session?.turn_count ?? 0;
    const prevHistLen = Array.isArray(session?.history) ? session.history.length : 0;
    const canAsyncWs = Boolean(socketRef.current && socketRef.current.readyState === WebSocket.OPEN);
    let asyncAccepted = false;
    activeTurnIdRef.current = null;
    const abortCtrl = canAsyncWs ? null : new AbortController();
    turnAbortControllerRef.current = abortCtrl;
    syncTurnRequestRef.current = !canAsyncWs;
    let postPromise = null;

    try {
      const payload = {
        session_id: session.id,
        user_id: user.user_id,
        choice_index: actionData?.choice_index !== undefined ? actionData.choice_index : null,
        custom_action_text: actionData?.custom_action_text || actionData?.custom_text || null,
        direct_choice: actionData?.direct_choice || null,
        combat_target: actionData?.combat_target || null,
        intent: actionData?.intent || null,
        target_npc: actionData?.target_npc || null,
        item_id: actionData?.item_id !== undefined ? actionData.item_id : null,
        target_type: actionData?.target_type || null,
        target_name: actionData?.target_name || null,
        target_user_id: actionData?.target_user_id !== undefined ? actionData.target_user_id : null,
        use_mode: actionData?.use_mode || null,
        skip_minutes: actionData?.skip_minutes !== undefined ? actionData.skip_minutes : null,
        sleep_mode: actionData?.sleep_mode || null,
        is_stealth: Boolean(actionData?.is_stealth),
        stance: actionData?.stance || null,
        action: actionData,
        async_ws: canAsyncWs
      };
      postPromise = apiCall('/api/adventure/action', {
        timeout: 240000,
        method: 'POST',
        ...(abortCtrl ? { signal: abortCtrl.signal } : {}),
        body: JSON.stringify(payload)
      });
      if (canAsyncWs) {
        pendingAsyncPostRef.current = postPromise;
      }
      const data = await postPromise;

      if (data?.status === 'accepted') {
        asyncAccepted = true;
        activeTurnIdRef.current = data.turn_id || null;
        return data;
      }

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
      if (e?.name === 'AbortError' || e?.isUserAbort) {
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        return null;
      }
      console.warn('Action API error or timeout, checking active session recovery...', e);
      const errMsg = e?.detail || e?.message || 'The action could not be completed. Please try again.';
      setActionError(errMsg);
      try {
        const recoveryData = await apiCall(`/api/adventure/active-session/${user.user_id}`);
        if (recoveryData && recoveryData.session) {
          const recTurnCount = recoveryData.session.turn_count ?? 0;
          const recHistLen = Array.isArray(recoveryData.session.history) ? recoveryData.session.history.length : 0;
          const inFlight = recoveryData.session.in_flight_turn;
          if (inFlight || recTurnCount > prevTurnCount || recHistLen > prevHistLen) {
            setActionError(null);
          }
          setSession(prev => ({
            ...recoveryData.session,
            scene_image_url: recoveryData.session?.scene_image_url || prev?.scene_image_url || null
          }));
          setWaitingForParty(false);
          if (inFlight) {
            asyncAccepted = true;
            activeTurnIdRef.current = inFlight.turn_id || null;
            setPendingAction(inFlight.action || actionData);
            setIsThinking(inFlight.status === 'thinking');
            armSafetyTimer(245000);
          } else {
            setIsStreaming(false);
            setStreamingNarrative(null);
            setStreamingState(null);
            setLastSyncTimestamp(Date.now());
          }
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
      if (pendingAsyncPostRef.current === postPromise) {
        pendingAsyncPostRef.current = null;
      }
      syncTurnRequestRef.current = false;
      if (turnAbortControllerRef.current === abortCtrl) {
        turnAbortControllerRef.current = null;
      }
      if (!asyncAccepted) {
        clearSafetyTimer();
        setProcessingState(false);
        setPendingAction(null);
        setIsThinking(false);
      }
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
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    clearSafetyTimer();
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
    activeSessionIdRef.current = null;
    clearImagePoll();
    closeSocket();
    setSession(null);
    setPausedOnDashboard(false);
    setWaitingForParty(false);
    setProcessingState(false);
    setPendingAction(null);
    setIsThinking(false);
    setCancellingTurn(false);
  };

  const retryGeneration = async () => {
    if (!session?.id || !user?.user_id || processingTurnRef.current) return null;
    setProcessingState(true);
    armSafetyTimer(245000);
    setIsStreaming(false);
    setIsThinking(false);
    setStreamingNarrative(null);
    setStreamingState(null);
    const hasHistory = Array.isArray(session?.history) && session.history.length > 0;
    setPendingAction({
      label: 'Regenerating scene...',
      ...(hasHistory ? {} : { isSyncTurnZeroRetry: true }),
    });
    setActionError(null);
    const canAsyncWs = Boolean(
      hasHistory &&
      socketRef.current &&
      socketRef.current.readyState === WebSocket.OPEN
    );
    let asyncAccepted = false;
    activeTurnIdRef.current = null;
    const abortCtrl = canAsyncWs ? null : new AbortController();
    turnAbortControllerRef.current = abortCtrl;
    syncTurnRequestRef.current = !canAsyncWs;
    let postPromise = null;
    try {
      postPromise = apiCall('/api/adventure/retry', {
        timeout: 240000,
        method: 'POST',
        ...(abortCtrl ? { signal: abortCtrl.signal } : {}),
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
          async_ws: canAsyncWs
        })
      });
      if (canAsyncWs) {
        pendingAsyncPostRef.current = postPromise;
      }
      const data = await postPromise;
      if (data?.status === 'accepted') {
        asyncAccepted = true;
        activeTurnIdRef.current = data.turn_id || null;
        return data;
      }
      if (data?.session) {
        setSession(data.session);
        setLastSyncTimestamp(Date.now());
      }
      return data;
    } catch (e) {
      if (e?.name === 'AbortError' || e?.isUserAbort) {
        return null;
      }
      const errMsg = e?.detail || e?.message || 'Failed to regenerate narration. Please try again.';
      setActionError(errMsg);
      return null;
    } finally {
      if (pendingAsyncPostRef.current === postPromise) {
        pendingAsyncPostRef.current = null;
      }
      syncTurnRequestRef.current = false;
      if (turnAbortControllerRef.current === abortCtrl) {
        turnAbortControllerRef.current = null;
      }
      if (!asyncAccepted) {
        clearSafetyTimer();
        setProcessingState(false);
        setPendingAction(null);
        setIsThinking(false);
      }
    }
  };

  const cancelTurn = useCallback(async () => {
    if (!session?.id || session.id === 'embarking' || !user?.user_id || cancellingTurn) return;
    setCancellingTurn(true);
    if (pendingAsyncPostRef.current) {
      try {
        await pendingAsyncPostRef.current;
      } catch {}
    }
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    try {
      const res = await apiCall('/api/adventure/cancel', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
        })
      });
      clearSafetyTimer();
      setIsStreaming(false);
      setStreamingNarrative(null);
      setStreamingState(null);
      setIsThinking(false);
      setProcessingState(false);
      setPendingAction(null);
      setWaitingForParty(false);
      setActionError(null);
      if (res?.session) {
        setSession(prev => ({
          ...res.session,
          scene_image_url: res.session?.scene_image_url || prev?.scene_image_url || null
        }));
        setLastSyncTimestamp(Date.now());
      }
    } catch (e) {
      console.error('Failed to cancel in-flight turn:', e);
      setActionError(e?.detail || e?.message || 'Failed to cancel turn.');
    } finally {
      setCancellingTurn(false);
    }
  }, [session?.id, user?.user_id, cancellingTurn, clearSafetyTimer, setProcessingState]);

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
    isThinking,
    cancellingTurn,
    streamingNarrative,
    streamingState,
    waitingForParty,
    partyStatus,
    lastSyncTimestamp,
    wsStatus,
    partyChatMessages,
    onlineUserIds,
    sendPartyChat,
    startSession,
    joinSession,
    submitAction,
    cancelTurn,
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
