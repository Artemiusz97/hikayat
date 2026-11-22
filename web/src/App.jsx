import { AnimatePresence, motion } from 'motion/react';
import { useAuth } from './hooks/useAuth';
import { useGameSession } from './hooks/useGameSession';
import AuthView from './views/AuthView';
import DashboardView from './views/DashboardView';
import GameView from './views/GameView';
import ScenarioBackdrop from './components/Common/ScenarioBackdrop';
import { EASE_OUT } from './components/Common/MotionPrimitives';
import { useScenarioTheme } from './theme/ThemeProvider';

const Splash = ({ label }) => (
  <div className="flex h-full items-center justify-center p-4">
    <div className="hk-acrylic-pill px-6 py-4 flex items-center gap-3.5 hk-enter">
      <div className="h-6 w-6 rounded-full border-2 border-fantasy-accent/30 border-t-fantasy-accent animate-spin shrink-0" />
      <span className="hk-display text-sm text-gray-100">{label}</span>
    </div>
  </div>
);

function App() {
  const {
    user, character, characters, loading: authLoading,
    loginGuest, loginDiscord, logout, createCharacter, switchCharacter,
    deleteCharacter, refreshCharacter, allocateStatPoint
  } = useAuth();

  const {
    session, setSession, pausedOnDashboard, loading: sessionLoading, processingTurn, pendingAction, isStreaming, isThinking, cancellingTurn, streamingNarrative, streamingState,
    waitingForParty, partyStatus, lastSyncTimestamp, wsStatus,
    partyChatMessages, onlineUserIds, sendPartyChat,
    startSession, joinSession, submitAction, cancelTurn,
    exitToDashboard, resumeSession, resumeSessionSlot, endSession, endSessionById, retryGeneration,
    rerollImage, rerollingImage,
    actionError, clearActionError,
    refreshSession
  } = useGameSession(user, character);

  // Auto theme follows whichever scenario is in focus (active or paused session).
  useScenarioTheme(session);

  const inGame = Boolean(user && !authLoading && session && !pausedOnDashboard && !sessionLoading);

  let viewKey = 'game';
  let view = null;
  if (authLoading) {
    viewKey = 'splash';
    view = <Splash label="Loading..." />;
  } else if (!user) {
    viewKey = 'auth';
    view = <AuthView loginGuest={loginGuest} loginDiscord={loginDiscord} />;
  } else if (sessionLoading && !session && !pausedOnDashboard) {
    viewKey = 'splash';
    view = <Splash label="Summoning Reality..." />;
  } else if (!session || pausedOnDashboard) {
    viewKey = 'dashboard';
    view = (
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
        actionError={actionError}
        clearActionError={clearActionError}
        onSessionLoaded={(s) => {
          setSession(s);
          resumeSession();
        }}
      />
    );
  } else if (sessionLoading) {
    viewKey = 'splash';
    view = <Splash label="Summoning Reality..." />;
  } else {
    viewKey = 'game';
    view = (
      <GameView
        user={user}
        character={character}
        refreshCharacter={refreshCharacter}
        allocateStatPoint={allocateStatPoint}
        session={session}
        setSession={setSession}
        refreshSession={refreshSession}
        lastSyncTimestamp={lastSyncTimestamp}
        wsStatus={wsStatus}
        processingTurn={processingTurn}
        pendingAction={pendingAction}
        isStreaming={isStreaming}
        isThinking={isThinking}
        cancellingTurn={cancellingTurn}
        streamingNarrative={streamingNarrative}
        streamingState={streamingState}
        waitingForParty={waitingForParty}
        partyStatus={partyStatus}
        partyChatMessages={partyChatMessages}
        onlineUserIds={onlineUserIds}
        sendPartyChat={sendPartyChat}
        submitAction={submitAction}
        cancelTurn={cancelTurn}
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

  return (
    <div className="relative h-full w-full overflow-hidden">
      <ScenarioBackdrop session={inGame ? session : null} isMenu={!inGame} />
      <AnimatePresence mode="wait">
        <motion.div
          key={viewKey}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22, ease: EASE_OUT }}
          className="relative h-full w-full min-w-0"
        >
          {view}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export default App;
