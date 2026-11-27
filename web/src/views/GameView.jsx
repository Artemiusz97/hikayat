import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowLeft,
  Bookmark,
  BookOpen,
  BookUser,
  Check,
  ChevronDown,
  Compass,
  FlagOff,
  Flame,
  History,
  LogOut,
  Menu,
  Package,
  ScrollText,
  Share2,
  Sliders,
  Smartphone,
  User,
  Users,
  X,
  Zap,
} from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { apiCall } from '../api/client';
import NpcProfileSideCard from '../components/Sidebar/NpcProfileSideCard';
import {
  EpistemicWatchStrip,
  LatestOutcomeCard,
  PresentNpcsCard,
} from '../components/Sidebar/WorldOutcomeSidebar';
import StoryFeed from '../components/StoryFeed/StoryFeed';
import ActionPanel from '../components/ActionPanel/ActionPanel';
import TacticalActionDock from '../components/Sidebar/TacticalActionDock';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';
import ThemeSwitcher from '../components/Common/ThemeSwitcher';
import AcrylicModeSwitcher from '../components/Common/AcrylicModeSwitcher';
import GameMenu from '../components/Common/GameMenu';
import {
  AcrylicPanel,
  CollapsibleSection,
  EASE_OUT,
  MotionButton,
  SPRING_PANEL,
} from '../components/Common/MotionPrimitives';
import { copyToClipboard } from '../utils/clipboard';
import { useEscapeLayer } from '../hooks/useEscapeLayer';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { useInventory } from '../hooks/useInventory';
import { useCodex } from '../hooks/useCodex';
import { usePhone } from '../hooks/usePhone';
import { useSettings } from '../hooks/useSettings';
import { useUiPreferences } from '../theme/UiPreferencesProvider';
import { formatCleanLocation } from '../utils/locationFormat';
import { formatCleanDeviceName } from '../utils/consumables';
import { isAnomalousScenarioKey, isValidSessionId } from '../utils/session';
import { matchesNpcIdentity, resolveSceneNpcProfile } from '../utils/npcProfile';
import { isAnomalousNpc, normalizeActorName } from '../utils/sceneTargets';
import GameTopLeftControls from './GameTopLeftControls';
import GameLeftDrawerContent from './GameLeftDrawerContent';
import GameViewModals from './GameViewModals';

const GameView = ({
  user,
  character,
  refreshCharacter,
  allocateStatPoint,
  session,
  setSession,
  refreshSession,
  lastSyncTimestamp,
  wsStatus = 'idle',
  processingTurn,
  pendingAction,
  isStreaming,
  isThinking = false,
  cancellingTurn = false,
  streamingNarrative,
  streamingState,
  waitingForParty,
  partyStatus,
  partyChatMessages = [],
  onlineUserIds = [],
  sendPartyChat,
  submitAction,
  cancelTurn = null,
  exitToDashboard,
  endSession,
  retryGeneration,
  rerollImage,
  rerollingImage,
  actionError,
  clearActionError,
  leaveSession,
}) => {
  const { t } = useTranslation();
  const reducedMotion = useReducedMotion();
  const isDesktop = useMediaQuery('(min-width: 1280px)');
  const {
    hud,
    clockFormat,
    readingMode,
    toggleLeftPanel,
    setHudField,
    toggleHudField,
  } = useUiPreferences();

  const [activeUtilityTab, setActiveUtilityTab] = useState('hero');
  const [mobileSheet, setMobileSheet] = useState(null); // null | 'npcs' | 'outcome' | 'actions'
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [worldMapExpandedOpen, setWorldMapExpandedOpen] = useState(false);
  const [worldMapTargetLocation, setWorldMapTargetLocation] = useState(null);

  const [phoneModalOpen, setPhoneModalOpen] = useState(false);
  const [merchantModalOpen, setMerchantModalOpen] = useState(false);
  const [savesModalOpen, setSavesModalOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [timeSkipModalOpen, setTimeSkipModalOpen] = useState(false);
  const [quickBeltModalOpen, setQuickBeltModalOpen] = useState(false);
  const [giveGiftModalOpen, setGiveGiftModalOpen] = useState(false);
  const [examineModalOpen, setExamineModalOpen] = useState(false);
  const [useItemInitialTarget, setUseItemInitialTarget] = useState(null);
  const [giveGiftInitialTarget, setGiveGiftInitialTarget] = useState(null);
  const [contractsModalOpen, setContractsModalOpen] = useState(false);

  const [selectedCombatTarget, setSelectedCombatTarget] = useState(null);
  const [headerCopied, setHeaderCopied] = useState(false);
  const [endSessionConfirmOpen, setEndSessionConfirmOpen] = useState(false);
  const [endingSessionBusy, setEndingSessionBusy] = useState(false);
  const headerCopyTimerRef = useRef(null);
  const [targetContactName, setTargetContactName] = useState(null);
  const [targetContactPulse, setTargetContactPulse] = useState(0);
  const [inspectedSceneNpc, setInspectedSceneNpc] = useState(null);
  const [phoneInitialNpc, setPhoneInitialNpc] = useState(null);
  const [isStealthActive, setIsStealthActive] = useState(false);
  const [stealthError, setStealthError] = useState(null);
  const stealthPendingRef = useRef(false);
  const [lastSeenChatCount, setLastSeenChatCount] = useState(
    () => partyChatMessages.length
  );

  const inventory = useInventory(user);
  const codex = useCodex(session?.id, user, session, refreshSession);
  const phone = usePhone(session?.id, user);
  const settings = useSettings(user?.user_id);

  const resolvedSceneNpcProfile = useMemo(
    () =>
      inspectedSceneNpc
        ? resolveSceneNpcProfile(inspectedSceneNpc, session, codex)
        : null,
    [inspectedSceneNpc, session, codex]
  );

  const isPartyTabVisible =
    hud.leftPanel === 'utility' && activeUtilityTab === 'party';

  useEffect(() => {
    if (isPartyTabVisible) {
      setLastSeenChatCount(partyChatMessages.length);
    }
  }, [isPartyTabVisible, partyChatMessages.length]);

  const unreadChatCount = isPartyTabVisible
    ? 0
    : Math.max(0, partyChatMessages.length - lastSeenChatCount);

  useEffect(() => () => {
    if (headerCopyTimerRef.current) clearTimeout(headerCopyTimerRef.current);
  }, []);

  useEscapeLayer(
    !isDesktop && hud.leftPanel !== null,
    () => setHudField('leftPanel', null),
    'mobile-left-drawer-esc'
  );
  useEscapeLayer(
    !isDesktop && mobileSheet !== null,
    () => setMobileSheet(null),
    'mobile-sheet-esc'
  );

  useEffect(() => {
    if (!inspectedSceneNpc) return;
    const currentList = Array.isArray(session?.current_npcs) ? session.current_npcs : [];
    const stillPresent = currentList.some(
      (entry) =>
        !isAnomalousNpc(entry) &&
        matchesNpcIdentity(entry, inspectedSceneNpc)
    );
    if (!stillPresent) {
      setInspectedSceneNpc(null);
    }
  }, [inspectedSceneNpc, session?.current_npcs]);

  useEffect(() => {
    setInspectedSceneNpc(null);
  }, [session?.id]);

  useEffect(() => {
    if (!isDesktop && mobileSheet !== 'npcs' && inspectedSceneNpc) {
      setInspectedSceneNpc(null);
    }
  }, [isDesktop, mobileSheet, inspectedSceneNpc]);

  useEscapeLayer(
    isDesktop && Boolean(inspectedSceneNpc),
    () => setInspectedSceneNpc(null),
    'npc-profile-side-esc'
  );
  useEscapeLayer(
    !isDesktop && mobileSheet === 'npcs' && Boolean(inspectedSceneNpc),
    () => setInspectedSceneNpc(null),
    'mobile-npc-profile-esc'
  );

  const handleConfirmEndSession = async () => {
    if (!endSession || endingSessionBusy) return;
    setEndingSessionBusy(true);
    try {
      await endSession();
      setEndSessionConfirmOpen(false);
    } finally {
      setEndingSessionBusy(false);
    }
  };

  const handleConsumeTargetContact = useCallback(() => {
    setTargetContactName(null);
  }, []);

  const handleOpenNpcInRoster = (name, preferredTarget = null) => {
    setInspectedSceneNpc(null);
    setTargetContactName(name);
    setTargetContactPulse((prev) => prev + 1);
    const needle = String(name ?? '').trim().toLowerCase();
    const isPersonalOrAcq =
      preferredTarget === 'contacts' ||
      preferredTarget === 'acquaintances' ||
      (preferredTarget !== 'codex' &&
        needle &&
        ((codex.contacts || []).some(
          (c) =>
            !c.is_dispatch_channel &&
            (String(c.name ?? '').trim().toLowerCase() === needle ||
              String(c.id ?? '').trim().toLowerCase() === needle ||
              String(c.npc_id ?? '').trim().toLowerCase() === needle)
        ) ||
          (codex.acquaintances || []).some(
            (a) =>
              String(a.name ?? '').trim().toLowerCase() === needle ||
              String(a.id ?? '').trim().toLowerCase() === needle ||
              String(a.npc_id ?? '').trim().toLowerCase() === needle ||
              String(a.npc_key ?? '').trim().toLowerCase() === needle
          )));
    setActiveUtilityTab(isPersonalOrAcq ? 'contacts' : 'codex');
    setMobileSheet(null);
    setHudField('leftPanel', 'utility');
  };

  const handleInspectSceneNpc = (name) => {
    const cleanTarget = normalizeActorName(name).toLowerCase();
    if (!cleanTarget) return;
    setInspectedSceneNpc((prev) =>
      prev && (normalizeActorName(prev).toLowerCase() === cleanTarget || matchesNpcIdentity({ name: prev }, name))
        ? null
        : name
    );
  };

  const handleMessageContact = (npc) => {
    const npcKey = typeof npc === 'string' ? npc : npc?.npc_id || npc?.name;
    if (!npcKey) return;
    if (!isDesktop) setHudField('leftPanel', null);
    setMobileSheet(null);
    setPhoneInitialNpc(npcKey);
    setPhoneModalOpen(true);
  };

  const openWorldMap = (targetLoc) => {
    setWorldMapTargetLocation(typeof targetLoc === 'string' ? targetLoc : null);
    setMobileSheet(null);
    setHudField('leftPanel', 'map');
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
      const inviteMsg = `${shareUrl}${
        session?.id ? ` (Invite Code: ${session.id})` : ''
      }`;
      if (await copyToClipboard(inviteMsg)) {
        setHeaderCopied(true);
        if (headerCopyTimerRef.current) clearTimeout(headerCopyTimerRef.current);
        headerCopyTimerRef.current = setTimeout(() => setHeaderCopied(false), 2500);
      }
    } catch (e) {
      console.error('Failed to copy adventure link:', e);
    }
  };

  useEffect(() => {
    const enemies = (
      session?.nearby_enemies ||
      session?.monsters ||
      []
    ).filter((e) => e && e.name && (e.hp ?? 1) > 0);
    if (enemies.length === 0) {
      setSelectedCombatTarget(null);
    } else if (
      !selectedCombatTarget ||
      !enemies.some((e) => e.name === selectedCombatTarget)
    ) {
      setSelectedCombatTarget(enemies[0].name);
    }
  }, [session?.nearby_enemies, session?.monsters, selectedCombatTarget]);

  const prevSessionIdForRefreshRef = useRef(session?.id ?? null);
  const sidebarRefreshRef = useRef({
    refreshCharacter,
    refreshInventory: inventory.refreshInventory,
    refreshCodex: codex.refreshCodex,
    refreshPhone: phone.refreshPhone,
  });
  sidebarRefreshRef.current = {
    refreshCharacter,
    refreshInventory: inventory.refreshInventory,
    refreshCodex: codex.refreshCodex,
    refreshPhone: phone.refreshPhone,
  };

  useEffect(() => {
    const nextId = session?.id ?? null;
    if (prevSessionIdForRefreshRef.current === nextId) return;
    prevSessionIdForRefreshRef.current = nextId;
    if (isValidSessionId(nextId)) {
      sidebarRefreshRef.current.refreshCharacter();
      sidebarRefreshRef.current.refreshInventory();
    }
  }, [session?.id]);

  const prevSyncTimestampRef = useRef(lastSyncTimestamp);

  useEffect(() => {
    if (lastSyncTimestamp <= 0 || prevSyncTimestampRef.current === lastSyncTimestamp) {
      return;
    }
    prevSyncTimestampRef.current = lastSyncTimestamp;
    sidebarRefreshRef.current.refreshCharacter();
    sidebarRefreshRef.current.refreshInventory();
    sidebarRefreshRef.current.refreshCodex();
    sidebarRefreshRef.current.refreshPhone();
  }, [lastSyncTimestamp]);

  const turnBusy = Boolean(processingTurn || waitingForParty || isStreaming);
  const stealthActiveRef = useRef(isStealthActive);
  stealthActiveRef.current = isStealthActive;
  const stealthPromiseRef = useRef(null);
  const activeSessionIdRef = useRef(session?.id);
  activeSessionIdRef.current = session?.id;

  useEffect(() => {
    const isHidden = session?.stealth_state?.is_hidden;
    const nextHidden = typeof isHidden === 'boolean' ? isHidden : false;
    stealthActiveRef.current = nextHidden;
    setIsStealthActive(nextHidden);
  }, [session?.id, session?.stealth_state?.is_hidden]);

  const handleToggleStealth = async () => {
    if (stealthPendingRef.current) return stealthPromiseRef.current;
    const reqSid = session?.id;
    const prevState = stealthActiveRef.current;
    const nextState = !prevState;
    stealthActiveRef.current = nextState;
    setIsStealthActive(nextState);
    setStealthError(null);
    if (isValidSessionId(reqSid) && user?.user_id) {
      stealthPendingRef.current = true;
      const syncPromise = (async () => {
        try {
          const res = await apiCall('/api/adventure/toggle_stealth', {
            method: 'POST',
            body: JSON.stringify({
              session_id: reqSid,
              user_id: user.user_id,
              active: nextState,
            }),
          });
          if (String(activeSessionIdRef.current) !== String(reqSid)) {
            return;
          }
          if (res?.session) {
            const serverHidden = res.session?.stealth_state?.is_hidden;
            if (typeof serverHidden === 'boolean') {
              stealthActiveRef.current = serverHidden;
              setIsStealthActive(serverHidden);
            }
            if (setSession) {
              setSession((prev) =>
                prev && String(prev.id) === String(reqSid)
                  ? {
                      ...res.session,
                      scene_image_url:
                        res.session?.scene_image_url || prev?.scene_image_url || null,
                    }
                  : prev
              );
            }
          }
        } catch (err) {
          console.warn('Failed to sync stealth stance to server:', err);
          if (String(activeSessionIdRef.current) === String(reqSid)) {
            stealthActiveRef.current = prevState;
            setIsStealthActive(prevState);
            setStealthError(err?.message || 'Failed to sync stealth stance.');
          }
        } finally {
          stealthPendingRef.current = false;
          if (stealthPromiseRef.current === syncPromise) {
            stealthPromiseRef.current = null;
          }
        }
      })();
      stealthPromiseRef.current = syncPromise;
      return syncPromise;
    }
    return null;
  };

  const handleAction = async (actionData) => {
    const reqSid = session?.id;
    if (stealthPromiseRef.current) {
      try {
        await stealthPromiseRef.current;
      } catch {}
      if (reqSid != null && String(activeSessionIdRef.current) !== String(reqSid)) {
        return;
      }
    }
    const finalAction = { ...actionData };
    const intent = finalAction.intent || '';
    const isVoluntaryDisengage =
      intent === 'rest_sleep' || intent === 'dialogue_init';

    if (isVoluntaryDisengage) {
      finalAction.is_stealth = false;
    } else if (stealthActiveRef.current && finalAction.is_stealth !== false) {
      finalAction.is_stealth = true;
      finalAction.stance = finalAction.stance || 'stealth';
    }

    let outcome;
    try {
      outcome = await submitAction(finalAction);
    } catch {
      return;
    }
    if (!outcome) {
      return;
    }
    if (isVoluntaryDisengage) {
      stealthActiveRef.current = false;
      setIsStealthActive(false);
    }
    if (outcome?.status === 'accepted') {
      return;
    }
    const updatedStealth = outcome?.session?.stealth_state || outcome?.stealth_state;
    if (updatedStealth && typeof updatedStealth.is_hidden === 'boolean') {
      stealthActiveRef.current = updatedStealth.is_hidden;
      setIsStealthActive(updatedStealth.is_hidden);
    }
  };

  const handleFastTravel = async (destination) => {
    if (!destination || turnBusy) return;
    if (typeof destination === 'object' && destination.direct_choice) {
      await handleAction({
        intent: 'movement',
        direct_choice: destination.direct_choice,
      });
      return;
    }
    const cleanDest =
      formatCleanLocation(destination, { includeZone: true, style: 'badge' }) ||
      destination;
    await handleAction({
      label: t('atlas.traveling_to', {
        destination: cleanDest,
        defaultValue: `Traveling to ${cleanDest}...`,
      }),
      custom_action_text: `I travel to ${destination}.`,
      target_location: destination,
      intent: 'fast_travel',
    });
  };

  const handleCastSpell = async (spell) => {
    if (!spell?.name || turnBusy) return;
    await handleAction({
      custom_action_text: `Cast ${spell.name}`,
      stat: 'INT',
      mp_cost: Number(spell.mp_cost || 0),
    });
  };

  const handleSessionLoaded = (loadedSession) => {
    if (setSession && loadedSession) {
      setSession(loadedSession);
    }
    if (!loadedSession?.id || String(loadedSession.id) === String(session?.id)) {
      sidebarRefreshRef.current.refreshCharacter();
      sidebarRefreshRef.current.refreshInventory();
      sidebarRefreshRef.current.refreshCodex();
      sidebarRefreshRef.current.refreshPhone();
    }
  };

  const handleRetryGeneration = async () => {
    if (!retryGeneration) return;
    await retryGeneration();
  };

  const activeQuestCount =
    (codex.activeStoryQuest ? 1 : 0) +
    (codex.quests || []).filter(
      (q) =>
        q &&
        !(
          q.is_story_quest ||
          q.quest_type === 'Story Quest' ||
          q.quest_type === 'Main Quest'
        ) &&
        q.status === 'Active'
    ).length;
  const contactsCount =
    (codex.contacts || []).filter((c) => !c.is_dispatch_channel).length ||
    null;
  const knownWorldCount =
    (codex.lorebook?.entities || []).filter((e) => e.is_discovered !== false)
      .length || null;

  const isAnomalous = isAnomalousScenarioKey(session?.scenario);
  useEffect(() => {
    if (!isAnomalous && activeUtilityTab === 'contracts') {
      setActiveUtilityTab('hero');
    }
  }, [isAnomalous, activeUtilityTab]);
  const contractsBadge = session?.contracts_hud?.has_breach
    ? '!'
    : session?.contracts_hud?.available_count > 0
      ? `+${session.contracts_hud.available_count}`
      : session?.contracts_hud?.slot_used > 0
        ? `${session.contracts_hud.slot_used}/${session.contracts_hud.slot_capacity || 2}`
        : null;

  const utilityTabs = [
    {
      id: 'hero',
      label: t('nav.hero'),
      icon: User,
      badge: character?.pending_stat_points ? '!' : null,
    },
    {
      id: 'party',
      label: t('nav.party'),
      icon: Users,
      badge:
        unreadChatCount > 0
          ? unreadChatCount
          : (session.party_members?.length || 1) +
            (session.party_npcs?.length || 0),
      alert: unreadChatCount > 0,
    },
    {
      id: 'inventory',
      label: t('nav.inventory'),
      icon: Package,
      badge: inventory.items?.length || null,
    },
    {
      id: 'quests',
      label: t('nav.quests'),
      icon: Compass,
      badge: activeQuestCount || null,
    },
    {
      id: 'contacts',
      label: t('nav.contacts', 'Contacts'),
      icon: BookUser,
      badge: contactsCount,
    },
    {
      id: 'codex',
      label: t('nav.codex'),
      icon: BookOpen,
      badge: knownWorldCount,
    },
    ...(isAnomalous
      ? [
          {
            id: 'contracts',
            label: t('contracts.nav_label', 'Contracts'),
            icon: Flame,
            badge: contractsBadge,
            alert: Boolean(session?.contracts_hud?.has_breach),
          },
        ]
      : []),
  ];

  const handleToggleWorldMapDrawer = () => {
    setWorldMapTargetLocation(null);
    toggleLeftPanel('map');
  };

  const inCombat = Boolean(
    session?.is_in_combat ||
      session?.in_combat ||
      session?.combat_state?.in_combat ||
      (session?.nearby_enemies || []).some((e) => e && (e.hp ?? 1) > 0) ||
      (session?.monsters || []).some((m) => m && (m.hp ?? 1) > 0)
  );
  const npcCount = Array.isArray(session?.current_npcs)
    ? session.current_npcs.length
    : 0;
  const hasPhoneAlerts = Boolean(
    phone.appointments?.length > 0 || phone.mediaGallery?.length > 0
  );
  const isSmartphoneAvailable = Boolean(
    session?.smartphone_available ?? phone.phoneData?.is_supported ?? phone.phoneData?.supported ?? false
  );
  const cleanDeviceName = formatCleanDeviceName(
    phone.branding?.device_name || t('nav.smartphone', 'Smartphone')
  );
  const phoneAlertCount =
    (phone.appointments?.length || 0) + (phone.mediaGallery?.length || 0);
  const hasUtilityAlert = Boolean(
    character?.pending_stat_points ||
      unreadChatCount > 0 ||
      hasPhoneAlerts ||
      (isAnomalous &&
        (session?.contracts_hud?.has_breach ||
          session?.contracts_hud?.available_count > 0))
  );

  const menuItems = [
    {
      id: 'share',
      label: headerCopied ? t('common.copied') : t('common.share'),
      icon: headerCopied ? Check : Share2,
      onClick: handleShareAdventure,
      keepOpen: true,
      active: headerCopied,
    },
    {
      id: 'contracts',
      label: t('contracts.nav_label', 'Contracts'),
      icon: Flame,
      onClick: () => {
        setActiveUtilityTab('contracts');
        setHudField('leftPanel', 'utility');
      },
      hidden: !isAnomalous,
    },
    {
      id: 'saves',
      label: t('nav.saves'),
      icon: Bookmark,
      onClick: () => setSavesModalOpen(true),
    },
    {
      id: 'settings',
      label: t('nav.settings'),
      icon: Sliders,
      onClick: () => setSettingsModalOpen(true),
    },
    { id: 'div', divider: true },
    {
      id: 'exit',
      label: t('nav.exit_dashboard'),
      icon: ArrowLeft,
      onClick: exitToDashboard,
      hidden: !exitToDashboard,
    },
    {
      id: 'end',
      label: t('nav.end_adventure'),
      icon: FlagOff,
      onClick: () => setEndSessionConfirmOpen(true),
      tone: 'warn',
      hidden: !endSession,
    },
    {
      id: 'logout',
      label: t('dashboard.logout'),
      icon: LogOut,
      onClick: leaveSession,
      tone: 'danger',
    },
  ];

  const menuHeaderSlot = (
    <div className="flex items-center justify-between gap-1">
      <ThemeSwitcher compact />
      <AcrylicModeSwitcher showLabel className="min-w-0 flex-1" />
      <LanguageSwitcher settingsHook={settings} />
    </div>
  );

  const dockProps = {
    session,
    inCombat,
    disabled: waitingForParty,
    processing: processingTurn,
    isStealthActive,
    selectedCombatTarget,
    onToggleStealth: handleToggleStealth,
    onAction: handleAction,
    inventory: inventory?.items || [],
    presentNpcs: session?.current_npcs || [],
    currentUserId: user?.user_id,
  };

  const closeSheetThen = (fn) => () => {
    setMobileSheet(null);
    fn();
  };

  const leftDrawerProps = {
    leftPanel: hud.leftPanel,
    utilityTabs,
    activeUtilityTab,
    setActiveUtilityTab,
    setHudField,
    worldMapTargetLocation,
    setWorldMapTargetLocation,
    setWorldMapExpandedOpen,
    setContractsModalOpen,
    setMerchantModalOpen,
    session,
    user,
    character,
    inventory,
    codex,
    inCombat,
    isStreaming,
    processingTurn: turnBusy,
    onlineUserIds,
    partyChatMessages,
    sendPartyChat,
    allocateStatPoint,
    refreshCharacter,
    handleAction,
    handleFastTravel,
    handleCastSpell,
    handleSessionLoaded,
    handleMessageContact,
    openWorldMap,
    targetContactName,
    setTargetContactName,
    targetContactPulse,
    setTargetContactPulse,
    handleConsumeTargetContact,
  };

  const topLeftControlsProps = {
    session,
    leftPanel: hud.leftPanel,
    clockFormat,
    wsStatus,
    processingTurn: turnBusy,
    inCombat,
    hasUtilityAlert,
    onToggleUtility: () => toggleLeftPanel('utility'),
    onToggleWorldMap: handleToggleWorldMapDrawer,
    onOpenTimeSkip: () => {
      if (!turnBusy && !inCombat) setTimeSkipModalOpen(true);
    },
  };

  const renderHamburgerMenu = () => (
    <GameMenu
      items={menuItems}
      headerSlot={menuHeaderSlot}
      label={t('nav.menu', 'Menu')}
      icon={Menu}
      width={284}
      triggerClassName="hk-acrylic-pill h-10 w-10 grid place-items-center text-gray-100 hover:text-fantasy-accent shrink-0"
    />
  );

  const renderNarrationCard = ({ compactDesktop = false } = {}) => (
    <AcrylicPanel
      variant="reading"
      origin="center"
      className={
        compactDesktop
          ? 'w-full max-w-[46rem] min-h-[12rem] max-h-full flex flex-col overflow-hidden pointer-events-auto'
          : 'flex-1 min-h-0 flex flex-col overflow-hidden'
      }
    >
      <StoryFeed
        history={session.history}
        currentScene={session}
        isStreaming={isStreaming}
        isThinking={isThinking}
        cancellingTurn={cancellingTurn}
        streamingNarrative={streamingNarrative}
        streamingState={streamingState}
        processing={processingTurn}
        pendingAction={pendingAction}
        onCancelTurn={cancelTurn}
        selectedCombatTarget={selectedCombatTarget}
        onSelectCombatTarget={setSelectedCombatTarget}
        showEnemyHp={(settings.settings?.show_enemy_hp ?? 1) === 1}
        showEnemyIntent={(settings.settings?.show_enemy_intent ?? 1) === 1}
        readingMode={readingMode}
        onOpenHistory={() => setHistoryModalOpen(true)}
        onRerollImage={rerollImage}
        rerollingImage={rerollingImage}
      />
    </AcrylicPanel>
  );

  const renderActionPanel = () => (
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
      showEnemyHp={(settings.settings?.show_enemy_hp ?? 1) === 1}
      showEnemyIntent={(settings.settings?.show_enemy_intent ?? 1) === 1}
      processing={processingTurn}
      pendingAction={pendingAction}
      isStreaming={isStreaming}
      waitingForParty={waitingForParty}
      partyStatus={partyStatus}
      onSelectContact={handleOpenNpcInRoster}
      actionError={actionError || stealthError}
      clearActionError={() => {
        setStealthError(null);
        if (clearActionError) clearActionError();
      }}
      onReloadSession={(loadedSess) => {
        if (loadedSess && setSession) {
          setSession(loadedSess);
        } else if (refreshSession) {
          refreshSession();
        }
        if (refreshCharacter) {
          refreshCharacter();
        }
      }}
      onExitToDashboard={exitToDashboard}
      collapsed={hud.actionBarCollapsed}
      onToggleCollapse={() => toggleHudField('actionBarCollapsed')}
    />
  );

  return (
    <div
      style={{
        height: 'var(--app-height, 100dvh)',
        maxHeight: 'var(--app-height, 100dvh)',
      }}
      className="w-full min-w-0 bg-transparent overflow-hidden font-sans"
    >
      {isDesktop ? (
        /* DESKTOP FLOATING SPATIAL HUD (>= 1280px) */
        <div className="h-full w-full p-3 flex gap-3 min-w-0 overflow-hidden">
          <main className="flex-1 min-w-0 flex flex-col gap-2.5 h-full min-h-0">
            {/* Stage Row: Floating Top-Left Controls & Drawer + Full-Height Centered Narration */}
            <div className="relative flex-1 min-h-0 flex min-w-0 pointer-events-none">
              <div className="pointer-events-none absolute inset-y-0 left-0 z-20 flex flex-col gap-2.5 min-h-0 max-w-full">
                <div className="shrink-0 pointer-events-auto w-fit max-w-[max(var(--hk-right-rail-w),calc(50vw_-_23rem_-_1.75rem))]">
                  <GameTopLeftControls {...topLeftControlsProps} />
                </div>

                <AnimatePresence>
                  {hud.leftPanel !== null && (
                    <AcrylicPanel
                      key={`left-rail-${hud.leftPanel}`}
                      variant="panel"
                      origin="left"
                      className={`pointer-events-auto flex-1 min-h-0 flex overflow-hidden ${
                        hud.leftPanel === 'map'
                          ? 'w-[min(48vw,clamp(30rem,32vw,39rem))]'
                          : 'w-[min(46vw,clamp(26.5rem,30vw,37rem))]'
                      }`}
                    >
                      <GameLeftDrawerContent {...leftDrawerProps} />
                    </AcrylicPanel>
                  )}
                </AnimatePresence>
              </div>

              <section
                aria-label={t('nav.reading_scene', 'Current Scene')}
                className="flex-1 min-w-0 min-h-0 flex flex-col items-center justify-start pl-[calc(var(--hk-right-rail-w)+0.75rem)]"
              >
                {renderNarrationCard({ compactDesktop: true })}
              </section>

              <AnimatePresence>
                {inspectedSceneNpc && resolvedSceneNpcProfile && (
                  <AcrylicPanel
                    key="npc-profile-side-card"
                    variant="panel"
                    origin="right"
                    role="complementary"
                    aria-label={t('scene.npc_profile_panel', {
                      name: resolvedSceneNpcProfile.npc?.name || inspectedSceneNpc,
                      defaultValue: `${resolvedSceneNpcProfile.npc?.name || inspectedSceneNpc} Profile`,
                    })}
                    className="pointer-events-auto absolute top-[3.125rem] bottom-0 right-0 z-20 w-[clamp(21rem,24vw,26rem)] max-w-[calc(100%-1rem)] flex flex-col overflow-hidden"
                  >
                    <NpcProfileSideCard
                      profile={resolvedSceneNpcProfile}
                      session={session}
                      codexHook={codex}
                      onClose={() => setInspectedSceneNpc(null)}
                      onOpenInRoster={handleOpenNpcInRoster}
                      onInspectLinkedNpc={(linkedName) => setInspectedSceneNpc(linkedName)}
                    />
                  </AcrylicPanel>
                )}
              </AnimatePresence>
            </div>

            {/* Bottom Dock Row: Collapsible Special Actions Dock + Dedicated Smartphone + Action Choices */}
            <div className="shrink-0 flex items-end gap-3 min-w-0">
              <AcrylicPanel
                variant="panel"
                origin="bottom"
                className="w-[min(34vw,23rem)] 2xl:w-[min(34vw,24.5rem)] shrink-0 overflow-hidden"
              >
                <div
                  className={`px-3 py-2 flex items-center justify-between gap-2 ${
                    !hud.actionsDockCollapsed ? 'border-b border-fantasy-border/25' : ''
                  }`}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Zap size={13} className="text-fantasy-accent shrink-0" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-200 truncate">
                      {t('nav.actions_dock', 'Special Actions')}
                    </span>
                    {hud.actionsDockCollapsed && isStealthActive && (
                      <span className="hk-chip hk-chip-accent text-[10px] shrink-0">🥷</span>
                    )}
                  </div>
                  <MotionButton
                    onClick={() => toggleHudField('actionsDockCollapsed')}
                    className="hk-icon-btn h-7 min-w-7 text-gray-400 hover:text-gray-100 shrink-0"
                    aria-expanded={!hud.actionsDockCollapsed}
                    aria-label={
                      hud.actionsDockCollapsed
                        ? t('nav.expand', 'Expand')
                        : t('nav.collapse', 'Collapse')
                    }
                    title={
                      hud.actionsDockCollapsed
                        ? t('nav.expand', 'Expand')
                        : t('nav.collapse', 'Collapse')
                    }
                  >
                    <ChevronDown
                      size={14}
                      className={`transition-transform duration-200 ${
                        hud.actionsDockCollapsed ? '' : 'rotate-180'
                      }`}
                    />
                  </MotionButton>
                </div>
                <CollapsibleSection isOpen={!hud.actionsDockCollapsed}>
                  <div className="p-2">
                    <TacticalActionDock
                      {...dockProps}
                      onOpenExamine={() => setExamineModalOpen(true)}
                      onOpenQuickBelt={() => {
                        setUseItemInitialTarget(null);
                        setQuickBeltModalOpen(true);
                      }}
                      onOpenGiveGift={() => {
                        setGiveGiftInitialTarget(null);
                        setGiveGiftModalOpen(true);
                      }}
                    />
                  </div>
                </CollapsibleSection>
              </AcrylicPanel>

              {isSmartphoneAvailable && (
                <MotionButton
                  type="button"
                  disabled={inCombat}
                  onClick={() => setPhoneModalOpen(true)}
                  title={hasPhoneAlerts ? `${cleanDeviceName} (${phoneAlertCount})` : cleanDeviceName}
                  aria-label={cleanDeviceName}
                  className={`hk-acrylic-pill w-10 h-10 grid place-items-center shrink-0 relative ${
                    phoneModalOpen
                      ? 'text-fantasy-accent ring-1 ring-fantasy-accent/60'
                      : 'text-gray-100 hover:text-fantasy-accent'
                  } disabled:opacity-45 disabled:cursor-not-allowed`}
                >
                  <Smartphone size={18} />
                  {hasPhoneAlerts && (
                    <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-pink-400 animate-pulse" />
                  )}
                </MotionButton>
              )}

              <div className="flex-1 min-w-0">
                {renderActionPanel()}
              </div>
            </div>
          </main>

          {/* Right Column: Hamburger + Epistemic Watch + NPCs + Latest Outcome/History */}
          <div className="w-[var(--hk-right-rail-w)] flex flex-col gap-2.5 shrink-0 min-h-0 h-full pointer-events-none">
            <div className="flex justify-end shrink-0 pointer-events-auto">
              {renderHamburgerMenu()}
            </div>

            <div className="flex-1 min-h-0 flex flex-col justify-between gap-2.5">
              <div className="min-h-0 flex flex-col gap-2 max-h-[54%] pointer-events-auto">
                <EpistemicWatchStrip
                  session={session}
                  collapsed={hud.epistemicCollapsed}
                  onToggleCollapse={() => toggleHudField('epistemicCollapsed')}
                />
                <PresentNpcsCard
                  session={session}
                  onSelectContact={handleInspectSceneNpc}
                  selectedNpcName={inspectedSceneNpc}
                  onQuickAction={handleAction}
                  collapsed={hud.npcsCollapsed}
                  onToggleCollapse={() => toggleHudField('npcsCollapsed')}
                  className="flex-1"
                />
              </div>

              <div className="min-h-0 flex flex-col justify-end max-h-[46%] pointer-events-auto">
                <LatestOutcomeCard
                  session={session}
                  collapsed={hud.outcomeCollapsed}
                  onToggleCollapse={() => toggleHudField('outcomeCollapsed')}
                  onOpenHistory={() => setHistoryModalOpen(true)}
                />
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* TABLET & MOBILE FLOATING HUD (< 1280px) */
        <div
          className="h-full w-full p-2 sm:p-3 flex flex-col gap-2 min-w-0 overflow-hidden"
          style={{ paddingBottom: 'max(0.5rem, env(safe-area-inset-bottom, 0px))' }}
        >
          {/* Floating Top Bar */}
          <header className="flex items-center gap-1.5 shrink-0 min-w-0">
            <GameTopLeftControls {...topLeftControlsProps} compact />
            {renderHamburgerMenu()}
          </header>

          {/* Center Narration + Action Bar */}
          <main className="flex-1 min-h-0 flex flex-col gap-2 min-w-0">
            {renderNarrationCard({ compactDesktop: false })}
            {renderActionPanel()}
          </main>

          {/* Slim Non-Scrolling Bottom Quick-Access Strip */}
          <div className={`shrink-0 grid ${isSmartphoneAvailable ? 'grid-cols-[repeat(4,minmax(0,1fr))_2.75rem]' : 'grid-cols-4'} gap-1.5`}>
            <MotionButton
              onClick={() => setMobileSheet('npcs')}
              className="hk-acrylic-pill min-h-[2.75rem] sm:h-10 py-1 px-1.5 sm:px-2 flex flex-col sm:flex-row items-center justify-center gap-0.5 sm:gap-1.5 text-[10px] sm:text-xs font-semibold text-gray-100 min-w-0 relative"
            >
              <Users size={14} className="text-fantasy-accent shrink-0" />
              <span className="truncate max-w-full">{t('scene.present', 'Present')}</span>
              {npcCount > 0 && (
                <span className="sm:static absolute top-1 right-1.5 hk-chip text-[9px] sm:text-[0.765rem] tabular-nums shrink-0 leading-none">
                  {npcCount}
                </span>
              )}
            </MotionButton>

            <MotionButton
              onClick={() => setMobileSheet('outcome')}
              className="hk-acrylic-pill min-h-[2.75rem] sm:h-10 py-1 px-1.5 sm:px-2 flex flex-col sm:flex-row items-center justify-center gap-0.5 sm:gap-1.5 text-[10px] sm:text-xs font-semibold text-gray-100 min-w-0"
            >
              <ScrollText size={14} className="text-fantasy-accent shrink-0" />
              <span className="truncate max-w-full">{t('nav.outcomes', 'Outcome')}</span>
            </MotionButton>

            <MotionButton
              onClick={() => setHistoryModalOpen(true)}
              className="hk-acrylic-pill min-h-[2.75rem] sm:h-10 py-1 px-1.5 sm:px-2 flex flex-col sm:flex-row items-center justify-center gap-0.5 sm:gap-1.5 text-[10px] sm:text-xs font-semibold text-gray-100 min-w-0"
            >
              <History size={14} className="text-fantasy-accent shrink-0" />
              <span className="truncate max-w-full">{t('history.title', 'History')}</span>
            </MotionButton>

            <MotionButton
              onClick={() => setMobileSheet('actions')}
              className="hk-acrylic-pill min-h-[2.75rem] sm:h-10 py-1 px-1.5 sm:px-2 flex flex-col sm:flex-row items-center justify-center gap-0.5 sm:gap-1.5 text-[10px] sm:text-xs font-semibold text-gray-100 min-w-0 relative"
            >
              <Zap size={14} className="text-fantasy-accent shrink-0" />
              <span className="truncate max-w-full">
                {t('nav.actions_dock', 'Actions')}
              </span>
              {isStealthActive && (
                <span className="sm:static absolute top-1.5 right-2 w-1.5 h-1.5 rounded-full bg-fantasy-accent animate-pulse shrink-0" />
              )}
            </MotionButton>

            {isSmartphoneAvailable && (
              <MotionButton
                type="button"
                disabled={inCombat}
                onClick={() => setPhoneModalOpen(true)}
                title={hasPhoneAlerts ? `${cleanDeviceName} (${phoneAlertCount})` : cleanDeviceName}
                aria-label={cleanDeviceName}
                className={`hk-acrylic-pill min-h-[2.75rem] sm:h-10 py-1 px-1.5 flex items-center justify-center min-w-0 relative ${
                  phoneModalOpen
                    ? 'text-fantasy-accent ring-1 ring-fantasy-accent/60'
                    : 'text-gray-100 hover:text-fantasy-accent'
                } disabled:opacity-45 disabled:cursor-not-allowed`}
              >
                <Smartphone size={16} />
                {hasPhoneAlerts && (
                  <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-pink-400 animate-pulse shrink-0" />
                )}
              </MotionButton>
            )}
          </div>
        </div>
      )}

      {/* Overlay Left Drawer & Slide-Up Mobile/Tablet Acrylic Sheets (< 1280px) */}
      {typeof document !== 'undefined' &&
        createPortal(
          <>
            <AnimatePresence>
              {!isDesktop && hud.leftPanel !== null && (
                <motion.div
                  data-motion="true"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: reducedMotion ? 0.12 : 0.2, ease: EASE_OUT }}
                  className="fixed inset-0 z-50 flex bg-black/60 backdrop-blur-sm p-2 sm:p-3"
                  onClick={() => setHudField('leftPanel', null)}
                >
                  <motion.div
                    role="dialog"
                    aria-modal="true"
                    aria-label={
                      hud.leftPanel === 'map'
                        ? t('nav.map', 'World Map')
                        : t('nav.utility', 'Utilities')
                    }
                    initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -24 }}
                    animate={reducedMotion ? { opacity: 1 } : { opacity: 1, x: 0 }}
                    exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: -24 }}
                    transition={reducedMotion ? { duration: 0.14 } : SPRING_PANEL}
                    onClick={(e) => e.stopPropagation()}
                    className="hk-acrylic relative w-[min(30rem,94dvw)] h-full flex overflow-hidden z-10"
                  >
                    <GameLeftDrawerContent {...leftDrawerProps} />
                  </motion.div>
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence>
              {!isDesktop && mobileSheet !== null && (
                <motion.div
                  data-motion="true"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: reducedMotion ? 0.12 : 0.2, ease: EASE_OUT }}
                  className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:p-4"
                  onClick={() => setMobileSheet(null)}
                >
                  <motion.div
                    role="dialog"
                    aria-modal="true"
                    aria-label={
                      mobileSheet === 'npcs'
                        ? t('scene.present', 'Present in Scene')
                        : mobileSheet === 'outcome'
                          ? t('scene.outcomes_title', 'Outcomes')
                          : t('nav.actions_dock', 'Special Actions')
                    }
                    initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 28 }}
                    animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
                    exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 28 }}
                    transition={reducedMotion ? { duration: 0.14 } : SPRING_PANEL}
                    onClick={(e) => e.stopPropagation()}
                    className="hk-acrylic w-full max-w-xl max-h-[78dvh] rounded-b-none sm:rounded-b-2xl flex flex-col overflow-hidden z-10"
                    style={{
                      paddingBottom: 'env(safe-area-inset-bottom, 0px)',
                    }}
                  >
                    <div className="px-4 py-2 border-b border-fantasy-border/30 flex items-center justify-between gap-2 shrink-0">
                      <span className="text-xs font-semibold uppercase tracking-wider text-fantasy-accent">
                        {mobileSheet === 'npcs'
                          ? t('scene.present', 'Present in Scene')
                          : mobileSheet === 'outcome'
                            ? t('scene.outcomes_title', 'Outcomes')
                            : t('nav.actions_dock', 'Special Actions')}
                      </span>
                      <MotionButton
                        onClick={() => setMobileSheet(null)}
                        className="hk-icon-btn h-7 min-w-7"
                        aria-label={t('common.close', 'Close')}
                      >
                        <X size={16} />
                      </MotionButton>
                    </div>

                    {mobileSheet === 'npcs' && (
                      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                        {inspectedSceneNpc && resolvedSceneNpcProfile ? (
                          <NpcProfileSideCard
                            isSheet
                            profile={resolvedSceneNpcProfile}
                            session={session}
                            codexHook={codex}
                            onBack={() => setInspectedSceneNpc(null)}
                            onClose={() => setMobileSheet(null)}
                            onOpenInRoster={handleOpenNpcInRoster}
                            onInspectLinkedNpc={(linkedName) => setInspectedSceneNpc(linkedName)}
                          />
                        ) : (
                          <>
                            <EpistemicWatchStrip session={session} isSheet />
                            <PresentNpcsCard
                              session={session}
                              onSelectContact={handleInspectSceneNpc}
                              selectedNpcName={inspectedSceneNpc}
                              onQuickAction={handleAction}
                              isSheet
                              className="flex-1"
                            />
                          </>
                        )}
                      </div>
                    )}

                    {mobileSheet === 'outcome' && (
                      <LatestOutcomeCard
                        session={session}
                        isSheet
                        onOpenHistory={() => {
                          setMobileSheet(null);
                          setHistoryModalOpen(true);
                        }}
                        className="flex-1"
                      />
                    )}

                    {mobileSheet === 'actions' && (
                      <div className="p-3 overflow-y-auto custom-scrollbar">
                        <TacticalActionDock
                          {...dockProps}
                          compact
                          onOpenExamine={closeSheetThen(() => setExamineModalOpen(true))}
                          onOpenQuickBelt={closeSheetThen(() => {
                            setUseItemInitialTarget(null);
                            setQuickBeltModalOpen(true);
                          })}
                          onOpenGiveGift={closeSheetThen(() => {
                            setGiveGiftInitialTarget(null);
                            setGiveGiftModalOpen(true);
                          })}
                        />
                      </div>
                    )}
                  </motion.div>
                </motion.div>
              )}
            </AnimatePresence>
          </>,
          document.body
        )}

      <GameViewModals
        session={session}
        setSession={setSession}
        user={user}
        character={character}
        inventory={inventory}
        codex={codex}
        phone={phone}
        settings={settings}
        inCombat={inCombat}
        isStealthActive={isStealthActive}
        processingTurn={turnBusy}
        rerollImage={rerollImage}
        rerollingImage={rerollingImage}
        handleFastTravel={handleFastTravel}
        handleAction={handleAction}
        handleSessionLoaded={handleSessionLoaded}
        refreshCharacter={refreshCharacter}
        historyModalOpen={historyModalOpen}
        setHistoryModalOpen={setHistoryModalOpen}
        worldMapExpandedOpen={worldMapExpandedOpen}
        setWorldMapExpandedOpen={setWorldMapExpandedOpen}
        worldMapTargetLocation={worldMapTargetLocation}
        setWorldMapTargetLocation={setWorldMapTargetLocation}
        merchantModalOpen={merchantModalOpen}
        setMerchantModalOpen={setMerchantModalOpen}
        phoneModalOpen={phoneModalOpen}
        setPhoneModalOpen={setPhoneModalOpen}
        phoneInitialNpc={phoneInitialNpc}
        setPhoneInitialNpc={setPhoneInitialNpc}
        savesModalOpen={savesModalOpen}
        setSavesModalOpen={setSavesModalOpen}
        settingsModalOpen={settingsModalOpen}
        setSettingsModalOpen={setSettingsModalOpen}
        examineModalOpen={examineModalOpen}
        setExamineModalOpen={setExamineModalOpen}
        quickBeltModalOpen={quickBeltModalOpen}
        setQuickBeltModalOpen={setQuickBeltModalOpen}
        useItemInitialTarget={useItemInitialTarget}
        setUseItemInitialTarget={setUseItemInitialTarget}
        giveGiftModalOpen={giveGiftModalOpen}
        setGiveGiftModalOpen={setGiveGiftModalOpen}
        giveGiftInitialTarget={giveGiftInitialTarget}
        setGiveGiftInitialTarget={setGiveGiftInitialTarget}
        contractsModalOpen={contractsModalOpen}
        setContractsModalOpen={setContractsModalOpen}
        timeSkipModalOpen={timeSkipModalOpen}
        setTimeSkipModalOpen={setTimeSkipModalOpen}
        endSessionConfirmOpen={endSessionConfirmOpen}
        setEndSessionConfirmOpen={setEndSessionConfirmOpen}
        endingSessionBusy={endingSessionBusy}
        onConfirmEndSession={handleConfirmEndSession}
      />
    </div>
  );
};

export default GameView;
