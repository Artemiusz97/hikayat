import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../api/client';
import { useSceneImagePoll } from './session/useSceneImagePoll';
import { useTurnTransport } from './session/useTurnTransport';
import { useSessionSocket } from './session/useSessionSocket';

export const useGameSession = (user, character) => {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [waitingForParty, setWaitingForParty] = useState(false);
  const [partyStatus, setPartyStatus] = useState(null);
  const [lastSyncTimestamp, setLastSyncTimestamp] = useState(0);
  const [pausedOnDashboard, setPausedOnDashboard] = useState(false);
  const [actionError, setActionError] = useState(null);

  const socketRef = useRef(null);
  const activeSessionIdRef = useRef(null);
  const fetchSessionAbortRef = useRef(null);
  const isInitialLoadRef = useRef(true);

  const userId = user?.user_id;
  const activeCharacterId = character?.id;

  const {
    clearImagePoll,
    pollForSceneImage,
    rerollImage,
    rerollingImage,
  } = useSceneImagePoll({ session, user, setSession });

  const {
    processingTurn,
    pendingAction,
    setPendingAction,
    isStreaming,
    setIsStreaming,
    isThinking,
    setIsThinking,
    cancellingTurn,
    setCancellingTurn,
    streamingNarrative,
    setStreamingNarrative,
    streamingState,
    setStreamingState,
    safetyTimerRef,
    turnAbortControllerRef,
    syncTurnRequestRef,
    processingTurnRef,
    activeTurnIdRef,
    turnGenerationRef,
    completedTurnIdsRef,
    recordCompletedTurnId,
    setProcessingState,
    clearSafetyTimer,
    armSafetyTimer,
    submitAction,
    retryGeneration,
    cancelTurn,
  } = useTurnTransport({
    session,
    user,
    setSession,
    setWaitingForParty,
    setPartyStatus,
    setLastSyncTimestamp,
    setActionError,
    pollForSceneImage,
    socketRef,
  });

  const {
    wsStatus,
    partyChatMessages,
    setPartyChatMessages,
    onlineUserIds,
    closeSocket,
    connectWebSocket,
    sendPartyChat,
  } = useSessionSocket({
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
  });

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
  }, [
    userId,
    connectWebSocket,
    armSafetyTimer,
    clearSafetyTimer,
    setProcessingState,
    syncTurnRequestRef,
    setPendingAction,
    setIsThinking,
    setCancellingTurn,
    setIsStreaming,
    setStreamingNarrative,
    setStreamingState,
  ]);

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

  const startSession = async (scenarioKey, mode = 'solo', options = {}) => {
    const startGen = ++turnGenerationRef.current;
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    activeTurnIdRef.current = null;
    clearSafetyTimer();
    clearImagePoll();
    const abortCtrl = new AbortController();
    turnAbortControllerRef.current = abortCtrl;
    const safeScenario = (!scenarioKey || ['none', 'null', 'undefined'].includes(String(scenarioKey).trim().toLowerCase()))
      ? 'fantasy'
      : scenarioKey;

    setActionError(null);
    setCancellingTurn(false);
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
        signal: abortCtrl.signal,
        body: JSON.stringify({
          ...options,
          user_id: user.user_id,
          scenario: safeScenario,
          mode: mode,
          capacity: options.capacity,
          tags: options.tags,
        }),
      });
      if (turnGenerationRef.current !== startGen) {
        return null;
      }

      setSession(data.session);
      setPartyChatMessages([]);
      connectWebSocket(data.session.id);
      setLastSyncTimestamp(Date.now());
      return data;
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || turnGenerationRef.current !== startGen) {
        return null;
      }
      setSession(null);
      setPausedOnDashboard(true);
      setActionError(err.message || 'Failed to embark on adventure.');
      throw err;
    } finally {
      if (turnAbortControllerRef.current === abortCtrl) {
        turnAbortControllerRef.current = null;
      }
      if (turnGenerationRef.current === startGen) {
        setProcessingState(false);
        setPendingAction(null);
      }
    }
  };

  const joinSession = async (joinCode) => {
    const joinGen = ++turnGenerationRef.current;
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    activeTurnIdRef.current = null;
    clearSafetyTimer();
    clearImagePoll();
    setCancellingTurn(false);
    const abortCtrl = new AbortController();
    turnAbortControllerRef.current = abortCtrl;
    try {
      const data = await apiCall('/api/adventure/join', {
        method: 'POST',
        signal: abortCtrl.signal,
        body: JSON.stringify({
          user_id: user.user_id,
          join_code: joinCode,
        }),
      });
      if (turnGenerationRef.current !== joinGen) {
        return null;
      }
      setSession(data.session);
      setPausedOnDashboard(false);
      setPartyChatMessages([]);
      connectWebSocket(data.session.id);
      setLastSyncTimestamp(Date.now());
      return data;
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || turnGenerationRef.current !== joinGen) {
        return null;
      }
      throw err;
    } finally {
      if (turnAbortControllerRef.current === abortCtrl) {
        turnAbortControllerRef.current = null;
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
          character_id: character?.id,
        }),
      });
      const activeSess = res?.session || sessionObj;
      setSession(activeSess);
      setPausedOnDashboard(false);
      connectWebSocket(activeSess.id);
      setLastSyncTimestamp(Date.now());
    } catch (e) {
      console.error('Failed to resume session slot', e);
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
          user_id: user.user_id,
        }),
      });
      setSession(prev => (prev?.id === sessionId ? null : prev));
      fetchActiveSession({ silent: true });
    } catch (e) {
      console.error('Failed to end session slot', e);
    }
  }, [user?.user_id, fetchActiveSession]);

  const endSession = async () => {
    turnGenerationRef.current += 1;
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
            user_id: user.user_id,
          }),
        });
      } catch (e) {
        console.warn('Failed to end session:', e);
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

  const clearActionError = useCallback(() => setActionError(null), []);
  const refreshSession = useCallback(() => fetchActiveSession({ silent: true }), [fetchActiveSession]);

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
    clearActionError,
    refreshSession,
  };
};
