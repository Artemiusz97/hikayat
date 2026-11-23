import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  Map,
  MapPin,
  Menu,
  Package,
  ScrollText,
  Share2,
  Sliders,
  Smartphone,
  User,
  Users,
  WifiOff,
  X,
  Zap,
} from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { apiCall } from '../api/client';
import CharacterSheet from '../components/Sidebar/CharacterSheet';
import InventoryPanel from '../components/Sidebar/InventoryPanel';
import PartyWidget from '../components/Sidebar/PartyWidget';
import ContactsPanel from '../components/Sidebar/ContactsPanel';
import NpcProfileSideCard from '../components/Sidebar/NpcProfileSideCard';
import QuestLogPanel from '../components/Sidebar/QuestLogPanel';
import CodexPanel from '../components/Sidebar/CodexPanel';
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
import ConfirmDialog from '../components/Common/ConfirmDialog';
import {
  AcrylicPanel,
  CollapsibleSection,
  EASE_OUT,
  LazyMount,
  MotionButton,
  SPRING_PANEL,
  isTopEscapeLayer,
  registerEscapeLayer,
} from '../components/Common/MotionPrimitives';
import { copyToClipboard } from '../utils/clipboard';

const PhoneModal = lazy(() => import('../components/Phone/PhoneModal'));
const MerchantModal = lazy(() => import('../components/Merchant/MerchantModal'));
const SavesModal = lazy(() => import('../components/Saves/SavesModal'));
const SettingsModal = lazy(() => import('../components/Settings/SettingsModal'));
const WorldMapModal = lazy(() => import('../components/Modals/WorldMapModal'));
const TurnHistoryModal = lazy(() => import('../components/Modals/TurnHistoryModal'));
const TimeSkipModal = lazy(() => import('../components/Modals/TimeSkipModal'));
const QuickBeltPopover = lazy(() => import('../components/Modals/QuickBeltPopover'));
const GiveGiftModal = lazy(() => import('../components/Modals/GiveGiftModal'));
const ExamineModal = lazy(() => import('../components/Modals/ExamineModal'));
const EntityContractsModal = lazy(() => import('../components/Modals/EntityContractsModal'));
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
import {
  formatClockTime,
  getDayOfWeekLabel,
  getTimeOfDayPhaseInfo,
} from '../utils/timeFormat';

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

  useEffect(() => {
    if (isDesktop || hud.leftPanel === null) return undefined;
    const token = Symbol('mobile-left-drawer-esc');
    const unregister = registerEscapeLayer(token);
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        setHudField('leftPanel', null);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      unregister();
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }, [isDesktop, hud.leftPanel, setHudField]);

  useEffect(() => {
    if (isDesktop || mobileSheet === null) return undefined;
    const token = Symbol('mobile-sheet-esc');
    const unregister = registerEscapeLayer(token);
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        setMobileSheet(null);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      unregister();
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }, [isDesktop, mobileSheet]);

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

  useEffect(() => {
    if (!isDesktop || !inspectedSceneNpc) return undefined;
    const token = Symbol('npc-profile-side-esc');
    const unregister = registerEscapeLayer(token);
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        setInspectedSceneNpc(null);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      unregister();
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }, [isDesktop, inspectedSceneNpc]);

  useEffect(() => {
    if (isDesktop || mobileSheet !== 'npcs' || !inspectedSceneNpc) return undefined;
    const token = Symbol('mobile-npc-profile-esc');
    const unregister = registerEscapeLayer(token);
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        setInspectedSceneNpc(null);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      unregister();
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }, [isDesktop, mobileSheet, inspectedSceneNpc]);

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

  useEffect(() => {
    const isHidden = session?.stealth_state?.is_hidden;
    if (typeof isHidden === 'boolean') {
      setIsStealthActive(isHidden);
    }
  }, [session?.stealth_state?.is_hidden]);

  const handleToggleStealth = async () => {
    if (stealthPendingRef.current) return;
    const prevState = isStealthActive;
    const nextState = !prevState;
    setIsStealthActive(nextState);
    setStealthError(null);
    if (isValidSessionId(session?.id) && user?.user_id) {
      stealthPendingRef.current = true;
      try {
        const res = await apiCall('/api/adventure/toggle_stealth', {
          method: 'POST',
          body: JSON.stringify({
            session_id: session.id,
            user_id: user.user_id,
            active: nextState,
          }),
        });
        if (res?.session && setSession) {
          setSession((prev) => ({
            ...res.session,
            scene_image_url:
              res.session?.scene_image_url || prev?.scene_image_url || null,
          }));
        }
      } catch (err) {
        console.warn('Failed to sync stealth stance to server:', err);
        setIsStealthActive(prevState);
        setStealthError(err?.message || 'Failed to sync stealth stance.');
      } finally {
        stealthPendingRef.current = false;
      }
    }
  };

  const handleAction = async (actionData) => {
    const finalAction = { ...actionData };
    const intent = finalAction.intent || '';
    const isVoluntaryDisengage =
      intent === 'rest_sleep' || intent === 'dialogue_init';

    if (isVoluntaryDisengage) {
      setIsStealthActive(false);
      finalAction.is_stealth = false;
    } else if (isStealthActive && finalAction.is_stealth !== false) {
      finalAction.is_stealth = true;
      finalAction.stance = finalAction.stance || 'stealth';
    }

    const outcome = await submitAction(finalAction);
    if (outcome?.status === 'accepted') {
      return;
    }
    const updatedStealth = outcome?.session?.stealth_state || outcome?.stealth_state;
    if (updatedStealth && typeof updatedStealth.is_hidden === 'boolean') {
      setIsStealthActive(updatedStealth.is_hidden);
    }
  };

  const handleFastTravel = async (destination) => {
    if (!destination || processingTurn) return;
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
    if (!spell?.name || processingTurn) return;
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

  const renderUtilityContent = () => {
    switch (activeUtilityTab) {
      case 'contracts':
        return (
          <Suspense fallback={<div className="p-4 text-xs text-gray-400">{t('common.loading', 'Loading...')}</div>}>
            <EntityContractsModal
              mode="drawer"
              isOpen={true}
              onClose={() => setHudField('leftPanel', null)}
              onExpandModal={() => {
                setHudField('leftPanel', null);
                setContractsModalOpen(true);
              }}
              session={session}
              user={user}
              onSessionUpdated={handleSessionLoaded}
              onContractMutated={() => {
                refreshCharacter();
                inventory.refreshInventory();
                codex.refreshCodex();
              }}
            />
          </Suspense>
        );
      case 'inventory':
        return (
          <InventoryPanel
            inventoryHook={inventory}
            onRefreshCharacter={refreshCharacter}
            onRefreshCodex={codex.refreshCodex}
            sessionId={session?.id}
            session={session}
            onAction={handleAction}
            inCombat={inCombat}
            currentUserId={user?.user_id}
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
              setTargetContactPulse((prev) => prev + 1);
              setActiveUtilityTab('codex');
            }}
            targetContactName={targetContactName}
            targetContactPulse={targetContactPulse}
            onConsumeTargetContact={handleConsumeTargetContact}
          />
        );
      case 'quests':
        return (
          <QuestLogPanel
            codexHook={codex}
            onRefreshCharacter={refreshCharacter}
            character={character}
            session={session}
            scenario={session?.scenario || character?.scenario}
            onOpenWorldMap={(targetLoc) => openWorldMap(targetLoc)}
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
            onConsumeTargetContact={handleConsumeTargetContact}
            isStreaming={isStreaming}
            processingTurn={processingTurn}
            onJumpToSavedContact={(npcName) => {
              setTargetContactName(npcName);
              setTargetContactPulse((prev) => prev + 1);
              setActiveUtilityTab('contacts');
            }}
          />
        );
      case 'hero':
      default:
        return (
          <CharacterSheet
            character={
              session?.player_clothing_status && character
                ? {
                    ...character,
                    clothing_status: session.player_clothing_status,
                  }
                : character
            }
            scenario={session?.scenario || character?.scenario}
            onAllocateStat={allocateStatPoint}
            onCastSpell={handleCastSpell}
            onRefreshCharacter={refreshCharacter}
            processingTurn={processingTurn}
          />
        );
    }
  };

  const handleToggleWorldMapDrawer = () => {
    setWorldMapTargetLocation(null);
    toggleLeftPanel('map');
  };

  const renderLeftPanelContent = () => {
    if (hud.leftPanel === 'map') {
      return (
        <Suspense fallback={<div className="p-4 text-xs text-gray-400">{t('common.loading', 'Loading...')}</div>}>
          <WorldMapModal
            mode="drawer"
            isOpen={true}
            onClose={() => {
              setWorldMapTargetLocation(null);
              setHudField('leftPanel', null);
            }}
            onExpandModal={() => {
              setHudField('leftPanel', null);
              setWorldMapExpandedOpen(true);
            }}
            session={session}
            user={user}
            onTravel={handleFastTravel}
            initialTargetLocation={worldMapTargetLocation}
            processingTurn={processingTurn}
          />
        </Suspense>
      );
    }

    const activeTabMeta =
      utilityTabs.find((tb) => tb.id === activeUtilityTab) || utilityTabs[0];

    return (
      <div className="flex flex-1 min-h-0 min-w-0 overflow-hidden">
        {/* Vertical Icon Rail */}
        <nav
          aria-label={t('nav.utility', 'Utilities')}
          className="w-[3.25rem] shrink-0 border-r border-fantasy-border/30 py-2.5 flex flex-col items-center gap-1.5"
        >
          {utilityTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeUtilityTab === tab.id;
            return (
              <MotionButton
                key={tab.id}
                onClick={() => setActiveUtilityTab(tab.id)}
                title={tab.label}
                aria-label={tab.label}
                aria-current={isActive ? 'page' : undefined}
                className={`relative w-10 h-10 rounded-xl grid place-items-center transition-colors ${
                  isActive
                    ? 'bg-fantasy-accent text-black shadow-sm'
                    : 'text-gray-300 hover:text-gray-50 hover:bg-gray-500/15'
                }`}
              >
                <Icon size={18} />
                {tab.badge != null && (
                  <span
                    className={`absolute -top-1 -right-1 min-w-[0.95rem] h-[0.95rem] px-1 rounded-full text-[9px] font-bold leading-[0.95rem] text-center ${
                      tab.badge === '!' || tab.alert
                        ? 'bg-emerald-400 text-black animate-pulse'
                        : isActive
                          ? 'bg-black/80 text-white'
                          : 'bg-gray-600 text-gray-100'
                    }`}
                  >
                    {tab.badge}
                  </span>
                )}
              </MotionButton>
            );
          })}
        </nav>

        {/* Borderless Utility Content Pane */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-fantasy-border/25 flex items-center justify-between gap-2 shrink-0">
            <span className="text-xs font-semibold uppercase tracking-wider text-fantasy-accent truncate">
              {activeTabMeta.label}
            </span>
            <MotionButton
              onClick={() => setHudField('leftPanel', null)}
              className="hk-icon-btn h-7 min-w-7"
              aria-label={t('common.close', 'Close')}
              title={t('common.close', 'Close')}
            >
              <X size={15} />
            </MotionButton>
          </div>
          <div
            className={
              activeUtilityTab === 'contracts'
                ? 'hk-utility-pane flex-1 min-h-0 flex flex-col overflow-hidden'
                : 'hk-utility-pane flex-1 min-h-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable] custom-scrollbar p-3.5 flex flex-col'
            }
          >
            {renderUtilityContent()}
          </div>
        </div>
      </div>
    );
  };

  const locationLabel = (() => {
    const raw = session?.current_location || '';
    const parts = String(raw)
      .split(/\s*(?:->|→|➔|>|›|»|\|)\s*/)
      .filter(Boolean);
    return parts[parts.length - 1] || session?.scene_title || 'Hikayat';
  })();
  const currentDay = Number(session?.current_day || 1);
  const currentMinute =
    session?.current_minute !== undefined && session?.current_minute !== null
      ? Number(session.current_minute)
      : 480;
  const turnCount = Number.isFinite(Number(session?.turn_count))
    ? Math.max(0, Math.floor(Number(session.turn_count)))
    : Array.isArray(session?.history)
      ? session.history.filter(
          (entry) => entry && typeof entry === 'object' && entry.type !== 'scene'
        ).length
      : 0;
  const dayLabel = getDayOfWeekLabel(currentDay, t);
  const shortDayLabel = getDayOfWeekLabel(currentDay, t, { short: true });
  const formattedClock = formatClockTime(currentMinute, clockFormat);
  const timePhase = getTimeOfDayPhaseInfo(currentMinute, t);
  const TimePhaseIcon = timePhase.Icon;
  const turnLabel = t('scene.turn_counter', {
    count: turnCount,
    defaultValue: `Turn ${turnCount}`,
  });
  const shortTurnLabel = t('scene.turn_counter_short', {
    count: turnCount,
    defaultValue: `T${turnCount}`,
  });
  const dayCountLabel = t('scene.day_counter', {
    count: currentDay,
    defaultValue: `Day ${currentDay}`,
  });
  const shortDayCountLabel = t('scene.day_counter_short', {
    count: currentDay,
    defaultValue: `D${currentDay}`,
  });
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

  const renderTopLeftControls = (compact = false) => (
    <div
      className={
        compact
          ? 'flex items-center gap-1.5 min-w-0 flex-1'
          : 'flex flex-wrap items-center gap-1.5 min-w-0'
      }
    >
      <MotionButton
        onClick={() => toggleLeftPanel('utility')}
        aria-expanded={hud.leftPanel === 'utility'}
        aria-label={t('nav.utility', 'Utilities')}
        title={t('nav.utility', 'Utilities')}
        className={`hk-acrylic-pill w-10 h-10 grid place-items-center shrink-0 relative ${
          hud.leftPanel === 'utility'
            ? 'text-fantasy-accent ring-1 ring-fantasy-accent/60'
            : 'text-gray-100 hover:text-fantasy-accent'
        }`}
      >
        <Compass size={18} />
        {hasUtilityAlert && (
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-fantasy-accent animate-pulse" />
        )}
      </MotionButton>

      <MotionButton
        onClick={handleToggleWorldMapDrawer}
        aria-expanded={hud.leftPanel === 'map'}
        aria-label={t('nav.map', 'World Map')}
        title={t('nav.map', 'World Map')}
        className={`hk-acrylic-pill w-10 h-10 grid place-items-center shrink-0 ${
          hud.leftPanel === 'map'
            ? 'text-fantasy-accent ring-1 ring-fantasy-accent/60'
            : 'text-gray-100 hover:text-fantasy-accent'
        }`}
      >
        <Map size={18} />
      </MotionButton>

      <MotionButton
        onClick={handleToggleWorldMapDrawer}
        title={session?.current_location || locationLabel}
        className={`hk-acrylic-pill min-h-10 h-auto py-1.5 px-3.5 inline-flex items-center gap-2 text-left min-w-0 ${
          compact ? 'flex-1' : 'max-w-[clamp(10rem,13vw,22rem)]'
        }`}
      >
        <MapPin size={14} className="text-fantasy-accent shrink-0" />
        <span className="text-xs font-semibold text-gray-100 truncate">
          {locationLabel}
        </span>
      </MotionButton>

      <MotionButton
        onClick={() => {
          if (!processingTurn && !inCombat) setTimeSkipModalOpen(true);
        }}
        disabled={processingTurn || inCombat}
        title={
          inCombat
            ? `${dayLabel} • ${formattedClock} (${timePhase.label}) • ${dayCountLabel} • ${turnLabel} — ${t('actions.cannot_rest_combat', 'Cannot rest during combat')}`
            : `${dayLabel} • ${formattedClock} (${timePhase.label}) • ${dayCountLabel} • ${turnLabel} — ${t('actions.open_chronos', 'Open Chronos Dial to advance time and rest')}`
        }
        className={`hk-acrylic-pill min-h-10 h-auto py-1.5 ${
          compact ? 'px-2.5' : 'px-3.5'
        } inline-flex items-center gap-1.5 shrink-0 disabled:opacity-75`}
      >
        <TimePhaseIcon
          size={14}
          className={`${timePhase.colorClass} shrink-0`}
          aria-hidden="true"
        />
        <span
          className={`${
            compact ? 'text-[11px]' : 'text-xs'
          } font-semibold text-gray-100 tabular-nums whitespace-nowrap`}
        >
          {compact
            ? `${shortDayLabel} • ${formattedClock} • ${shortDayCountLabel} • ${shortTurnLabel}`
            : `${dayLabel} • ${formattedClock} • ${dayCountLabel} • ${turnLabel}`}
        </span>
      </MotionButton>

      {wsStatus === 'reconnecting' && (
        <span
          role="status"
          aria-live="polite"
          className="hk-acrylic-pill h-10 px-3 inline-flex items-center gap-1.5 shrink-0 text-xs font-semibold text-amber-300 border border-amber-500/40 bg-amber-950/50"
        >
          <WifiOff size={13} className="animate-pulse shrink-0" />
          <span className={compact ? 'hidden sm:inline' : ''}>
            {t('status.reconnecting', 'Reconnecting…')}
          </span>
        </span>
      )}
    </div>
  );

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
          {/* Left + Center Workspace: Floating Top Controls & Drawer + Full-Height Top-Level Centered Narration + Bottom Action Dock Row */}
          <main className="flex-1 min-w-0 flex flex-col gap-2.5 h-full min-h-0">
            {/* Stage Row: Floating Top-Left Controls & Drawer + Full-Height Centered Narration */}
            <div className="relative flex-1 min-h-0 flex min-w-0 pointer-events-none">
              <div className="pointer-events-none absolute inset-y-0 left-0 z-20 flex flex-col gap-2.5 min-h-0 max-w-full">
                <div className="shrink-0 pointer-events-auto w-fit max-w-[max(var(--hk-right-rail-w),calc(50vw_-_23rem_-_1.75rem))]">
                  {renderTopLeftControls()}
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
                      {renderLeftPanelContent()}
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
            {renderTopLeftControls(true)}
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
                    {renderLeftPanelContent()}
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

      {/* Full Turn History Chronicle Modal */}
      <LazyMount open={historyModalOpen}>
        <TurnHistoryModal
          isOpen={historyModalOpen}
          onClose={() => setHistoryModalOpen(false)}
          session={session}
          scenario={session?.scenario || character?.scenario}
          onRerollImage={rerollImage}
          rerollingImage={rerollingImage}
        />
      </LazyMount>

      {/* Expanded Full-Screen World Atlas Modal */}
      <LazyMount open={worldMapExpandedOpen}>
        <WorldMapModal
          mode="modal"
          isOpen={worldMapExpandedOpen}
          onClose={() => {
            setWorldMapExpandedOpen(false);
            setWorldMapTargetLocation(null);
          }}
          session={session}
          user={user}
          onTravel={handleFastTravel}
          initialTargetLocation={worldMapTargetLocation}
          processingTurn={processingTurn}
        />
      </LazyMount>

      {/* Merchant Emporium Modal */}
      <LazyMount open={merchantModalOpen}>
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
      </LazyMount>

      {/* Smartphone OS Modal */}
      <LazyMount open={phoneModalOpen}>
        <PhoneModal
          isOpen={phoneModalOpen}
          onClose={() => setPhoneModalOpen(false)}
          phoneHook={phone}
          codexHook={codex}
          session={session}
          user={user}
          imageGenMode={settings.settings?.image_gen_enabled}
          initialChatNpc={phoneInitialNpc}
          onClearInitialChatNpc={() => setPhoneInitialNpc(null)}
          onRefreshInventory={inventory.refreshInventory}
          onRefreshCodex={codex.refreshCodex}
          onRefreshCharacter={refreshCharacter}
        />
      </LazyMount>

      {/* Save / Load Checkpoints Modal */}
      <LazyMount open={savesModalOpen}>
        <SavesModal
          isOpen={savesModalOpen}
          onClose={() => setSavesModalOpen(false)}
          user={user}
          onSessionLoaded={handleSessionLoaded}
        />
      </LazyMount>

      {/* Chronicle Preferences & Streaming Settings Modal */}
      <LazyMount open={settingsModalOpen}>
        <SettingsModal
          isOpen={settingsModalOpen}
          onClose={() => setSettingsModalOpen(false)}
          settingsHook={settings}
          user={user}
          session={session}
          onSessionUpdated={handleSessionLoaded}
          onRefreshCharacter={refreshCharacter}
          onRefreshCodex={codex.refreshCodex}
          onImageModeSaved={(nextMode) => {
            if (
              session &&
              (Number(session.capacity || 1) <= 1 ||
                String(session.host_user_id) === String(user?.user_id))
            ) {
              setSession((prev) => (prev ? { ...prev, image_gen_enabled: nextMode } : prev));
              phone.refreshPhone?.();
            }
          }}
        />
      </LazyMount>

      {/* Zero-Turn Async Examine / Intel Modal */}
      <LazyMount open={examineModalOpen}>
        <ExamineModal
          isOpen={examineModalOpen}
          onClose={() => setExamineModalOpen(false)}
          session={session}
          user={user}
          inCombat={inCombat}
          processing={processingTurn}
          onTargetUseItem={(target) => {
            setExamineModalOpen(false);
            setUseItemInitialTarget(target);
            setQuickBeltModalOpen(true);
          }}
          onTargetGiveGift={(target) => {
            setExamineModalOpen(false);
            setGiveGiftInitialTarget(target);
            setGiveGiftModalOpen(true);
          }}
          onPickupItem={(rawName, displayName) => {
            setExamineModalOpen(false);
            handleAction({
              choice_index: null,
              direct_choice: {
                label: `Pick up ${displayName || rawName}`,
                pickup_item_name: rawName,
                stat: 'FREE',
                requirement: 0,
              },
            });
          }}
          onOpenWorldMap={(locName) => {
            setWorldMapTargetLocation(locName);
            setWorldMapExpandedOpen(true);
          }}
        />
      </LazyMount>

      {/* Contextual Use Item Modal */}
      <LazyMount open={quickBeltModalOpen}>
        <QuickBeltPopover
          isOpen={quickBeltModalOpen}
          onClose={() => setQuickBeltModalOpen(false)}
          items={inventory?.items}
          inventoryHook={inventory}
          session={session}
          character={character}
          currentUserId={user?.user_id}
          presentNpcs={session?.current_npcs || []}
          inCombat={inCombat}
          isStealthActive={isStealthActive}
          initialTarget={useItemInitialTarget}
          onClearInitialTarget={() => setUseItemInitialTarget(null)}
          onAction={handleAction}
          onRefreshCharacter={refreshCharacter}
          processing={processingTurn}
        />
      </LazyMount>

      {/* Give Gift / Transfer Item Modal */}
      <LazyMount open={giveGiftModalOpen}>
        <GiveGiftModal
          isOpen={giveGiftModalOpen}
          onClose={() => setGiveGiftModalOpen(false)}
          items={inventory?.items}
          inventoryHook={inventory}
          session={session}
          presentNpcs={session?.current_npcs || []}
          currentUserId={user?.user_id}
          initialTarget={giveGiftInitialTarget}
          onClearInitialTarget={() => setGiveGiftInitialTarget(null)}
          onAction={handleAction}
          processing={processingTurn}
        />
      </LazyMount>

      {/* Entity Contracts & Devil Pacts Modal */}
      {isAnomalousScenarioKey(session?.scenario) && (
        <LazyMount open={contractsModalOpen}>
          <EntityContractsModal
            isOpen={contractsModalOpen}
            onClose={() => setContractsModalOpen(false)}
            session={session}
            user={user}
            onSessionUpdated={handleSessionLoaded}
            onContractMutated={() => {
              refreshCharacter();
              inventory.refreshInventory();
              codex.refreshCodex();
            }}
          />
        </LazyMount>
      )}

      {/* Chronos Dial Time Skip Modal */}
      <LazyMount open={timeSkipModalOpen}>
        <TimeSkipModal
          isOpen={timeSkipModalOpen}
          onClose={() => setTimeSkipModalOpen(false)}
          session={session}
          phoneHook={phone}
          onAction={handleAction}
          processing={processingTurn}
        />
      </LazyMount>

      <ConfirmDialog
        isOpen={endSessionConfirmOpen}
        onClose={() => setEndSessionConfirmOpen(false)}
        onConfirm={handleConfirmEndSession}
        busy={endingSessionBusy}
        tone="danger"
        title={t('dashboard.confirm_end_session_title', 'End Adventure Session?')}
        message={t('dashboard.confirm_end_session', 'End this adventure session?')}
        confirmLabel={t('dashboard.end', 'End')}
      />
    </div>
  );
};

export default GameView;
