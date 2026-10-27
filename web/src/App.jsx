import React from 'react';
import { useAuth } from './hooks/useAuth';
import { useGameSession } from './hooks/useGameSession';
import AuthView from './views/AuthView';
import DashboardView from './views/DashboardView';
import GameView from './views/GameView';
import { useScenarioTheme } from './theme/ThemeProvider';

const Splash = ({ label }) => (
  <div className="flex h-full items-center justify-center">
    <div className="flex flex-col items-center gap-4 hk-enter">
      <div className="h-10 w-10 rounded-full border-2 border-fantasy-accent/25 border-t-fantasy-accent animate-spin" />
      <span className="hk-display text-sm text-gray-400">{label}</span>
    </div>
  </div>
);

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
    exitToDashboard, resumeSession, resumeSessionSlot, endSession, endSessionById, retryGeneration,
    rerollImage, rerollingImage,
    actionError, clearActionError,
    refreshSession
  } = useGameSession(user, character);

  // Auto theme follows whichever scenario is in focus (active or paused session).
  useScenarioTheme(session);

  if (authLoading) {
    return <Splash label="Loading..." />;
  }

  if (!user) {
    return <AuthView loginGuest={loginGuest} loginDiscord={loginDiscord} />;
  }

  // Cold-start initial loading: Only show full-screen loader when there is no session and user is not on dashboard
  if (sessionLoading && !session && !pausedOnDashboard) {
    return <Splash label="Summoning Reality..." />;
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
        onResumeSlot={resumeSessionSlot}
        onEndSession={endSession}
        onEndSlot={endSessionById}
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
    return <Splash label="Summoning Reality..." />;
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
