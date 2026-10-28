import React, { useState, useEffect } from 'react';
import { Menu, LogOut, User, Package, Users, Compass, BookOpen, X, Smartphone, Sliders, Bookmark, Map, ArrowLeft, FlagOff, ScrollText, Share2, Check, MoreVertical, Clock } from 'lucide-react';
import { apiCall } from '../api/client';
import CharacterSheet from '../components/Sidebar/CharacterSheet';
import InventoryPanel from '../components/Sidebar/InventoryPanel';
import PartyWidget from '../components/Sidebar/PartyWidget';
import ContactsPanel from '../components/Sidebar/ContactsPanel';
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
import ThemeSwitcher from '../components/Common/ThemeSwitcher';
import GameMenu from '../components/Common/GameMenu';
import { useMediaQuery } from '../hooks/useMediaQuery';
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
  const [targetContactPulse, setTargetContactPulse] = useState(0);
  const [phoneInitialNpc, setPhoneInitialNpc] = useState(null);
  const [isStealthActive, setIsStealthActive] = useState(false);
  const [timeSkipModalOpen, setTimeSkipModalOpen] = useState(false);
  const [quickBeltModalOpen, setQuickBeltModalOpen] = useState(false);
  const [giveGiftModalOpen, setGiveGiftModalOpen] = useState(false);

  // Right rail (world & outcomes) only fits on wide screens; below that it becomes a sidebar tab.
  const isWide = useMediaQuery('(min-width: 1280px)');

  const handleSelectContact = (name) => {
    setTargetContactName(name);
    setTargetContactPulse(Date.now());
    const needle = String(name ?? '').trim().toLowerCase();
    const isPersonalContact = needle && (codex.contacts || []).some(c =>
      !c.is_dispatch_channel && (
        String(c.name ?? '').trim().toLowerCase() === needle ||
        String(c.id ?? '').trim().toLowerCase() === needle ||
        String(c.npc_id ?? '').trim().toLowerCase() === needle
      )
    );
    setActiveSidebarTab(isPersonalContact ? 'contacts' : 'codex');
    if (!window.matchMedia('(min-width: 768px)').matches) {
      setMobileDrawerOpen(true);
    }
  };

  const handleMessageContact = (npc) => {
    const npcKey = typeof npc === 'string' ? npc : (npc?.npc_id || npc?.name);
    if (!npcKey) return;
    setMobileDrawerOpen(false);
    setPhoneInitialNpc(npcKey);
    setPhoneModalOpen(true);
  };

  const openWorldMap = (targetLoc) => {
    setWorldMapTargetLocation(typeof targetLoc === 'string' ? targetLoc : null);
    setMobileDrawerOpen(false);
    setWorldMapModalOpen(true);
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
    const intent = finalAction.intent || '';
    const isVoluntaryDisengage = intent === 'rest_sleep' || intent === 'dialogue_init';

    if (isVoluntaryDisengage) {
      setIsStealthActive(false);
      finalAction.is_stealth = false;
    } else if (isStealthActive && finalAction.is_stealth !== false) {
      finalAction.is_stealth = true;
      finalAction.stance = finalAction.stance || 'stealth';
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
      target_location: destination,
      intent: 'fast_travel',
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
  const contactsCount = (codex.contacts || []).filter(c => !c.is_dispatch_channel).length || null;
  const knownWorldCount = (codex.lorebook?.entities || []).filter(e => e.is_discovered !== false).length || null;
  const hasActiveMerchant = Boolean(session?.merchant?.available || session?.merchant?.active);

  const tabs = [
    { id: 'hero', label: t('nav.hero'), icon: User, badge: character?.pending_stat_points ? '!' : null },
    { id: 'inventory', label: t('nav.inventory'), icon: Package, badge: inventory.items?.length || null },
    { id: 'party', label: t('nav.party'), icon: Users, badge: (session.party_members?.length || 1) + (session.party_npcs?.length || 0) },
    { id: 'contacts', label: t('nav.contacts', 'Contacts'), icon: Smartphone, badge: contactsCount },
    { id: 'quests', label: t('nav.quests'), icon: Compass, badge: activeQuestCount || null },
    { id: 'codex', label: t('nav.codex'), icon: BookOpen, badge: knownWorldCount },
    { id: 'outcomes', label: t('nav.outcomes'), icon: ScrollText, badge: null }
  ];

  const sidebarTabs = isWide ? tabs.filter((tb) => tb.id !== 'outcomes') : tabs;

  // When the right rail is visible, the "outcomes" tab is redundant.
  useEffect(() => {
    if (isWide && activeSidebarTab === 'outcomes') setActiveSidebarTab('hero');
  }, [isWide, activeSidebarTab]);

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
      case 'contacts':
        return (
          <ContactsPanel
            codexHook={codex}
            session={session}
            user={user}
            onSessionUpdated={handleSessionLoaded}
            onMessageContact={handleMessageContact}
            onJumpToCharacterInCodex={(npcName) => {
              setTargetContactName(npcName);
              setTargetContactPulse(Date.now());
              setActiveSidebarTab('codex');
            }}
            targetContactName={targetContactName}
            targetContactPulse={targetContactPulse}
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
            targetContactPulse={targetContactPulse}
            onJumpToSavedContact={(npcName) => {
              setTargetContactName(npcName);
              setTargetContactPulse(Date.now());
              setActiveSidebarTab('contacts');
            }}
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

  const locationLabel = (() => {
    const raw = session?.current_location || '';
    const parts = String(raw).split(/\s*(?:->|→|➔|>|›|»|\|)\s*/).filter(Boolean);
    return parts[parts.length - 1] || session?.scene_title || '';
  })();
  const clockLabel = session?.formatted_time || 'Day 1 • 08:00';
  const scenarioLabel = session.scenario_display_name || session.scenario || 'Realms of Myth & Magic';
  const hasPhoneAlerts = Boolean(phone.appointments?.length > 0 || phone.mediaGallery?.length > 0);
  const hasDrawerAlert = Boolean(character?.pending_stat_points || activeQuestCount > 0 || hasPhoneAlerts);

  const menuItems = (includeSettings) => [
    { id: 'share', label: headerCopied ? t('common.copied') : t('common.share'), icon: headerCopied ? Check : Share2, onClick: handleShareAdventure, keepOpen: true, active: headerCopied },
    { id: 'saves', label: t('nav.saves'), icon: Bookmark, onClick: () => setSavesModalOpen(true) },
    { id: 'map', label: t('nav.map'), icon: Map, onClick: () => openWorldMap() },
    { id: 'settings', label: t('nav.settings'), icon: Sliders, onClick: () => setSettingsModalOpen(true), hidden: !includeSettings },
    { id: 'div', divider: true },
    { id: 'exit', label: t('nav.exit_dashboard'), icon: ArrowLeft, onClick: exitToDashboard, hidden: !exitToDashboard },
    { id: 'end', label: t('nav.end_adventure'), icon: FlagOff, onClick: endSession, tone: 'warn', hidden: !endSession },
    { id: 'logout', label: t('dashboard.logout'), icon: LogOut, onClick: leaveSession, tone: 'danger' },
  ];

  const dockProps = {
    session,
    inventoryHook: inventory,
    phoneHook: phone,
    isStealthActive,
    onToggleStealth: handleToggleStealth,
    onClosePhone: () => setPhoneModalOpen(false),
    phoneOpen: phoneModalOpen,
    onAction: handleAction,
    selectedCombatTarget,
    processing: processingTurn,
  };

  const renderTabs = (list, { dense = false } = {}) => (
    <div className={`hk-segmented ${dense ? 'grid-flow-row grid-cols-3' : ''}`} role="tablist">
      {list.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeSidebarTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => setActiveSidebarTab(tab.id)}
            title={tab.label}
            className={dense ? 'relative min-w-0 !gap-3 !px-2' : '!h-auto !flex-col !gap-0.5 !py-1.5 relative min-w-0'}
          >
            <span className={`relative ${isActive ? 'text-fantasy-accent' : ''}`}>
              <Icon size={16} />
              {tab.badge && (
                <span className={`absolute -top-1.5 -right-3 min-w-[1rem] h-4 px-1 rounded-full text-[9px] font-bold leading-4 text-center ${
                  tab.badge === '!' ? 'bg-fantasy-accent text-black animate-pulse' : 'bg-gray-500/25 text-gray-200'
                }`}>
                  {tab.badge}
                </span>
              )}
            </span>
            <span className="block max-w-full truncate text-[10.5px] leading-tight">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );

  return (
    <div
      style={{ height: 'var(--app-height, 100dvh)', maxHeight: 'var(--app-height, 100dvh)' }}
      className="flex w-full bg-transparent overflow-hidden font-sans"
    >

      {/* Left rail (tablet & desktop) */}
      <aside className="hidden md:flex w-[316px] lg:w-[348px] 2xl:w-[400px] flex-col bg-fantasy-panel border-r border-fantasy-border/50 h-full min-h-0 shrink-0">

        {/* Rail header */}
        <div className="px-3 h-14 border-b border-fantasy-border/50 flex items-center justify-between gap-2 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="hidden lg:grid place-items-center w-8 h-8 rounded-lg bg-fantasy-accent text-black shrink-0">
              <Compass size={16} />
            </div>
            <div className="min-w-0">
              <h1 className="hk-display font-bold text-gray-50 text-sm leading-tight truncate">Hikayat</h1>
              <p className="text-[11px] text-gray-500 truncate" title={scenarioLabel}>{scenarioLabel}</p>
            </div>
          </div>
          <div className="flex items-center shrink-0">
            <ThemeSwitcher compact />
            <LanguageSwitcher settingsHook={settings} />
            <button
              type="button"
              onClick={() => setSettingsModalOpen(true)}
              className="hk-icon-btn"
              title={t('nav.settings')}
              aria-label={t('nav.settings')}
            >
              <Sliders size={16} />
            </button>
            <GameMenu items={menuItems(false)} label={t('nav.menu', 'Menu')} />
          </div>
        </div>

        {/* Tabs */}
        <div className="px-3 pt-3 pb-2 shrink-0">
          {renderTabs(sidebarTabs, { dense: sidebarTabs.length > 5 })}
        </div>

        {/* Tab content */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-3 pb-3 flex flex-col">
          {renderSidebarContent()}
        </div>

        {/* Quick actions dock */}
        <div className="shrink-0 p-2.5 border-t border-fantasy-border/50 bg-fantasy-darker/40">
          <TacticalActionDock
            {...dockProps}
            onOpenPhone={() => setPhoneModalOpen(true)}
            onOpenTimeSkip={() => setTimeSkipModalOpen(true)}
            onOpenQuickBelt={() => setQuickBeltModalOpen(true)}
            onOpenGiveGift={() => setGiveGiftModalOpen(true)}
          />
        </div>
      </aside>

      {/* Main column */}
      <main className="flex-1 flex flex-col h-full min-h-0 relative min-w-0">

        {/* Mobile header */}
        <header className="md:hidden flex items-center gap-1 px-2 h-14 bg-fantasy-panel border-b border-fantasy-border/50 z-30 select-none shrink-0">
          <button
            type="button"
            onClick={() => setMobileDrawerOpen(true)}
            className="hk-icon-btn relative"
            aria-label={t('nav.journal', 'Journal & tools')}
            title={t('nav.journal', 'Journal & tools')}
          >
            <Menu size={20} />
            {hasDrawerAlert && <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-fantasy-accent" />}
          </button>

          <button
            type="button"
            onClick={() => { setActiveSidebarTab('outcomes'); setMobileDrawerOpen(true); }}
            className="flex-1 min-w-0 flex flex-col items-start px-1 text-left"
            title={t('nav.outcomes')}
          >
            <span className="w-full truncate text-[13px] font-semibold text-gray-100 leading-tight">{locationLabel || 'Hikayat'}</span>
            <span className="inline-flex items-center gap-1 text-[11px] text-gray-400 leading-tight">
              <Clock size={11} className="text-fantasy-accent shrink-0" />
              <span className="truncate">{clockLabel}</span>
            </span>
          </button>

          <div className="flex items-center shrink-0">
            <ThemeSwitcher compact />
            <LanguageSwitcher settingsHook={settings} />
            <GameMenu items={menuItems(true)} label={t('nav.menu', 'Menu')} icon={MoreVertical} />
          </div>
        </header>

        {/* Tablet / small-desktop context bar (right sidebar hidden) */}
        {!isWide && (
          <div className="hidden md:flex items-center gap-2 px-4 h-11 border-b border-fantasy-border/40 bg-fantasy-panel/60 shrink-0">
            <span className="flex-1 min-w-0 truncate text-[13px] font-medium text-gray-200" title={session?.current_location || ''}>
              {locationLabel}
            </span>
            <span className="hk-chip"><Clock size={11} className="text-fantasy-accent" /> {clockLabel}</span>
            <button type="button" onClick={() => openWorldMap()} className="hk-icon-btn h-8" title={t('nav.map')} aria-label={t('nav.map')}>
              <Map size={15} />
            </button>
            <button
              type="button"
              onClick={() => setActiveSidebarTab('outcomes')}
              className={`hk-icon-btn h-8 ${activeSidebarTab === 'outcomes' ? 'text-fantasy-accent' : ''}`}
              title={t('nav.outcomes')}
              aria-label={t('nav.outcomes')}
            >
              <ScrollText size={15} />
            </button>
          </div>
        )}

        {/* Narrative feed */}
        <div className="flex-1 min-h-0 overflow-hidden relative">
          <div className="absolute inset-0 bg-fantasy-dark/75 z-0"></div>
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

        {/* Choices & custom action */}
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

      {/* Right rail: world context & outcomes (wide screens) */}
      {isWide && (
        <aside className="flex w-[340px] 2xl:w-[400px] flex-col bg-fantasy-panel border-l border-fantasy-border/50 h-full min-h-0 shrink-0">
          <WorldOutcomeSidebar
            session={session}
            onOpenWorldMap={openWorldMap}
            onSelectContact={handleSelectContact}
          />
        </aside>
      )}

      {/* Mobile drawer: journal, tabs & quick actions */}
      {mobileDrawerOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setMobileDrawerOpen(false)}
          />
          <div className="hk-drawer-left relative w-[22rem] max-w-[90vw] bg-fantasy-panel border-r border-fantasy-border/60 h-full flex flex-col z-10 shadow-2xl">
            <div className="px-3 h-14 border-b border-fantasy-border/50 flex justify-between items-center shrink-0">
              <div className="min-w-0">
                <h2 className="hk-display font-bold text-gray-50 text-sm leading-tight">Hikayat</h2>
                <p className="text-[11px] text-gray-500 truncate">{scenarioLabel}</p>
              </div>
              <button
                type="button"
                onClick={() => setMobileDrawerOpen(false)}
                className="hk-icon-btn"
                aria-label={t('common.close')}
              >
                <X size={18} />
              </button>
            </div>

            <div className="px-3 pt-3 grid grid-cols-2 gap-2 shrink-0">
              <button
                type="button"
                onClick={() => { setMobileDrawerOpen(false); openWorldMap(); }}
                className="hk-btn hk-btn-ghost h-10"
              >
                <Map size={15} className="text-fantasy-accent" /> {t('nav.map')}
              </button>
              <button
                type="button"
                onClick={() => { setMobileDrawerOpen(false); setPhoneModalOpen(true); }}
                className="hk-btn hk-btn-ghost h-10 relative"
              >
                <Smartphone size={15} className="text-pink-400" /> {phone?.branding?.device_name || t('nav.phone')}
                {hasPhoneAlerts && <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-pink-400 animate-pulse" />}
              </button>
            </div>

            <div className="px-3 pt-3 pb-2 shrink-0">
              {renderTabs(tabs, { dense: true })}
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-3 pb-3 flex flex-col">
              {renderSidebarContent()}
            </div>

            <div className="shrink-0 p-2.5 border-t border-fantasy-border/50 bg-fantasy-darker/40" style={{ paddingBottom: 'max(0.625rem, env(safe-area-inset-bottom))' }}>
              <TacticalActionDock
                {...dockProps}
                isMobile
                onOpenPhone={() => { setMobileDrawerOpen(false); setPhoneModalOpen(true); }}
                onOpenTimeSkip={() => { setMobileDrawerOpen(false); setTimeSkipModalOpen(true); }}
                onOpenQuickBelt={() => { setMobileDrawerOpen(false); setQuickBeltModalOpen(true); }}
                onOpenGiveGift={() => { setMobileDrawerOpen(false); setGiveGiftModalOpen(true); }}
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
        initialChatNpc={phoneInitialNpc}
        onClearInitialChatNpc={() => setPhoneInitialNpc(null)}
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

