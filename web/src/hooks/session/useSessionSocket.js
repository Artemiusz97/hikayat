import { useState, useCallback, useRef } from 'react';
import { apiCall } from '../../api/client';
import { isAutoSceneImageGen } from './useSceneImagePoll';

export const useSessionSocket = ({
  user,
  socketRef,
  activeSessionIdRef,
  safetyTimerRef,
  clearImagePoll,
  pollForSceneImage,
  clearSafetyTimer,
  armSafetyTimer,
  recordCompletedTurnId,
  completedTurnIdsRef,
  activeTurnIdRef,
  processingTurnRef,
  cancellingTurnRef,
  syncTurnRequestRef,
  setProcessingState,
  setPendingAction,
  setIsThinking,
  setCancellingTurn,
  setIsStreaming,
  setStreamingNarrative,
  setStreamingState,
  setActionError,
  setSession,
  setWaitingForParty,
  setPartyStatus,
  setLastSyncTimestamp,
}) => {
  const [wsStatus, setWsStatus] = useState('idle');
  const [partyChatMessages, setPartyChatMessages] = useState([]);
  const [onlineUserIds, setOnlineUserIds] = useState([]);

  const reconnectTimeoutRef = useRef(null);
  const hasConnectedOnceRef = useRef(false);

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
      if (ws._pingInterval) {
        clearInterval(ws._pingInterval);
        ws._pingInterval = null;
      }
      ws._intentionalClose = true;
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try {
        ws.close();
      } catch {}
    }
  }, [socketRef]);

  const connectWebSocket = useCallback((sessionId) => {
    const userId = user?.user_id;
    const authToken = user?.auth_token;
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
      if (prevWs._pingInterval) {
        clearInterval(prevWs._pingInterval);
        prevWs._pingInterval = null;
      }
      prevWs._intentionalClose = true;
      prevWs.onopen = null;
      prevWs.onmessage = null;
      prevWs.onerror = null;
      prevWs.onclose = null;
      try {
        prevWs.close();
      } catch {}
    }

    setWsStatus(hasConnectedOnceRef.current ? 'reconnecting' : 'connecting');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenParam = authToken ? `&token=${encodeURIComponent(authToken)}` : '';
    const wsUrl = `${protocol}//${window.location.host}/ws/session/${sessionId}?user_id=${userId}${tokenParam}`;

    const ws = new WebSocket(wsUrl);
    ws._sessionId = sessionId;
    socketRef.current = ws;

    const isStaleTurnEvent = (turnId) =>
      Boolean(
        (turnId && completedTurnIdsRef.current.has(turnId)) ||
        (turnId && activeTurnIdRef.current && turnId !== activeTurnIdRef.current)
      );

    const applyCompletedScenePayload = (payload) => {
      if (isStaleTurnEvent(payload?.turn_id)) return;
      clearSafetyTimer();
      recordCompletedTurnId(payload?.turn_id);
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
      if (isAutoSceneImageGen(payload.session) && !payload.session?.scene_image_url) {
        pollForSceneImage(payload.session.id);
      }
    };

    ws.onopen = async () => {
      if (socketRef.current !== ws) return;
      hasConnectedOnceRef.current = true;
      setWsStatus('connected');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      const expectedSid = String(sessionId);
      if (processingTurnRef.current && !cancellingTurnRef?.current && userId && String(activeSessionIdRef.current) === expectedSid) {
        try {
          const res = await apiCall(`/api/adventure/active-session/${userId}`);
          if (socketRef.current !== ws || cancellingTurnRef?.current) return;
          if (
            res?.session &&
            String(activeSessionIdRef.current) === expectedSid &&
            String(res.session.id) === expectedSid
          ) {
            if (res.session.in_flight_turn) {
              setPendingAction(res.session.in_flight_turn.action || { label: 'Resolving Action...' });
              setIsThinking(res.session.in_flight_turn.status === 'thinking');
            } else if (processingTurnRef.current && !syncTurnRequestRef.current && !cancellingTurnRef?.current) {
              clearSafetyTimer();
              setSession(prev => ({
                ...res.session,
                scene_image_url: res.session?.scene_image_url || prev?.scene_image_url || null,
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
              recordCompletedTurnId(activeTurnIdRef.current);
              activeTurnIdRef.current = null;
              if (isAutoSceneImageGen(res.session) && !res.session?.scene_image_url) {
                pollForSceneImage(res.session.id);
              }
            }
          }
        } catch {}
      }
    };

    ws.onmessage = (event) => {
      if (socketRef.current !== ws) return;
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        console.warn('Ignoring malformed WebSocket message:', err);
        return;
      }
      if (!data || typeof data !== 'object') return;
      if (data.type === 'STREAM_THINKING') {
        if (cancellingTurnRef?.current || isStaleTurnEvent(data?.turn_id)) return;
        setProcessingState(true);
        setWaitingForParty(false);
        setIsThinking(true);
        if (data.action) {
          setPendingAction(prev => prev || data.action);
        }
        armSafetyTimer(182000);
      } else if (data.type === 'STREAM_START') {
        if (cancellingTurnRef?.current || isStaleTurnEvent(data?.turn_id)) return;
        setProcessingState(true);
        setWaitingForParty(false);
        setIsThinking(false);
        setIsStreaming(true);
        setStreamingNarrative('');
        setStreamingState({
          action: data.action || null,
          outcomeText: '',
          nextText: '',
        });
      } else if (data.type === 'STREAM_CHUNK') {
        if (cancellingTurnRef?.current || isStaleTurnEvent(data?.turn_id)) return;
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
        if (isStaleTurnEvent(data?.turn_id)) return;
        applyCompletedScenePayload(data);
      } else if (data.type === 'STREAM_RESET') {
        if (cancellingTurnRef?.current || isStaleTurnEvent(data?.turn_id)) return;
        setIsThinking(false);
        setStreamingNarrative('');
        setStreamingState(prev => (prev ? { ...prev, outcomeText: '', nextText: '' } : null));
      } else if (data.type === 'STREAM_ERROR') {
        if (isStaleTurnEvent(data?.turn_id)) return;
        clearSafetyTimer();
        recordCompletedTurnId(data?.turn_id);
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
            scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null,
          }));
          setLastSyncTimestamp(data.sync_timestamp || Date.now());
        }
        if (data.error) {
          setActionError(data.error);
        }
      } else if (data.type === 'TURN_CANCELLED') {
        if (isStaleTurnEvent(data?.turn_id)) return;
        clearSafetyTimer();
        recordCompletedTurnId(data?.turn_id);
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
            scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null,
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
            ...(data.non_lethal_mode !== undefined ? { non_lethal_mode: data.non_lethal_mode } : {}),
          }));
          if (data.type === 'UPDATE_SCENE') {
            setLastSyncTimestamp(data.sync_timestamp || Date.now());
          }
        } else if (data.non_lethal_mode !== undefined) {
          setSession(prev => (prev ? { ...prev, non_lethal_mode: data.non_lethal_mode } : prev));
        }
      } else if (data.type === 'PICK_LOCKED') {
        const nextWaiting = data.waiting_count;
        setPartyStatus({
          lockedCount: data.locked_picks || 0,
          total: data.total || 0,
          waitingCount: nextWaiting,
        });
        if (nextWaiting === 0 || (data.total && (data.locked_picks || 0) >= data.total)) {
          setWaitingForParty(false);
          setProcessingState(true);
        } else if (data.user_id != null && String(data.user_id) === String(userId)) {
          setWaitingForParty(true);
          setProcessingState(false);
        }
      } else if (data.type === 'SCENE_IMAGE') {
        clearImagePoll();
        setSession(prev => {
          if (!prev) return prev;
          const hist = Array.isArray(prev.history) ? [...prev.history] : [];
          if (hist.length > 0 && typeof hist[hist.length - 1] === 'object') {
            hist[hist.length - 1] = {
              ...hist[hist.length - 1],
              scene_image_url: data.image_url,
              scene_image_orientation: data.orientation || 'portrait',
            };
          }
          return {
            ...prev,
            scene_image_url: data.image_url,
            history: hist,
          };
        });
      } else if (data.type === 'PHONE_MEDIA_IMAGE') {
        try {
          window.dispatchEvent(new CustomEvent('hikayat:phone-media-image', { detail: data }));
        } catch {
          // ignore CustomEvent errors in non-browser environments
        }
      } else if (data.type === 'CHAT_MESSAGE') {
        setPartyChatMessages(prev => [
          ...prev.slice(-49),
          {
            id: `${Date.now()}-${Math.random()}`,
            user_id: data.user_id,
            sender: data.sender || 'Party Member',
            message: data.message || '',
            timestamp: Date.now(),
          },
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
        setSession(prev =>
          prev
            ? {
                ...prev,
                contracts_sync_ts: ts,
                ...(data.overview ? { contracts_overview: data.overview } : {}),
                ...(data.contracts ? { contracts: data.contracts } : {}),
              }
            : prev
        );
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
              ...(nextChoices ? { choices: nextChoices } : {}),
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
              actors: incomingSt.actors || prevSt.actors || {},
            },
          };
        });
      }
    };

    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'PING' }));
      }
    }, 15000);
    ws._pingInterval = interval;

    ws.onclose = (event) => {
      clearInterval(interval);
      if (ws._pingInterval === interval) {
        ws._pingInterval = null;
      }
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
  }, [
    user?.user_id,
    user?.auth_token,
    socketRef,
    activeSessionIdRef,
    safetyTimerRef,
    clearImagePoll,
    pollForSceneImage,
    clearSafetyTimer,
    armSafetyTimer,
    recordCompletedTurnId,
    completedTurnIdsRef,
    activeTurnIdRef,
    processingTurnRef,
    cancellingTurnRef,
    syncTurnRequestRef,
    setProcessingState,
    setPendingAction,
    setIsThinking,
    setCancellingTurn,
    setIsStreaming,
    setStreamingNarrative,
    setStreamingState,
    setActionError,
    setSession,
    setWaitingForParty,
    setPartyStatus,
    setLastSyncTimestamp,
  ]);

  const sendPartyChat = useCallback((messageText, senderName) => {
    const clean = (messageText || '').trim();
    if (!clean) return;
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(
        JSON.stringify({
          type: 'CHAT',
          sender: senderName || user?.display_name || 'Adventurer',
          message: clean,
        })
      );
    } else {
      setPartyChatMessages(prev => [
        ...prev.slice(-49),
        {
          id: `${Date.now()}-${Math.random()}`,
          user_id: user?.user_id,
          sender: senderName || user?.display_name || 'Adventurer',
          message: clean,
          timestamp: Date.now(),
        },
      ]);
    }
  }, [user?.user_id, user?.display_name, socketRef]);

  return {
    wsStatus,
    partyChatMessages,
    setPartyChatMessages,
    onlineUserIds,
    closeSocket,
    connectWebSocket,
    sendPartyChat,
  };
};
