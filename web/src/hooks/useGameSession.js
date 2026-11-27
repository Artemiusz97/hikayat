import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../api/client';
import { isValidSessionId } from '../utils/session';
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
    cancellingTurnRef,
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
  });

  const resetTransientTurnState = useCallback(() => {
    clearSafetyTimer();
    activeTurnIdRef.current = null;
    setProcessingState(false);
    setPendingAction(null);
    setIsStreaming(false);
    setIsThinking(false);
    setStreamingNarrative(null);
    setStreamingState(null);
    setCancellingTurn(false);
    setWaitingForParty(false);
    setPartyStatus(null);
    setActionError(null);
    setPartyChatMessages([]);
  }, [
    clearSafetyTimer,
    activeTurnIdRef,
    setProcessingState,
    setPendingAction,
    setIsStreaming,
    setIsThinking,
    setStreamingNarrative,
    setStreamingState,
    setCancellingTurn,
    setWaitingForParty,
    setPartyStatus,
    setActionError,
    setPartyChatMessages,
  ]);

  const fetchActiveSession = useCallback(async (options = {}) => {
    const isInitial = isInitialLoadRef.current;
    const silent = options?.silent ?? !isInitial;
    const fetchGen = turnGenerationRef.current;
    if (!userId) {
      if (fetchSessionAbortRef.current) {
        try {
          fetchSessionAbortRef.current.abort();
        } catch {}
        fetchSessionAbortRef.current = null;
      }
      resetTransientTurnState();
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
      if (fetchSessionAbortRef.current !== controller || turnGenerationRef.current !== fetchGen) {
        return;
      }
      if (data && data.session) {
        if (activeSessionIdRef.current && String(activeSessionIdRef.current) !== String(data.session.id)) {
          clearImagePoll();
          resetTransientTurnState();
        }
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
        resetTransientTurnState();
        setSession(null);
      }
    } catch (e) {
      if (e?.isUserAbort || e?.name === 'AbortError') {
        aborted = true;
        return;
      }
      if (fetchSessionAbortRef.current !== controller || turnGenerationRef.current !== fetchGen) {
        return;
      }
      if (silent && activeSessionIdRef.current && e?.status !== 404) {
        console.warn('Transient active-session refresh failed; retaining current session:', e);
        return;
      }
      resetTransientTurnState();
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
    turnGenerationRef,
    clearImagePoll,
    resetTransientTurnState,
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
      turnGenerationRef.current += 1;
      if (turnAbortControllerRef.current) {
        try {
          turnAbortControllerRef.current.abort();
        } catch {}
        turnAbortControllerRef.current = null;
      }
      syncTurnRequestRef.current = false;
      resetTransientTurnState();
      if (fetchSessionAbortRef.current) {
        try {
          fetchSessionAbortRef.current.abort();
        } catch {}
        fetchSessionAbortRef.current = null;
      }
      clearImagePoll();
      closeSocket();
    };
  }, [
    fetchActiveSession,
    activeCharacterId,
    clearImagePoll,
    closeSocket,
    turnGenerationRef,
    turnAbortControllerRef,
    syncTurnRequestRef,
    resetTransientTurnState,
  ]);

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
    if (fetchSessionAbortRef.current) {
      try {
        fetchSessionAbortRef.current.abort();
      } catch {}
      fetchSessionAbortRef.current = null;
    }
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    clearImagePoll();
    const abortCtrl = new AbortController();
    turnAbortControllerRef.current = abortCtrl;
    const safeScenario = (!scenarioKey || ['none', 'null', 'undefined'].includes(String(scenarioKey).trim().toLowerCase()))
      ? 'fantasy'
      : scenarioKey;

    resetTransientTurnState();
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
    if (fetchSessionAbortRef.current) {
      try {
        fetchSessionAbortRef.current.abort();
      } catch {}
      fetchSessionAbortRef.current = null;
    }
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    clearImagePoll();
    resetTransientTurnState();
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
    if (!sessionObj?.id || !user?.user_id) return null;
    const resumeGen = ++turnGenerationRef.current;
    if (fetchSessionAbortRef.current) {
      try {
        fetchSessionAbortRef.current.abort();
      } catch {}
      fetchSessionAbortRef.current = null;
    }
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    clearImagePoll();
    resetTransientTurnState();
    const abortCtrl = new AbortController();
    turnAbortControllerRef.current = abortCtrl;
    try {
      const res = await apiCall('/api/adventure/resume', {
        method: 'POST',
        signal: abortCtrl.signal,
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: sessionObj.id,
          character_id: character?.id,
        }),
      });
      if (turnGenerationRef.current !== resumeGen) {
        return null;
      }
      const activeSess = res?.session || sessionObj;
      setSession(activeSess);
      if (activeSess?.in_flight_turn) {
        activeTurnIdRef.current = activeSess.in_flight_turn.turn_id || null;
        setProcessingState(true);
        setPendingAction(activeSess.in_flight_turn.action || { label: 'Resolving Action...' });
        setIsThinking(activeSess.in_flight_turn.status === 'thinking');
        armSafetyTimer(245000);
      }
      setPausedOnDashboard(false);
      connectWebSocket(activeSess.id);
      setLastSyncTimestamp(Date.now());
      return activeSess;
    } catch (e) {
      if (e?.isUserAbort || e?.name === 'AbortError' || turnGenerationRef.current !== resumeGen) {
        return null;
      }
      console.error('Failed to resume session slot', e);
      setActionError(e?.message || 'Failed to resume session slot.');
      return null;
    } finally {
      if (turnAbortControllerRef.current === abortCtrl) {
        turnAbortControllerRef.current = null;
      }
    }
  }, [
    user?.user_id,
    character?.id,
    connectWebSocket,
    turnGenerationRef,
    turnAbortControllerRef,
    syncTurnRequestRef,
    activeTurnIdRef,
    clearImagePoll,
    resetTransientTurnState,
    setProcessingState,
    setPendingAction,
    setIsThinking,
    setActionError,
    armSafetyTimer,
  ]);

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
      const isEndingActive =
        activeSessionIdRef.current != null &&
        String(activeSessionIdRef.current) === String(sessionId);
      if (isEndingActive) {
        turnGenerationRef.current += 1;
        if (turnAbortControllerRef.current) {
          try {
            turnAbortControllerRef.current.abort();
          } catch {}
          turnAbortControllerRef.current = null;
        }
        syncTurnRequestRef.current = false;
        activeSessionIdRef.current = null;
        clearImagePoll();
        closeSocket();
        resetTransientTurnState();
      }
      setSession(prev => (prev && String(prev.id) === String(sessionId) ? null : prev));
      fetchActiveSession({ silent: true });
    } catch (e) {
      console.error('Failed to end session slot', e);
    }
  }, [
    user?.user_id,
    fetchActiveSession,
    turnGenerationRef,
    turnAbortControllerRef,
    syncTurnRequestRef,
    clearImagePoll,
    closeSocket,
    resetTransientTurnState,
  ]);

  const endSession = async () => {
    turnGenerationRef.current += 1;
    const endGen = turnGenerationRef.current;
    if (fetchSessionAbortRef.current) {
      try {
        fetchSessionAbortRef.current.abort();
      } catch {
        // ignore abort error
      }
      fetchSessionAbortRef.current = null;
    }
    if (turnAbortControllerRef.current) {
      turnAbortControllerRef.current.abort();
      turnAbortControllerRef.current = null;
    }
    syncTurnRequestRef.current = false;
    if (isValidSessionId(session?.id) && user?.user_id) {
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
    if (turnGenerationRef.current !== endGen) {
      return;
    }
    activeSessionIdRef.current = null;
    clearImagePoll();
    closeSocket();
    setSession(null);
    setPausedOnDashboard(false);
    resetTransientTurnState();
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
