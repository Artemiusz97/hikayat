import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../../api/client';
import { isAutoSceneImageGen } from './useSceneImagePoll';

export const useTurnTransport = ({
  session,
  user,
  setSession,
  setWaitingForParty,
  setPartyStatus,
  setLastSyncTimestamp,
  setActionError,
  pollForSceneImage,
  socketRef,
}) => {
  const [processingTurn, setProcessingTurn] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [cancellingTurn, setCancellingTurn] = useState(false);
  const [streamingNarrative, setStreamingNarrative] = useState(null);
  const [streamingState, setStreamingState] = useState(null);

  const safetyTimerRef = useRef(null);
  const turnAbortControllerRef = useRef(null);
  const syncTurnRequestRef = useRef(false);
  const processingTurnRef = useRef(false);
  const pendingAsyncPostRef = useRef(null);
  const activeTurnIdRef = useRef(null);
  const turnGenerationRef = useRef(0);
  const completedTurnIdsRef = useRef(new Set());

  useEffect(() => {
    processingTurnRef.current = processingTurn;
  }, [processingTurn]);

  const setProcessingState = useCallback((next) => {
    processingTurnRef.current = next;
    setProcessingTurn(next);
  }, []);

  const recordCompletedTurnId = useCallback((turnId) => {
    if (!turnId) return;
    if (completedTurnIdsRef.current.size > 32) {
      completedTurnIdsRef.current.clear();
    }
    completedTurnIdsRef.current.add(turnId);
  }, []);

  const acceptAsyncTurn = useCallback((data, postPromise, canAsyncWs) => {
    const alreadyFinished =
      !processingTurnRef.current ||
      (canAsyncWs && pendingAsyncPostRef.current !== postPromise) ||
      Boolean(data?.turn_id && completedTurnIdsRef.current.has(data.turn_id));
    if (alreadyFinished) {
      return false;
    }
    activeTurnIdRef.current = data?.turn_id || null;
    return true;
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

  useEffect(() => {
    if (!processingTurn || !session?.id || session.id === 'embarking' || !user?.user_id) {
      return;
    }
    const pollAbort = new AbortController();
    const pollId = setInterval(async () => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        return;
      }
      try {
        const res = await apiCall(`/api/adventure/active-session/${user.user_id}`, {
          signal: pollAbort.signal,
        });
        if (pollAbort.signal.aborted) return;
        if (res?.session) {
          if (res.session.in_flight_turn) {
            if (!processingTurnRef.current) return;
            setIsThinking(res.session.in_flight_turn.status === 'thinking');
          } else if (processingTurnRef.current && !syncTurnRequestRef.current) {
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
            activeTurnIdRef.current = null;
            if (isAutoSceneImageGen(res.session) && !res.session?.scene_image_url) {
              pollForSceneImage(res.session.id);
            }
          }
        }
      } catch {}
    }, 5000);
    return () => {
      pollAbort.abort();
      clearInterval(pollId);
    };
  }, [
    processingTurn,
    session?.id,
    user?.user_id,
    socketRef,
    clearSafetyTimer,
    pollForSceneImage,
    setProcessingState,
    setSession,
    setLastSyncTimestamp,
    setActionError,
  ]);

  const runTurnRequest = async ({
    endpoint,
    body,
    optimisticAction,
    canAsyncWs,
    resetStreamBeforeRequest = false,
    onSyncSuccess,
    onHttpError,
  }) => {
    turnGenerationRef.current += 1;
    setProcessingState(true);
    armSafetyTimer(245000);
    if (resetStreamBeforeRequest) {
      setIsStreaming(false);
      setStreamingNarrative(null);
      setStreamingState(null);
    }
    setIsThinking(false);
    setPendingAction(optimisticAction);
    setActionError(null);

    let asyncAccepted = false;
    activeTurnIdRef.current = null;
    const abortCtrl = new AbortController();
    turnAbortControllerRef.current = abortCtrl;
    syncTurnRequestRef.current = !canAsyncWs;
    let postPromise = null;

    try {
      postPromise = apiCall(endpoint, {
        timeout: 240000,
        method: 'POST',
        signal: abortCtrl.signal,
        body: JSON.stringify(body),
      });
      if (canAsyncWs) {
        pendingAsyncPostRef.current = postPromise;
      }
      const data = await postPromise;
      if (data?.status === 'accepted') {
        if (acceptAsyncTurn(data, postPromise, canAsyncWs)) {
          asyncAccepted = true;
        }
        return data;
      }
      if (onSyncSuccess) {
        onSyncSuccess(data);
      }
      return data;
    } catch (e) {
      if (e?.name === 'AbortError' || e?.isUserAbort) {
        if (!resetStreamBeforeRequest) {
          setIsStreaming(false);
          setStreamingNarrative(null);
          setStreamingState(null);
        }
        return null;
      }
      if (onHttpError) {
        return await onHttpError(e, {
          markAsyncAccepted: () => {
            asyncAccepted = true;
          },
        });
      }
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

  const submitAction = async (actionData) => {
    if (processingTurnRef.current) return;
    const prevTurnCount = session?.turn_count ?? 0;
    const prevHistLen = Array.isArray(session?.history) ? session.history.length : 0;
    const canAsyncWs = Boolean(socketRef.current && socketRef.current.readyState === WebSocket.OPEN);
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
      async_ws: canAsyncWs,
    };

    return runTurnRequest({
      endpoint: '/api/adventure/action',
      body: payload,
      optimisticAction: actionData,
      canAsyncWs,
      onSyncSuccess: (data) => {
        if (data.status === 'waiting_for_party') {
          setWaitingForParty(true);
          setPartyStatus({
            lockedCount: data.locked_picks,
            total: data.total,
          });
        } else {
          setSession(prev => ({
            ...data.session,
            scene_image_url: data.session?.scene_image_url || prev?.scene_image_url || null,
          }));
          setWaitingForParty(false);
          setIsStreaming(false);
          setStreamingNarrative(null);
          setStreamingState(null);
          setLastSyncTimestamp(Date.now());
          if (isAutoSceneImageGen(data.session) && !data.session?.scene_image_url) {
            pollForSceneImage(data.session.id);
          }
        }
      },
      onHttpError: async (e, { markAsyncAccepted }) => {
        console.warn('Action API error or timeout, checking active session recovery...', e);
        const errMsg = e?.message || 'The action could not be completed. Please try again.';
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
              scene_image_url: recoveryData.session?.scene_image_url || prev?.scene_image_url || null,
            }));
            setWaitingForParty(false);
            if (inFlight) {
              markAsyncAccepted();
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
            return undefined;
          }
        } catch (recErr) {
          console.error('State recovery check failed:', recErr);
        }
        setIsStreaming(false);
        setStreamingNarrative(null);
        setStreamingState(null);
        throw e;
      },
    });
  };

  const retryGeneration = async () => {
    if (!session?.id || !user?.user_id || processingTurnRef.current) return null;
    const hasHistory = Array.isArray(session?.history) && session.history.length > 0;
    const canAsyncWs = Boolean(
      hasHistory &&
      socketRef.current &&
      socketRef.current.readyState === WebSocket.OPEN
    );
    return runTurnRequest({
      endpoint: '/api/adventure/retry',
      body: {
        session_id: session.id,
        user_id: user.user_id,
        async_ws: canAsyncWs,
      },
      optimisticAction: {
        label: 'Regenerating scene...',
        ...(hasHistory ? {} : { isSyncTurnZeroRetry: true }),
      },
      canAsyncWs,
      resetStreamBeforeRequest: true,
      onSyncSuccess: (data) => {
        if (data?.session) {
          setSession(data.session);
          setLastSyncTimestamp(Date.now());
          if (isAutoSceneImageGen(data.session) && !data.session?.scene_image_url) {
            pollForSceneImage(data.session.id);
          }
        }
      },
      onHttpError: async (e) => {
        const errMsg = e?.message || 'Failed to regenerate narration. Please try again.';
        setActionError(errMsg);
        return null;
      },
    });
  };

  const cancelTurn = useCallback(async () => {
    if (!session?.id || session.id === 'embarking' || !user?.user_id || cancellingTurn) return;
    setCancellingTurn(true);
    const cancelGen = turnGenerationRef.current;
    const targetTurnId = activeTurnIdRef.current;
    if (pendingAsyncPostRef.current) {
      try {
        await Promise.race([
          pendingAsyncPostRef.current.catch(() => {}),
          new Promise((resolve) => setTimeout(resolve, 400)),
        ]);
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
        }),
      });
      recordCompletedTurnId(res?.turn_id || targetTurnId);
      if (turnGenerationRef.current === cancelGen) {
        clearSafetyTimer();
        activeTurnIdRef.current = null;
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
            scene_image_url: res.session?.scene_image_url || prev?.scene_image_url || null,
          }));
          setLastSyncTimestamp(Date.now());
        }
      }
    } catch (e) {
      console.error('Failed to cancel in-flight turn:', e);
      if (turnGenerationRef.current === cancelGen) {
        setActionError(e?.message || 'Failed to cancel turn.');
      }
    } finally {
      if (turnGenerationRef.current === cancelGen) {
        setCancellingTurn(false);
      }
    }
  }, [
    session?.id,
    user?.user_id,
    cancellingTurn,
    clearSafetyTimer,
    recordCompletedTurnId,
    setProcessingState,
    setWaitingForParty,
    setActionError,
    setSession,
    setLastSyncTimestamp,
  ]);

  return {
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
  };
};
