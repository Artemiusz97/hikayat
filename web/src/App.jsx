import React from 'react';
import { useAuth } from './hooks/useAuth';
import { useGameSession } from './hooks/useGameSession';
import AuthView from './views/AuthView';
import DashboardView from './views/DashboardView';
import GameView from './views/GameView';

function App() {
  const {
    user, character, characters, loading: authLoading,
    loginGuest, loginDiscord, logout, createCharacter, switchCharacter,
    deleteCharacter, regenerateStarterGear, refreshCharacter, allocateStatPoint
  } = useAuth();

  const {
    session, setSession, pausedOnDashboard, loading: sessionLoading, processingTurn, pendingAction, isStreaming, streamingNarrative, streamingState,
    waitingForParty, partyStatus, lastSyncTimestamp,
    partyChatMessages, onlineUserIds, sendPartyChat,
    startSession, joinSession, submitAction,
    exitToDashboard, resumeSession, endSession, retryGeneration,
    rerollImage, rerollingImage,
    actionError, clearActionError,
    refreshSession
  } = useGameSession(user, character);

  if (authLoading) {
    return <div className="flex h-screen items-center justify-center text-fantasy-accent">Loading...</div>;
  }

  if (!user) {
    return <AuthView loginGuest={loginGuest} loginDiscord={loginDiscord} />;
  }

  // Cold-start initial loading: Only show full-screen loader when there is no session and user is not on dashboard
  if (sessionLoading && !session && !pausedOnDashboard) {
    return <div className="flex h-screen items-center justify-center text-fantasy-accent">Summoning Reality...</div>;
  }

  if (!session || pausedOnDashboard) {
    return (
      <DashboardView
        user={user}
        character={character}
        characters={characters}
        logout={logout}
        createCharacter={createCharacter}
        switchCharacter={switchCharacter}
        deleteCharacter={deleteCharacter}
        startSession={startSession}
        joinSession={joinSession}
        activeSession={session}
        onResumeSession={resumeSession}
        onEndSession={endSession}
        refreshCharacter={refreshCharacter}
        refreshSession={refreshSession}
        onSessionLoaded={(s) => {
          setSession(s);
          resumeSession();
        }}
      />
    );
  }

  if (sessionLoading) {
    return <div className="flex h-screen items-center justify-center text-fantasy-accent">Summoning Reality...</div>;
  }

  return (
    <GameView
      user={user}
      character={character}
      refreshCharacter={refreshCharacter}
      allocateStatPoint={allocateStatPoint}
      session={session}
      setSession={setSession}
      lastSyncTimestamp={lastSyncTimestamp}
      processingTurn={processingTurn}
      pendingAction={pendingAction}
      isStreaming={isStreaming}
      streamingNarrative={streamingNarrative}
      streamingState={streamingState}
      waitingForParty={waitingForParty}
      partyStatus={partyStatus}
      partyChatMessages={partyChatMessages}
      onlineUserIds={onlineUserIds}
      sendPartyChat={sendPartyChat}
      submitAction={submitAction}
      exitToDashboard={exitToDashboard}
      endSession={endSession}
      retryGeneration={retryGeneration}
      rerollImage={rerollImage}
      rerollingImage={rerollingImage}
      actionError={actionError}
      clearActionError={clearActionError}
      leaveSession={logout}
    />
  );
}

export default App;
