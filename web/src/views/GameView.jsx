import React, { useState, useEffect } from 'react';
import { Menu, LogOut, User, Package, Users, Compass, BookOpen, X, Smartphone, Sliders, Bookmark, Map, ArrowLeft, FlagOff, ScrollText, Share2, Check, MoreVertical, Clock } from 'lucide-react';
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
import TacticalActionDock from '../components/Sidebar/TacticalActionDock';
import TimeSkipModal from '../components/Modals/TimeSkipModal';
import QuickBeltPopover from '../components/Modals/QuickBeltPopover';
import GiveGiftModal from '../components/Modals/GiveGiftModal';
import { useTranslation } from 'react-i18next';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';
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
  pendingAction,
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
  rerollImage,
  rerollingImage,
  actionError,
  clearActionError,
  leaveSession
}) => {
  const { t } = useTranslation();
  const [activeSidebarTab, setActiveSidebarTab] = useState('hero'); // 'hero' | 'inventory' | 'party' | 'quests' | 'codex' | 'outcomes'
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [mobileOutcomeOpen, setMobileOutcomeOpen] = useState(false);
  const [threeDotsOpen, setThreeDotsOpen] = useState(false);
  const [phoneModalOpen, setPhoneModalOpen] = useState(false);
  const [merchantModalOpen, setMerchantModalOpen] = useState(false);
  const [savesModalOpen, setSavesModalOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [worldMapModalOpen, setWorldMapModalOpen] = useState(false);
  const [worldMapTargetLocation, setWorldMapTargetLocation] = useState(null);
  const [selectedCombatTarget, setSelectedCombatTarget] = useState(null);
  const [headerCopied, setHeaderCopied] = useState(false);
  const [targetContactName, setTargetContactName] = useState(null);
  const [isStealthActive, setIsStealthActive] = useState(false);
  const [timeSkipModalOpen, setTimeSkipModalOpen] = useState(false);
  const [quickBeltModalOpen, setQuickBeltModalOpen] = useState(false);
  const [giveGiftModalOpen, setGiveGiftModalOpen] = useState(false);

  const handleSelectContact = (name) => {
    setTargetContactName(name);
    setActiveSidebarTab('codex');
    setMobileOutcomeOpen(false);
    setMobileDrawerOpen(true);
  };

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

  // Bi-directional synchronization with server stealth state
  useEffect(() => {
    const serverStealth = session?.stealth_state;
    if (serverStealth && typeof serverStealth.is_hidden === 'boolean') {
      setIsStealthActive(serverStealth.is_hidden);
    }
  }, [session?.stealth_state?.is_hidden]);

  const handleToggleStealth = async () => {
    const nextState = !isStealthActive;
    setIsStealthActive(nextState);
    if (session?.id && user?.user_id) {
      try {
        const res = await apiCall('/api/adventure/toggle_stealth', {
          method: 'POST',
          body: JSON.stringify({
            session_id: session.id,
            user_id: user.user_id,
            active: nextState
          })
        });
        if (res?.session && setSession) {
          setSession(prev => ({
            ...res.session,
            scene_image_url: res.session?.scene_image_url || prev?.scene_image_url || null
          }));
        }
      } catch (err) {
        console.warn('Failed to sync stealth stance to server:', err);
      }
    }
  };

  const handleAction = async (actionData) => {
    let finalAction = { ...actionData };
    if (isStealthActive) {
      finalAction.is_stealth = true;
      finalAction.stance = 'stealth';
      if (
        finalAction.custom_action_text &&
        !finalAction.custom_action_text.toLowerCase().includes('sneak') &&
        !finalAction.custom_action_text.toLowerCase().includes('stealth')
      ) {
        finalAction.custom_action_text = `[Stealth] ${finalAction.custom_action_text}`;
      }
    }

    // Smart auto-break: resting or speaking openly breaks stealth stance
    const intent = finalAction.intent || '';
    if (intent === 'rest_sleep' || intent === 'dialogue_init') {
      setIsStealthActive(false);
    }

    const outcome = await submitAction(finalAction);
    const updatedStealth = outcome?.session?.stealth_state || outcome?.stealth_state;
    if (updatedStealth && typeof updatedStealth.is_hidden === 'boolean') {
      setIsStealthActive(updatedStealth.is_hidden);
    }
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
    { id: 'hero', label: t('nav.hero'), icon: User, badge: character?.pending_stat_points ? '!' : null },
    { id: 'inventory', label: t('nav.inventory'), icon: Package, badge: inventory.items?.length || null },
    { id: 'party', label: t('nav.party'), icon: Users, badge: (session.party_members?.length || 1) + (session.party_npcs?.length || 0) },
    { id: 'quests', label: t('nav.quests'), icon: Compass, badge: activeQuestCount || null },
    { id: 'codex', label: t('nav.codex'), icon: BookOpen, badge: contactsCount },
    { id: 'outcomes', label: t('nav.outcomes'), icon: ScrollText, badge: null }
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
            targetContactName={targetContactName}
          />
        );
      case 'outcomes':
        return (
          <WorldOutcomeSidebar
            session={session}
            isMobileDrawer={true}
            onOpenWorldMap={(targetLoc) => {
              setWorldMapTargetLocation(typeof targetLoc === 'string' ? targetLoc : null);
              setMobileDrawerOpen(false);
              setWorldMapModalOpen(true);
            }}
            onSelectContact={handleSelectContact}
          />
        );
      case 'hero':
      default:
        return (
          <CharacterSheet
            character={session?.player_clothing_status && character ? { ...character, clothing_status: session.player_clothing_status } : character}
            onAllocateStat={allocateStatPoint}
            onCastSpell={handleCastSpell}
            processingTurn={processingTurn}
          />
        );
    }
  };

  return (
    <div
      style={{ height: 'var(--app-height, 100dvh)', maxHeight: 'var(--app-height, 100dvh)' }}
      className="flex w-full bg-black overflow-hidden font-sans"
    >

      {/* Sidebar (Desktop) */}
      <aside className="hidden md:flex w-[460px] xl:w-[500px] 2xl:w-[540px] flex-col bg-fantasy-panel border-r border-fantasy-border h-full shrink-0 transition-all duration-200">

        {/* Top Header */}
        <div className="p-4 border-b border-fantasy-border flex justify-between items-center bg-black/40">
          <div className="flex items-center gap-2.5">
            <Compass size={20} className="text-fantasy-accent" />
            <div>
              <h1 className="font-rpg font-bold text-fantasy-accent text-lg leading-tight">Hikayat</h1>
              <p className="text-xs text-gray-400 mt-0.5">{session.scenario_display_name || session.scenario || 'Realms of Myth & Magic'}</p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <LanguageSwitcher settingsHook={settings} />

            {/* Share Public Adventure Link */}
            <button
              onClick={handleShareAdventure}
              className={`p-1.5 rounded transition-colors ${
                headerCopied
                  ? 'text-green-400 bg-green-950/40 border border-green-500/40'
                  : 'text-gray-500 hover:text-fantasy-accent hover:bg-black/40'
              }`}
              title={headerCopied ? t('common.copied') : t('common.share')}
            >
              {headerCopied ? <Check size={14} className="text-green-400" /> : <Share2 size={14} />}
            </button>

            {/* Save / Load Checkpoints Button */}
            <button
              onClick={() => setSavesModalOpen(true)}
              className="p-1.5 text-gray-500 hover:text-fantasy-accent rounded hover:bg-black/40 transition-colors"
              title={t('nav.saves')}
            >
              <Bookmark size={14} />
            </button>

            <button
              onClick={() => setSettingsModalOpen(true)}
              className="p-1.5 text-gray-500 hover:text-fantasy-accent rounded hover:bg-black/40 transition-colors"
              title={t('nav.settings')}
            >
              <Sliders size={14} />
            </button>

            {exitToDashboard && (
              <button
                onClick={exitToDashboard}
                className="p-1.5 text-gray-400 hover:text-fantasy-accent rounded hover:bg-black/40 transition-colors"
                title={t('nav.exit_dashboard')}
              >
                <ArrowLeft size={14} />
              </button>
            )}

            {endSession && (
              <button
                onClick={endSession}
                className="p-1.5 text-amber-500/80 hover:text-red-400 rounded hover:bg-black/40 transition-colors"
                title={t('nav.end_adventure')}
              >
                <FlagOff size={14} />
              </button>
            )}

            <button
              onClick={leaveSession}
              className="p-1.5 text-gray-500 hover:text-red-400 rounded hover:bg-black/40 transition-colors"
              title={t('dashboard.logout')}
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>

        {/* Tab Navigation Switcher */}
        <div className="flex border-b border-fantasy-border bg-black/60 p-1.5 gap-1.5">
          {tabs.filter(t => t.id !== 'outcomes').map(tab => {
            const Icon = tab.icon;
            const isActive = activeSidebarTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveSidebarTab(tab.id)}
                className={`flex-1 flex flex-col items-center justify-center py-2 px-1 rounded-lg text-xs font-bold uppercase tracking-wider transition-all relative ${
                  isActive
                    ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-black/40'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <Icon size={15} />
                  {tab.badge && (
                    <span className={`text-[9px] px-1 rounded-full font-bold leading-none ${
                      tab.badge === '!'
                        ? 'bg-amber-500 text-black animate-bounce'
                        : 'bg-black/80 text-gray-300 border border-fantasy-border'
                    }`}>
                      {tab.badge}
                    </span>
                  )}
                </div>
                <span className="mt-1">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Scrollable Tab Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-3 sm:p-3.5 flex flex-col">
          {renderSidebarContent()}
        </div>

        {/* Pinned Tactical Action Dock (Desktop) */}
        <div className="shrink-0 p-2.5 bg-black/85 border-t border-fantasy-border/80 backdrop-blur-md">
          <TacticalActionDock
            session={session}
            inventoryHook={inventory}
            phoneHook={phone}
            isStealthActive={isStealthActive}
            onToggleStealth={handleToggleStealth}
            onOpenPhone={() => setPhoneModalOpen(true)}
            onClosePhone={() => setPhoneModalOpen(false)}
            phoneOpen={phoneModalOpen}
            onAction={handleAction}
            selectedCombatTarget={selectedCombatTarget}
            processing={processingTurn}
            onOpenTimeSkip={() => setTimeSkipModalOpen(true)}
            onOpenQuickBelt={() => setQuickBeltModalOpen(true)}
            onOpenGiveGift={() => setGiveGiftModalOpen(true)}
          />
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full min-h-0 relative min-w-0">

        {/* Mobile Header: Left (Menu + Game Title), Center (In-Game Clock), Right (Language + 3-Dots Menu) */}
        <header className="md:hidden flex justify-between items-center px-2.5 py-1.5 bg-fantasy-panel border-b border-fantasy-border z-30 select-none">
          {/* Top Left: Menu Button + Game Title */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setMobileDrawerOpen(true)}
              className="p-1.5 bg-black/50 border border-fantasy-border hover:border-fantasy-accent/60 rounded-lg text-fantasy-accent flex items-center justify-center transition-all relative shrink-0"
              title="Open Journal & Utilities (Outcomes, Map, Phone, Character, Pack, Party, Quests, Codex)"
              aria-label="Open utilities"
            >
              <Menu size={18} />
              {(character?.pending_stat_points || activeQuestCount > 0 || (phone.appointments?.length > 0 || phone.mediaGallery?.length > 0)) && (
                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse border-2 border-fantasy-panel" />
              )}
            </button>
            <div className="flex items-center gap-1.5">
              <Compass size={16} className="text-fantasy-accent animate-pulse shrink-0" />
              <h1 className="font-rpg font-bold text-fantasy-accent text-sm tracking-wider leading-none hidden min-[360px]:inline">
                Hikayat
              </h1>
            </div>
          </div>

          {/* Top Center: In-Game Clock Pill */}
          <div className="flex-1 flex justify-center items-center min-w-0 px-1.5">
            <div
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-black/60 border border-fantasy-border/80 text-[10px] sm:text-[11px] font-mono text-amber-300 shadow-sm"
              title="Current In-Game Time & Day"
            >
              <Clock size={11} className="text-amber-400 shrink-0" />
              <span className="truncate max-w-[95px] sm:max-w-[130px]">{session?.formatted_time || 'Day 1 • 08:00'}</span>
            </div>
          </div>

          {/* Top Right: Language Switcher + 3-Dots Button */}
          <div className="flex items-center gap-1.5 shrink-0">
            <LanguageSwitcher settingsHook={settings} />

            <div className="relative">
              <button
                type="button"
                onClick={() => setThreeDotsOpen((prev) => !prev)}
                className="p-1.5 bg-black/50 border border-fantasy-border hover:border-fantasy-accent rounded-lg text-gray-300 hover:text-fantasy-accent transition-colors flex items-center justify-center"
                title="Adventure Options & Menu"
                aria-label="Adventure options menu"
              >
                <MoreVertical size={18} />
              </button>

            {threeDotsOpen && (
              <>
                <div
                  className="fixed inset-0 z-40 bg-black/20"
                  onClick={() => setThreeDotsOpen(false)}
                />
                <div className="absolute right-0 mt-2 w-56 rounded-xl bg-fantasy-panel border border-fantasy-border shadow-2xl py-1.5 z-50 animate-in fade-in zoom-in-95 duration-100">
                  {/* Share Adventure Link */}
                  <button
                    type="button"
                    onClick={() => {
                      handleShareAdventure();
                    }}
                    className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium transition-colors text-left ${
                      headerCopied
                        ? 'text-green-400 bg-green-950/40'
                        : 'text-gray-200 hover:text-white hover:bg-white/5'
                    }`}
                  >
                    {headerCopied ? <Check size={15} className="text-green-400" /> : <Share2 size={15} className="text-gray-400" />}
                    <span>{headerCopied ? t('common.copied') : t('common.share')}</span>
                  </button>

                  {/* Save & Load Checkpoints */}
                  <button
                    type="button"
                    onClick={() => {
                      setThreeDotsOpen(false);
                      setSavesModalOpen(true);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-gray-200 hover:text-white hover:bg-white/5 transition-colors text-left"
                  >
                    <Bookmark size={15} className="text-gray-400" />
                    <span>{t('nav.saves')}</span>
                  </button>

                  {/* Settings & Chronicle */}
                  <button
                    type="button"
                    onClick={() => {
                      setThreeDotsOpen(false);
                      setSettingsModalOpen(true);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-gray-200 hover:text-white hover:bg-white/5 transition-colors text-left"
                  >
                    <Sliders size={15} className="text-gray-400" />
                    <span>{t('nav.settings')}</span>
                  </button>

                  <div className="my-1 border-t border-fantasy-border/60" />

                  {/* Return to Dashboard */}
                  {exitToDashboard && (
                    <button
                      type="button"
                      onClick={() => {
                        setThreeDotsOpen(false);
                        exitToDashboard();
                      }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-gray-200 hover:text-fantasy-accent hover:bg-white/5 transition-colors text-left"
                    >
                      <ArrowLeft size={15} className="text-gray-400" />
                      <span>{t('nav.exit_dashboard')}</span>
                    </button>
                  )}

                  {endSession && (
                    <button
                      type="button"
                      onClick={() => {
                        setThreeDotsOpen(false);
                        endSession();
                      }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-amber-400 hover:text-amber-300 hover:bg-amber-950/30 transition-colors text-left"
                    >
                      <FlagOff size={15} className="text-amber-400" />
                      <span>{t('nav.end_adventure')}</span>
                    </button>
                  )}

                  {/* Log Out */}
                  <button
                    type="button"
                    onClick={() => {
                      setThreeDotsOpen(false);
                      leaveSession();
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium text-red-400 hover:text-red-300 hover:bg-red-950/30 transition-colors text-left"
                  >
                    <LogOut size={15} className="text-red-400" />
                    <span>{t('dashboard.logout')}</span>
                  </button>
                </div>
              </>
            )}
          </div>
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
            processing={processingTurn}
            pendingAction={pendingAction}
            selectedCombatTarget={selectedCombatTarget}
            onSelectCombatTarget={setSelectedCombatTarget}
            onRerollImage={rerollImage}
            rerollingImage={rerollingImage}
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
          onOpenPhone={() => setPhoneModalOpen(true)}
          onClosePhone={() => setPhoneModalOpen(false)}
          phoneOpen={phoneModalOpen}
          phoneHook={phone}
          showPercentages={(settings.settings?.show_percentages ?? 1) === 1}
          processing={processingTurn}
          pendingAction={pendingAction}
          isStreaming={isStreaming}
          waitingForParty={waitingForParty}
          partyStatus={partyStatus}
          onSelectContact={handleSelectContact}
          actionError={actionError}
          clearActionError={clearActionError}
        />
      </main>

      {/* Right Sidebar: World Context (Map, Day/Time, Present NPCs) & Dedicated Outcomes/Changes Log */}
      <aside className="hidden lg:flex w-[420px] xl:w-[460px] 2xl:w-[500px] flex-col bg-fantasy-panel border-l border-fantasy-border h-full shrink-0 transition-all duration-200">
        <WorldOutcomeSidebar
          session={session}
          onOpenWorldMap={() => setWorldMapModalOpen(true)}
          onSelectContact={handleSelectContact}
        />
      </aside>

      {/* Mobile Utility Drawer (Outcomes, Map, Phone, Character, Pack, Party, Quests, Codex) */}
      {mobileDrawerOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setMobileDrawerOpen(false)}
          />
          <div className="relative w-84 max-w-[88vw] bg-fantasy-panel border-r border-fantasy-border h-full flex flex-col z-10 shadow-2xl">
            {/* Header */}
            <div className="p-3.5 border-b border-fantasy-border flex justify-between items-center bg-black/60">
              <div className="flex items-center gap-2">
                <Compass size={18} className="text-fantasy-accent" />
                <div>
                  <h2 className="font-rpg font-bold text-fantasy-accent text-sm leading-tight">Journal & Utilities</h2>
                  <p className="text-[10px] text-gray-400">{session.scenario_display_name || session.scenario || 'Realms of Myth & Magic'}</p>
                </div>
              </div>
              <button
                onClick={() => setMobileDrawerOpen(false)}
                className="p-1.5 text-gray-400 hover:text-gray-200 rounded-lg hover:bg-white/10"
              >
                <X size={18} />
              </button>
            </div>

            {/* Quick Access Tools: World Map & Smartphone OS */}
            <div className="grid grid-cols-2 gap-2 p-2 border-b border-fantasy-border/70 bg-black/40">
              <button
                type="button"
                onClick={() => {
                  setMobileDrawerOpen(false);
                  setWorldMapModalOpen(true);
                }}
                className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg bg-black/60 hover:bg-black/90 border border-fantasy-border hover:border-fantasy-accent/60 text-xs font-semibold text-fantasy-accent transition-all active:scale-95 shadow-sm"
              >
                <Map size={14} />
                <span>World Map</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMobileDrawerOpen(false);
                  setPhoneModalOpen(true);
                }}
                className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg bg-pink-950/40 hover:bg-pink-900/50 border border-pink-700/50 hover:border-pink-500 text-xs font-semibold text-pink-300 transition-all active:scale-95 shadow-sm"
              >
                <Smartphone size={14} />
                <span>Smartphone</span>
                {(phone.appointments?.length > 0 || phone.mediaGallery?.length > 0) && (
                  <span className="w-1.5 h-1.5 rounded-full bg-pink-400 animate-pulse" />
                )}
              </button>
            </div>

            {/* Utility Tabs Grid (Hero, Pack, Party, Quests, Codex, Outcomes) */}
            <div className="grid grid-cols-3 border-b border-fantasy-border bg-black/60 p-1 gap-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeSidebarTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveSidebarTab(tab.id)}
                    className={`flex flex-col items-center justify-center py-1.5 px-1 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all relative ${
                      isActive
                        ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                        : 'text-gray-400 hover:text-gray-200 hover:bg-black/40 border border-transparent'
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
                    <span className="mt-0.5 truncate">{tab.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto custom-scrollbar p-3 flex flex-col min-h-0">
              {renderSidebarContent()}
            </div>

            {/* Pinned Tactical Action Dock in Mobile Drawer */}
            <div className="shrink-0 p-2 bg-black/85 border-t border-fantasy-border/80 backdrop-blur-md">
              <TacticalActionDock
                session={session}
                inventoryHook={inventory}
                phoneHook={phone}
                isStealthActive={isStealthActive}
                onToggleStealth={handleToggleStealth}
                onOpenPhone={() => {
                  setMobileDrawerOpen(false);
                  setPhoneModalOpen(true);
                }}
                onClosePhone={() => setPhoneModalOpen(false)}
                phoneOpen={phoneModalOpen}
                onAction={handleAction}
                selectedCombatTarget={selectedCombatTarget}
                processing={processingTurn}
                onOpenTimeSkip={() => {
                  setMobileDrawerOpen(false);
                  setTimeSkipModalOpen(true);
                }}
                onOpenQuickBelt={() => {
                  setMobileDrawerOpen(false);
                  setQuickBeltModalOpen(true);
                }}
                onOpenGiveGift={() => {
                  setMobileDrawerOpen(false);
                  setGiveGiftModalOpen(true);
                }}
                isMobile={true}
              />
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
                onSelectContact={handleSelectContact}
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

      {/* Quick-Belt Consumables Popover */}
      <QuickBeltPopover
        isOpen={quickBeltModalOpen}
        onClose={() => setQuickBeltModalOpen(false)}
        inventoryHook={inventory}
        inCombat={Boolean(session?.in_combat || session?.combat_state?.in_combat || (session?.nearby_enemies && session.nearby_enemies.length > 0))}
        onAction={handleAction}
        onRefreshCharacter={refreshCharacter}
        processing={processingTurn}
      />

      {/* Give Gift to NPC Modal */}
      <GiveGiftModal
        isOpen={giveGiftModalOpen}
        onClose={() => setGiveGiftModalOpen(false)}
        session={session}
        inventoryHook={inventory}
        onAction={handleAction}
        processing={processingTurn}
      />

      {/* Genshin-Style Time Skip Chronos Dial Modal */}
      <TimeSkipModal
        isOpen={timeSkipModalOpen}
        onClose={() => setTimeSkipModalOpen(false)}
        session={session}
        phoneHook={phone}
        onAction={handleAction}
        processing={processingTurn}
      />

    </div>
  );
};

export default GameView;

