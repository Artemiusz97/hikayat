import { useState, useCallback, useEffect, useRef } from 'react';
import { apiCall } from '../api/client';

export const useGameSession = (user) => {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processingTurn, setProcessingTurn] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingNarrative, setStreamingNarrative] = useState(null);
  const [streamingState, setStreamingState] = useState(null);
  const [waitingForParty, setWaitingForParty] = useState(false);
  const [partyStatus, setPartyStatus] = useState(null);
  const [lastSyncTimestamp, setLastSyncTimestamp] = useState(0);
  const [partyChatMessages, setPartyChatMessages] = useState([]);
  const [onlineUserIds, setOnlineUserIds] = useState([]);
  const [pausedOnDashboard, setPausedOnDashboard] = useState(false);

  const socketRef = useRef(null);

  const fetchActiveSession = useCallback(async () => {
    if (!user) return;
    try {
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
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchActiveSession();
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [fetchActiveSession]);

  const connectWebSocket = (sessionId) => {
    if (
      socketRef.current &&
      socketRef.current._sessionId === sessionId &&
      (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    if (socketRef.current) socketRef.current.close();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/session/${sessionId}?user_id=${user.user_id}`;

    const ws = new WebSocket(wsUrl);
    ws._sessionId = sessionId;
    socketRef.current = ws;

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
      } else if (data.type === 'PICK_LOCKED') {
        setPartyStatus({
          lockedCount: data.locked_picks || 0,
          total: data.total || 0,
          waitingCount: data.waiting_count
        });
      } else if (data.type === 'SCENE_IMAGE') {
        setSession(prev => prev ? { ...prev, scene_image_url: data.image_url } : prev);
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
      }
    };

    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'PING' }));
      }
    }, 15000);

    ws.onclose = () => clearInterval(interval);
  };

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
    const data = await apiCall('/api/adventure/start', {
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
    setPausedOnDashboard(false);
    setPartyChatMessages([]);
    connectWebSocket(data.session.id);
    setLastSyncTimestamp(Date.now());
    return data;
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
    try {
      const payload = {
        session_id: session.id,
        user_id: user.user_id,
        choice_index: actionData?.choice_index !== undefined ? actionData.choice_index : null,
        custom_action_text: actionData?.custom_action_text || actionData?.custom_text || null,
        direct_choice: actionData?.direct_choice || null,
        combat_target: actionData?.combat_target || null,
        action: actionData
      };
      const data = await apiCall('/api/adventure/action', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      if (data.status === 'waiting_for_party') {
        setWaitingForParty(true);
        setPartyStatus({
          lockedCount: data.locked_picks,
          total: data.total
        });
        setProcessingTurn(false);
      } else {
        setSession(data.session);
        setWaitingForParty(false);
        setProcessingTurn(false);
        setLastSyncTimestamp(Date.now());
      }
    } catch (e) {
      setProcessingTurn(false);
      throw e;
    }
  };

  const exitToDashboard = useCallback(() => {
    setPausedOnDashboard(true);
  }, []);

  const resumeSession = useCallback(() => {
    setPausedOnDashboard(false);
  }, []);

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

  return {
    session,
    setSession,
    pausedOnDashboard,
    loading,
    processingTurn,
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
    endSession,
    retryGeneration,
    refreshSession: fetchActiveSession
  };
};
