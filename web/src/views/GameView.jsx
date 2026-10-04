import React, { useState, useEffect } from 'react';
import { Menu, LogOut, User, Package, Users, Compass, BookOpen, X, Smartphone, Sliders, Bookmark, Map, ArrowLeft, FlagOff, ScrollText, Share2, Check } from 'lucide-react';
import { apiCall } from '../api/client';
import CharacterSheet from '../components/Sidebar/CharacterSheet';
import InventoryPanel from '../components/Sidebar/InventoryPanel';
import PartyWidget from '../components/Sidebar/PartyWidget';
import QuestLogPanel from '../components/Sidebar/QuestLogPanel';
import CodexPanel from '../components/Sidebar/CodexPanel';
import WorldOutcomeSidebar from '../components/Sidebar/WorldOutcomeSidebar';
import PhoneModal from '../components/Phone/PhoneModal';
import MerchantModal from '../components/Merchant/MerchantModal';
import SavesModal from '../components/Saves/SavesModal';
import SettingsModal from '../components/Settings/SettingsModal';
import WorldMapModal from '../components/Modals/WorldMapModal';
import StoryFeed from '../components/StoryFeed/StoryFeed';
import ActionPanel from '../components/ActionPanel/ActionPanel';
import { useInventory } from '../hooks/useInventory';
import { useCodex } from '../hooks/useCodex';
import { usePhone } from '../hooks/usePhone';
import { useSettings } from '../hooks/useSettings';

const GameView = ({
  user,
  character,
  refreshCharacter,
  allocateStatPoint,
  session,
  setSession,
  lastSyncTimestamp,
  processingTurn,
  isStreaming,
  streamingNarrative,
  streamingState,
  waitingForParty,
  partyStatus,
  partyChatMessages = [],
  onlineUserIds = [],
  sendPartyChat,
  submitAction,
  exitToDashboard,
  endSession,
  retryGeneration,
  leaveSession
}) => {
  const [activeSidebarTab, setActiveSidebarTab] = useState('hero'); // 'hero' | 'inventory' | 'party' | 'quests' | 'codex'
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [mobileOutcomeOpen, setMobileOutcomeOpen] = useState(false);
  const [phoneModalOpen, setPhoneModalOpen] = useState(false);
  const [merchantModalOpen, setMerchantModalOpen] = useState(false);
  const [savesModalOpen, setSavesModalOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [worldMapModalOpen, setWorldMapModalOpen] = useState(false);
  const [worldMapTargetLocation, setWorldMapTargetLocation] = useState(null);
  const [selectedCombatTarget, setSelectedCombatTarget] = useState(null);
  const [headerCopied, setHeaderCopied] = useState(false);

  const handleShareAdventure = async () => {
    try {
      let shareUrl = window.location.origin;
      try {
        const res = await apiCall('/api/server/public-url');
        if (res?.public_url) {
          shareUrl = res.public_url;
        }
      } catch {
        // fallback
      }
      const inviteMsg = `${shareUrl}${session?.id ? ` (Invite Code: ${session.id})` : ''}`;
      await navigator.clipboard.writeText(inviteMsg);
      setHeaderCopied(true);
      setTimeout(() => setHeaderCopied(false), 2500);
    } catch (e) {
      console.error('Failed to copy adventure link:', e);
    }
  };

  const inventory = useInventory(user);
  const codex = useCodex(session?.id, user);
  const phone = usePhone(session?.id, user);
  const settings = useSettings(user?.user_id);

  // Sync selectedCombatTarget with first living enemy in session.nearby_enemies
  useEffect(() => {
    const enemies = (session?.nearby_enemies || session?.monsters || []).filter(e => e && e.name && (e.hp ?? 1) > 0);
    if (enemies.length === 0) {
      setSelectedCombatTarget(null);
    } else if (!selectedCombatTarget || !enemies.some(e => e.name === selectedCombatTarget)) {
      setSelectedCombatTarget(enemies[0].name);
    }
  }, [session?.nearby_enemies, session?.monsters, selectedCombatTarget]);

  const refreshAllSidebars = () => {
    refreshCharacter();
    inventory.refreshInventory();
    codex.refreshCodex();
    phone.refreshPhone();
  };

  // Real-time WebSocket sync: whenever STREAM_END or NEW_SCENE arrives, refresh sidebars
  useEffect(() => {
    if (lastSyncTimestamp > 0) {
      refreshAllSidebars();
    }
  }, [lastSyncTimestamp]);

  const handleAction = async (actionData) => {
    await submitAction(actionData);
    refreshAllSidebars();
  };

  const handleFastTravel = async (destination) => {
    if (!destination || processingTurn) return;
    await handleAction({
      custom_action_text: `I travel to ${destination}.`,
    });
  };

  const handleCastSpell = async (spell) => {
    if (!spell?.name || processingTurn) return;
    await handleAction({
      custom_action_text: `Cast ${spell.name}`,
      stat: 'INT',
      mp_cost: Number(spell.mp_cost || 0)
    });
  };

  const handleSessionLoaded = (loadedSession) => {
    if (setSession && loadedSession) {
      setSession(loadedSession);
    }
    refreshAllSidebars();
  };

  const handleRetryGeneration = async () => {
    if (!retryGeneration) return;
    await retryGeneration();
    refreshAllSidebars();
  };

  const activeQuestCount = (codex.activeStoryQuest ? 1 : 0) + codex.quests.filter(q => q.status !== 'Completed').length;
  const contactsCount = codex.contacts?.length || null;
  const hasActiveMerchant = Boolean(session?.merchant?.available || session?.merchant?.active);

  const tabs = [
    { id: 'hero', label: 'Hero', icon: User, badge: character?.pending_stat_points ? '!' : null },
    { id: 'inventory', label: 'Pack', icon: Package, badge: inventory.items?.length || null },
    { id: 'party', label: 'Party', icon: Users, badge: (session.party_members?.length || 1) + (session.party_npcs?.length || 0) },
    { id: 'quests', label: 'Quests', icon: Compass, badge: activeQuestCount || null },
    { id: 'codex', label: 'Codex', icon: BookOpen, badge: contactsCount }
  ];

  const renderSidebarContent = () => {
    switch (activeSidebarTab) {
      case 'inventory':
        return (
          <InventoryPanel
            inventoryHook={inventory}
            onRefreshCharacter={refreshCharacter}
            onRefreshCodex={codex.refreshCodex}
            sessionId={session?.id}
            session={session}
          />
        );
      case 'party':
        return (
          <PartyWidget
            session={session}
            currentUserId={user?.user_id}
            characterName={character?.name || user?.display_name}
            onlineUserIds={onlineUserIds}
            partyChatMessages={partyChatMessages}
            onSendPartyChat={sendPartyChat}
            onSessionUpdated={handleSessionLoaded}
            onTriggerAction={handleAction}
          />
        );
      case 'quests':
        return (
          <QuestLogPanel
            codexHook={codex}
            onRefreshCharacter={refreshCharacter}
            character={character}
            onOpenWorldMap={(targetLoc) => {
              setWorldMapTargetLocation(typeof targetLoc === 'string' ? targetLoc : null);
              setMobileDrawerOpen(false);
              setWorldMapModalOpen(true);
            }}
          />
        );
      case 'codex':
        return (
          <CodexPanel
            codexHook={codex}
            session={session}
            user={user}
            onSessionUpdated={handleSessionLoaded}
            onRefreshCharacter={refreshCharacter}
            onOpenMerchant={() => setMerchantModalOpen(true)}
            onTriggerAction={handleAction}
          />
        );
      case 'hero':
      default:
        return (
          <CharacterSheet
            character={character}
            onAllocateStat={allocateStatPoint}
            onCastSpell={handleCastSpell}
            processingTurn={processingTurn}
          />
        );
    }
  };

  return (
    <div className="flex h-screen bg-black overflow-hidden font-sans">

      {/* Sidebar (Desktop) */}
      <aside className="hidden md:flex w-[440px] xl:w-[480px] flex-col bg-fantasy-panel border-r border-fantasy-border h-full shrink-0 transition-all duration-200">

        {/* Top Header */}
        <div className="p-3.5 border-b border-fantasy-border flex justify-between items-center bg-black/40">
          <div className="flex items-center gap-2">
            <Compass size={18} className="text-fantasy-accent" />
            <div>
              <h1 className="font-rpg font-bold text-fantasy-accent text-base leading-tight">Hikayat</h1>
              <p className="text-[11px] text-gray-500 capitalize">{session.scenario || 'Fantasy'} Realm</p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {/* Contextual Phone OS Button */}
            {phone.isSupported && (
              <button
                onClick={() => setPhoneModalOpen(true)}
                className="flex items-center gap-1 px-2 py-1 bg-black/60 hover:bg-neutral-900 border border-neutral-700 hover:border-pink-500/60 rounded-lg text-xs font-semibold text-gray-200 transition-all shadow-sm relative group"
                title={`Open ${phone.branding?.device_name || 'Smartphone'}`}
              >
                <Smartphone size={13} className="text-pink-400" />
                <span className="font-mono text-[11px]">Phone</span>
                {(phone.appointments?.length > 0 || phone.mediaGallery?.length > 0) && (
                  <span className="w-2 h-2 rounded-full bg-pink-400 animate-pulse" />
                )}
              </button>
            )}

            {/* Share Public Adventure Link */}
            <button
              onClick={handleShareAdventure}
              className={`p-1.5 rounded transition-colors ${
                headerCopied
                  ? 'text-green-400 bg-green-950/40 border border-green-500/40'
                  : 'text-gray-500 hover:text-fantasy-accent hover:bg-black/40'
              }`}
              title={headerCopied ? "Link Copied to Clipboard!" : "Share Adventure Link (Invite Friends)"}
            >
              {headerCopied ? <Check size={14} className="text-green-400" /> : <Share2 size={14} />}
            </button>

            {/* Save / Load Checkpoints Button */}
            <button
              onClick={() => setSavesModalOpen(true)}
              className="p-1.5 text-gray-500 hover:text-fantasy-accent rounded hover:bg-black/40 transition-colors"
              title="Save / Load Checkpoints"
            >
              <Bookmark size={14} />
            </button>

            <button
              onClick={() => setSettingsModalOpen(true)}
              className="p-1.5 text-gray-500 hover:text-fantasy-accent rounded hover:bg-black/40 transition-colors"
              title="Preferences & Streaming Settings"
            >
              <Sliders size={14} />
            </button>

            {exitToDashboard && (
              <button
                onClick={exitToDashboard}
                className="p-1.5 text-gray-400 hover:text-fantasy-accent rounded hover:bg-black/40 transition-colors"
                title="Exit to Dashboard (Keep Adventure Active)"
              >
                <ArrowLeft size={14} />
              </button>
            )}

            {endSession && (
              <button
                onClick={endSession}
                className="p-1.5 text-amber-500/80 hover:text-red-400 rounded hover:bg-black/40 transition-colors"
                title="End Adventure"
              >
                <FlagOff size={14} />
              </button>
            )}

            <button
              onClick={leaveSession}
              className="p-1.5 text-gray-500 hover:text-red-400 rounded hover:bg-black/40 transition-colors"
              title="Log Out"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>

        {/* Tab Navigation Switcher */}
        <div className="flex border-b border-fantasy-border bg-black/60 p-1 gap-1">
          {tabs.map(tab => {
            const Icon = tab.icon;
            const isActive = activeSidebarTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveSidebarTab(tab.id)}
                className={`flex-1 flex flex-col items-center justify-center py-1.5 px-0.5 rounded text-[10px] font-semibold uppercase tracking-wider transition-all relative ${
                  isActive
                    ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-black/30'
                }`}
              >
                <div className="flex items-center gap-1">
                  <Icon size={13} />
                  {tab.badge && (
                    <span className={`text-[8px] px-1 rounded-full font-bold leading-none ${
                      tab.badge === '!'
                        ? 'bg-amber-500 text-black animate-bounce'
                        : 'bg-black/80 text-gray-300 border border-fantasy-border'
                    }`}>
                      {tab.badge}
                    </span>
                  )}
                </div>
                <span className="mt-0.5">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Scrollable Tab Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-3">
          {renderSidebarContent()}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full relative min-w-0">

        {/* Mobile Header */}
        <header className="md:hidden flex justify-between items-center p-3 bg-fantasy-panel border-b border-fantasy-border z-10">
          <div className="flex items-center gap-2">
            <Compass size={18} className="text-fantasy-accent" />
            <h1 className="font-rpg font-bold text-fantasy-accent text-sm">Hikayat</h1>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setWorldMapModalOpen(true)}
              className="p-1.5 bg-black/40 border border-fantasy-border rounded text-fantasy-accent flex items-center text-xs"
              title="World Atlas & Fast-Travel"
            >
              <Map size={15} />
            </button>
            <button
              onClick={() => setMobileOutcomeOpen(true)}
              className="p-1.5 bg-black/40 border border-fantasy-border rounded text-amber-300 flex items-center text-xs"
              title="World Context & Turn Outcomes"
            >
              <ScrollText size={15} />
            </button>
            {phone.isSupported && (
              <button
                onClick={() => setPhoneModalOpen(true)}
                className="p-1.5 bg-black/40 border border-neutral-700 rounded text-pink-400 flex items-center text-xs"
                title="Phone OS"
              >
                <Smartphone size={15} />
              </button>
            )}
            <button
              onClick={handleShareAdventure}
              className={`p-1.5 bg-black/40 border rounded transition-colors ${
                headerCopied
                  ? 'text-green-400 border-green-500/40'
                  : 'border-fantasy-border text-gray-300 hover:text-fantasy-accent'
              }`}
              title={headerCopied ? "Link Copied!" : "Share Adventure Link"}
            >
              {headerCopied ? <Check size={15} className="text-green-400" /> : <Share2 size={15} />}
            </button>
            <button
              onClick={() => setSavesModalOpen(true)}
              className="p-1.5 bg-black/40 border border-fantasy-border rounded text-gray-300 hover:text-fantasy-accent"
              title="Checkpoints"
            >
              <Bookmark size={15} />
            </button>
            <button
              onClick={() => setSettingsModalOpen(true)}
              className="p-1.5 bg-black/40 border border-fantasy-border rounded text-gray-300 hover:text-fantasy-accent"
              title="Settings & Streaming"
            >
              <Sliders size={15} />
            </button>
            <button
              onClick={() => setMobileDrawerOpen(true)}
              className="p-1.5 bg-black/40 border border-fantasy-border rounded text-gray-300 hover:text-fantasy-accent flex items-center gap-1 text-xs"
            >
              <Menu size={16} />
            </button>
            {exitToDashboard && (
              <button onClick={exitToDashboard} className="text-gray-400 hover:text-fantasy-accent p-1" title="Exit to Dashboard">
                <ArrowLeft size={16} />
              </button>
            )}
            {endSession && (
              <button onClick={endSession} className="text-amber-500 hover:text-red-400 p-1" title="End Adventure">
                <FlagOff size={16} />
              </button>
            )}
            <button onClick={leaveSession} className="text-gray-500 hover:text-red-400 p-1" title="Log Out">
              <LogOut size={16}/>
            </button>
          </div>
        </header>

        {/* Narrative Feed */}
        <div className="flex-1 min-h-0 overflow-hidden relative">
          <div className="absolute inset-0 bg-fantasy-dark/80 backdrop-blur-sm z-0"></div>
          <StoryFeed
            history={session.history}
            currentScene={session}
            isStreaming={isStreaming}
            streamingNarrative={streamingNarrative}
            streamingState={streamingState}
            selectedCombatTarget={selectedCombatTarget}
            onSelectCombatTarget={setSelectedCombatTarget}
          />
        </div>

        {/* Action Panel */}
        <ActionPanel
          choices={session.choices || []}
          session={session}
          selectedCombatTarget={selectedCombatTarget}
          onSelectCombatTarget={setSelectedCombatTarget}
          onAction={handleAction}
          onRetry={handleRetryGeneration}
          onOpenMerchant={() => setMerchantModalOpen(true)}
          showPercentages={(settings.settings?.show_percentages ?? 1) === 1}
          processing={processingTurn}
          isStreaming={isStreaming}
          waitingForParty={waitingForParty}
          partyStatus={partyStatus}
        />
      </main>

      {/* Right Sidebar: World Context (Map, Day/Time, Present NPCs) & Dedicated Outcomes/Changes Log */}
      <aside className="hidden lg:flex w-[390px] xl:w-[440px] 2xl:w-[480px] flex-col bg-fantasy-panel border-l border-fantasy-border h-full shrink-0 transition-all duration-200">
        <WorldOutcomeSidebar
          session={session}
          onOpenWorldMap={() => setWorldMapModalOpen(true)}
        />
      </aside>

      {/* Mobile Drawer Backdrop & Left Drawer */}
      {mobileDrawerOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setMobileDrawerOpen(false)}
          />
          <div className="relative w-80 max-w-[85vw] bg-fantasy-panel border-r border-fantasy-border h-full flex flex-col z-10">
            <div className="p-3.5 border-b border-fantasy-border flex justify-between items-center bg-black/40">
              <h2 className="font-rpg font-bold text-fantasy-accent text-sm">Journal & Systems</h2>
              <button
                onClick={() => setMobileDrawerOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-200"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex border-b border-fantasy-border bg-black/60 p-1 gap-1">
              {tabs.map(tab => {
                const Icon = tab.icon;
                const isActive = activeSidebarTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveSidebarTab(tab.id)}
                    className={`flex-1 flex flex-col items-center justify-center py-1 rounded text-[10px] font-semibold uppercase tracking-wider transition-all ${
                      isActive
                        ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                        : 'text-gray-400'
                    }`}
                  >
                    <Icon size={12} />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar p-3">
              {renderSidebarContent()}
            </div>
          </div>
        </div>
      )}

      {/* Mobile/Tablet Right Drawer for World Context & Outcomes */}
      {mobileOutcomeOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex justify-end">
          <div
            className="fixed inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setMobileOutcomeOpen(false)}
          />
          <div className="relative w-[390px] max-w-[90vw] bg-fantasy-panel border-l border-fantasy-border h-full flex flex-col z-10">
            <div className="p-3 border-b border-fantasy-border flex justify-between items-center bg-black/60">
              <h2 className="font-rpg font-bold text-fantasy-accent text-sm">World & Outcomes</h2>
              <button
                onClick={() => setMobileOutcomeOpen(false)}
                className="p-1 text-gray-400 hover:text-gray-200"
              >
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <WorldOutcomeSidebar
                session={session}
                onOpenWorldMap={() => {
                  setMobileOutcomeOpen(false);
                  setWorldMapModalOpen(true);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* World Map & Fast-Travel Modal */}
      <WorldMapModal
        isOpen={worldMapModalOpen}
        onClose={() => {
          setWorldMapModalOpen(false);
          setWorldMapTargetLocation(null);
        }}
        session={session}
        user={user}
        onTravel={handleFastTravel}
        initialTargetLocation={worldMapTargetLocation}
      />

      {/* Merchant Emporium Modal */}
      <MerchantModal
        isOpen={merchantModalOpen}
        onClose={() => setMerchantModalOpen(false)}
        session={session}
        user={user}
        onRefreshCodex={codex.refreshCodex}
        onTransactionComplete={() => {
          refreshCharacter();
          inventory.refreshInventory();
        }}
      />

      {/* Smartphone OS Modal */}
      <PhoneModal
        isOpen={phoneModalOpen}
        onClose={() => setPhoneModalOpen(false)}
        phoneHook={phone}
        codexHook={codex}
        session={session}
        user={user}
        onRefreshInventory={inventory.refreshInventory}
        onRefreshCodex={codex.refreshCodex}
        onRefreshCharacter={refreshCharacter}
      />

      {/* Save / Load Checkpoints Modal */}
      <SavesModal
        isOpen={savesModalOpen}
        onClose={() => setSavesModalOpen(false)}
        user={user}
        onSessionLoaded={handleSessionLoaded}
      />

      {/* Chronicle Preferences & Streaming Settings Modal */}
      <SettingsModal
        isOpen={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        settingsHook={settings}
        user={user}
        session={session}
        onSessionUpdated={handleSessionLoaded}
        onRefreshCharacter={refreshCharacter}
        onRefreshCodex={codex.refreshCodex}
      />

    </div>
  );
};

export default GameView;

