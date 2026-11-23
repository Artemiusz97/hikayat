import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import {
  X, Camera, Video, MessageSquare, Rss, Wifi,
  Calendar, ChevronLeft, ShoppingBag, ShieldAlert, Home,
  Settings, Sparkles, RefreshCw, Image as ImageIcon, Check, Loader2, Play
} from 'lucide-react';
import { apiCall } from '../../api/client';
import { formatClockTime } from '../../utils/timeFormat';
import { useUiPreferences } from '../../theme/UiPreferencesProvider';
import { resolveTimeOfDayPhase, TIME_OF_DAY_GRADES } from '../../theme/backgrounds';
import { EASE_OUT, SPRING_PANEL, isTopEscapeLayer, registerEscapeLayer } from '../Common/MotionPrimitives';
import PhoneHomeApp from './PhoneHomeApp';
import PhoneRealtyApp from './PhoneRealtyApp';
import PhonePlannerApp from './PhonePlannerApp';
import PhonePhotosApp from './PhonePhotosApp';
import PhoneDmsApp from './PhoneDmsApp';
import PhoneFeedApp from './PhoneFeedApp';
import PhoneShopApp from './PhoneShopApp';
import PhoneBountiesApp from './PhoneBountiesApp';
import PhoneSettingsApp from './PhoneSettingsApp';
import {
  FOCAL_OBJECT_CLASS,
  buildCarouselCandidates,
  isImageGenModeActive,
  isIntimateMediaItem,
  isVideoMediaItem,
  pickNextCarouselWallpaper,
  resolveActivePhoneWallpaper,
} from './phoneWallpapers';

const PhoneModal = ({
  isOpen,
  onClose,
  phoneHook,
  codexHook,
  session,
  user,
  imageGenMode = null,
  initialChatNpc = null,
  onClearInitialChatNpc = null,
  onRefreshInventory,
  onRefreshCodex,
  onRefreshCharacter,
}) => {
  const { t } = useTranslation();
  const {
    clockFormat,
    setClockFormat,
    phonePrefs,
    setPhonePref,
    setSessionPhoneWallpaper,
  } = useUiPreferences();
  const reduced = useReducedMotion();
  const [activeApp, setActiveApp] = useState('home'); // 'home' | 'photos' | 'dms' | 'feed' | 'shop' | 'planner' | 'bounties' | 'realty' | 'settings'
  const [activeCarouselEntry, setActiveCarouselEntry] = useState(null);
  const [messagesSubTab, setMessagesSubTab] = useState('contacts'); // 'contacts' | 'dispatch'
  const [selectedPhoto, setSelectedPhoto] = useState(null);
  const [photoCategory, setPhotoCategory] = useState('all'); // 'all' | 'photo' | 'intimate' | 'video'
  const [photoContactFilter, setPhotoContactFilter] = useState('__all__');
  const [deletingPhoto, setDeletingPhoto] = useState(false);
  const [generatingPhotoId, setGeneratingPhotoId] = useState(null);
  const [photoActionError, setPhotoActionError] = useState(null);
  const [dmInput, setDmInput] = useState('');
  const [selectedIntent, setSelectedIntent] = useState('chat');
  const [dmOutcomeBanner, setDmOutcomeBanner] = useState(null);

  // Feed & PeerPulse state
  const [feedSubTab, setFeedSubTab] = useState('timeline'); // 'timeline' | 'peerpulse'
  const [feedBusy, setFeedBusy] = useState(false);
  const [feedBanner, setFeedBanner] = useState(null);
  const [peerQuery, setPeerQuery] = useState('');
  const [peerProfile, setPeerProfile] = useState(null);
  const [peerBusy, setPeerBusy] = useState(false);
  const [peerFeedback, setPeerFeedback] = useState(null);

  // Online Shop state
  const [shopData, setShopData] = useState(null);
  const [loadingShop, setLoadingShop] = useState(false);
  const [buyingItem, setBuyingItem] = useState(null);
  const [shopFeedback, setShopFeedback] = useState(null);

  // Requests / Bounties state
  const [bountySubTab, setBountySubTab] = useState('available'); // 'available' | 'active'
  const [selectedFactionFilter, setSelectedFactionFilter] = useState('all');
  const [generatingBounties, setGeneratingBounties] = useState(false);
  const [busyBountyId, setBusyBountyId] = useState(null);
  const [bountyActionBanner, setBountyActionBanner] = useState(null);
  const [cancellingCommitmentId, setCancellingCommitmentId] = useState(null);

  // Realty & Safehouses state
  const [realtyData, setRealtyData] = useState(null);
  const [loadingRealty, setLoadingRealty] = useState(false);
  const [realtySubTab, setRealtySubTab] = useState('owned'); // 'owned' | 'market'
  const [realtyBusy, setRealtyBusy] = useState(false);
  const [realtyBanner, setRealtyBanner] = useState(null);
  const [selectedSpareKeyNpc, setSelectedSpareKeyNpc] = useState({});

  const {
    branding, appointments, commitments: phoneCommitments = [], gossipFeed, mediaGallery, contacts,
    dispatchChannels = [], suggestedPeers = [], socialState,
    activeChatNpc, chatMessages, dailyLimits, loadingChat, sendingChat,
    imageGenEnabled = 0, generateMediaPhoto,
    loadChatMessages, sendMessage, closeChat,
    refreshFeed, scourFeed, discoverPeer, sendFriendRequest, refreshPhoneData, cancelCommitment,
  } = phoneHook;

  const effectiveImageGenMode =
    session?.image_gen_enabled ?? imageGenMode ?? imageGenEnabled ?? 0;
  const isImgGenActive = isImageGenModeActive(effectiveImageGenMode);

  const wasOpenRef = useRef(false);
  const lastCarouselKeyRef = useRef(null);
  const prevSessionIdRef = useRef(session?.id ?? null);
  const phoneDialogRef = useRef(null);
  const previousFocusRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const shopSeqRef = useRef(0);
  const shopAbortRef = useRef(null);
  const realtySeqRef = useRef(0);
  const realtyAbortRef = useRef(null);

  const phonePrefsRef = useRef(phonePrefs);
  phonePrefsRef.current = phonePrefs;
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const mediaGalleryRef = useRef(mediaGallery);
  mediaGalleryRef.current = mediaGallery;

  useEffect(() => {
    const nextSid = session?.id ?? null;
    if (prevSessionIdRef.current === nextSid) return;
    prevSessionIdRef.current = nextSid;
    setActiveApp('home');
    setActiveCarouselEntry(null);
    lastCarouselKeyRef.current = null;
    setSelectedPhoto(null);
    setPhotoCategory('all');
    setPhotoContactFilter('__all__');
    setPhotoActionError(null);
    setDmInput('');
    setDmOutcomeBanner(null);
    setFeedBanner(null);
    setPeerQuery('');
    setPeerProfile(null);
    setPeerFeedback(null);
    setShopData(null);
    setShopFeedback(null);
    setBountyActionBanner(null);
    setSelectedFactionFilter('all');
    setRealtyData(sessionRef.current?.realty?.enabled ? sessionRef.current.realty : null);
    setRealtyBanner(null);
    setSelectedSpareKeyNpc({});
  }, [session?.id]);

  const advanceCarousel = useCallback(() => {
    const p = phonePrefsRef.current;
    const candidates = buildCarouselCandidates({
      poolMode: p?.carouselPool || 'all_builtin',
      customIds: p?.carouselCustomIds || [],
      session: sessionRef.current,
      mediaGallery: mediaGalleryRef.current || [],
      includeIntimate: Boolean(p?.includeIntimateInCarousel),
    });
    const nextEntry = pickNextCarouselWallpaper(candidates, lastCarouselKeyRef.current);
    if (nextEntry) {
      lastCarouselKeyRef.current = nextEntry.key;
      setActiveCarouselEntry(nextEntry);
    } else {
      setActiveCarouselEntry(null);
    }
  }, []);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const token = Symbol('phone-modal');
    const unregister = registerEscapeLayer(token);

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const frame = requestAnimationFrame(() => {
      const node = phoneDialogRef.current;
      if (node && !node.contains(document.activeElement)) {
        node.focus({ preventScroll: true });
      }
    });

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        onCloseRef.current?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown, true);

    return () => {
      unregister();
      cancelAnimationFrame(frame);
      window.removeEventListener('keydown', handleKeyDown, true);
      const prev = previousFocusRef.current;
      if (prev && typeof prev.focus === 'function' && prev.isConnected) {
        prev.focus({ preventScroll: true });
      }
    };
  }, [isOpen]);

  const loadChatMessagesRef = useRef(loadChatMessages);
  loadChatMessagesRef.current = loadChatMessages;
  const onClearInitialChatNpcRef = useRef(onClearInitialChatNpc);
  onClearInitialChatNpcRef.current = onClearInitialChatNpc;

  // Open requested DM thread (or home screen on false -> true transition) when modal opens
  useEffect(() => {
    const justOpened = isOpen && !wasOpenRef.current;
    wasOpenRef.current = isOpen;
    if (!isOpen) return;

    if (justOpened && phonePrefsRef.current?.carouselEnabled) {
      advanceCarousel();
    }

    if (initialChatNpc) {
      setSelectedPhoto(null);
      setPhotoActionError(null);
      setActiveApp('dms');
      setMessagesSubTab('contacts');
      setDmOutcomeBanner(null);
      if (loadChatMessagesRef.current) {
        loadChatMessagesRef.current(initialChatNpc);
      }
      if (onClearInitialChatNpcRef.current) {
        onClearInitialChatNpcRef.current();
      }
    } else if (justOpened) {
      setSelectedPhoto(null);
      setPhotoActionError(null);
      setActiveApp('home');
    }
  }, [isOpen, initialChatNpc, advanceCarousel]);

  const availablePhotoCount = useMemo(() => {
    const npcCount = (mediaGallery || []).filter((m) => m?.image_url && !isVideoMediaItem(m)).length;
    const histCount = Array.isArray(session?.history)
      ? session.history.filter((h) => Boolean(h?.scene_image_url)).length
      : 0;
    const topSceneCount = session?.scene_image_url ? 1 : 0;
    return npcCount + histCount + topSceneCount;
  }, [mediaGallery, session?.scene_image_url, session?.history]);

  useEffect(() => {
    if (!phonePrefs?.carouselEnabled) return;
    const candidates = buildCarouselCandidates({
      poolMode: phonePrefs?.carouselPool || 'all_builtin',
      customIds: phonePrefs?.carouselCustomIds || [],
      session: sessionRef.current,
      mediaGallery: mediaGalleryRef.current || [],
      includeIntimate: Boolean(phonePrefs?.includeIntimateInCarousel),
    });
    const stillValid =
      activeCarouselEntry &&
      candidates.some(
        (c) =>
          c.key === activeCarouselEntry.key ||
          (activeCarouselEntry.type === 'npc_photo' &&
            c.type === 'npc_photo' &&
            ((activeCarouselEntry.id != null && String(c.id) === String(activeCarouselEntry.id)) ||
              (activeCarouselEntry.url && c.url === activeCarouselEntry.url))) ||
          (activeCarouselEntry.type === 'scene' &&
            c.type === 'scene' &&
            c.url === activeCarouselEntry.url)
      );
    if (!stillValid) {
      advanceCarousel();
    }
  }, [
    phonePrefs?.carouselEnabled,
    phonePrefs?.carouselPool,
    phonePrefs?.includeIntimateInCarousel,
    phonePrefs?.carouselCustomIds,
    availablePhotoCount,
    activeCarouselEntry,
    advanceCarousel,
  ]);

  const plannerItems = (phoneCommitments && phoneCommitments.length > 0) ? phoneCommitments : (appointments || []);

  const handleOpenChatWithContact = (npcIdOrName) => {
    if (!npcIdOrName) return;
    setDmOutcomeBanner(null);
    setActiveApp('dms');
    if (loadChatMessages) {
      loadChatMessages(npcIdOrName);
    }
  };

  const handleCancelPlannerItem = async (commitmentId) => {
    if (!commitmentId || !cancelCommitment || cancellingCommitmentId) return;
    setCancellingCommitmentId(commitmentId);
    try {
      await cancelCommitment(commitmentId, 'player_cancelled');
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      console.warn('Failed to cancel commitment:', err);
    } finally {
      setCancellingCommitmentId(null);
    }
  };

  const handleDeleteMedia = async (photo) => {
    if (!photo?.id || !user?.user_id || deletingPhoto) return;
    setDeletingPhoto(true);
    setPhotoActionError(null);
    try {
      await apiCall('/api/inventory/drop', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          item_id: photo.id,
        }),
      });
      const sidKey = session?.id != null ? String(session.id) : null;
      const activeOverride = sidKey ? phonePrefs?.sessionWallpapers?.[sidKey] : null;
      if (
        sidKey &&
        activeOverride?.type === 'npc_photo' &&
        (String(activeOverride.id) === String(photo.id) ||
          (photo.image_url && activeOverride.url === photo.image_url))
      ) {
        setSessionPhoneWallpaper(sidKey, null);
      }
      if (
        activeCarouselEntry?.type === 'npc_photo' &&
        (String(activeCarouselEntry.id) === String(photo.id) ||
          (photo.image_url && activeCarouselEntry.url === photo.image_url))
      ) {
        if (phonePrefs?.carouselEnabled) {
          advanceCarousel();
        } else {
          setActiveCarouselEntry(null);
        }
      }
      setSelectedPhoto(null);
      if (refreshPhoneData) await refreshPhoneData();
      if (onRefreshInventory) onRefreshInventory();
    } catch (err) {
      setPhotoActionError(err?.message || t('phone.vault.delete_failed', 'Could not delete media.'));
    } finally {
      setDeletingPhoto(false);
    }
  };

  const handleGenerateMediaPhoto = async (itemId, { forceRegenerate = false } = {}) => {
    if (!itemId || !generateMediaPhoto) return;
    setGeneratingPhotoId(itemId);
    setPhotoActionError(null);
    try {
      await generateMediaPhoto(itemId, { forceRegenerate });
    } catch (err) {
      const errMsg = err?.message || t('phone.vault.generate_failed', 'Could not generate photo.');
      setPhotoActionError(errMsg);
      if (activeApp === 'dms' && !selectedPhoto) {
        setDmOutcomeBanner({ error: errMsg });
      }
    } finally {
      setGeneratingPhotoId(null);
    }
  };

  const handleRefreshFeed = async () => {
    if (!refreshFeed || feedBusy) return;
    setFeedBusy(true);
    setFeedBanner(null);
    try {
      await refreshFeed();
    } catch (err) {
      setFeedBanner({ type: 'error', text: err.message || 'Could not refresh timeline.' });
    } finally {
      setFeedBusy(false);
    }
  };

  const handleScourRumor = async () => {
    if (!scourFeed || feedBusy) return;
    setFeedBusy(true);
    setFeedBanner(null);
    try {
      const res = await scourFeed();
      if (res?.clue) {
        setFeedBanner({
          type: 'ok',
          title: `⚡ Verified Lead (${res.check?.stat || 'PER'} ${res.check?.tier_label || 'Success'})`,
          text: `${res.clue} (Source: ${res.source || 'NetWire'}) — Logged to Caseboard!`,
        });
        if (onRefreshCodex) onRefreshCodex();
      } else {
        setFeedBanner({
          type: 'warn',
          title: res?.check ? `🔍 ${res.check.stat} Check: ${res.check.tier_label}` : 'No New Leads',
          text: res?.message || 'Only campus noise and memes surfaced this time.',
        });
      }
    } catch (err) {
      setFeedBanner({ type: 'error', text: err.message || 'Failed to scour rumors.' });
    } finally {
      setFeedBusy(false);
    }
  };

  const handleDiscoverPeer = async (queryText = '') => {
    if (!discoverPeer || peerBusy) return;
    setPeerBusy(true);
    setPeerFeedback(null);
    try {
      const res = await discoverPeer(queryText);
      if (res?.profile) {
        setPeerProfile(res.profile);
      }
    } catch (err) {
      setPeerFeedback({ type: 'error', text: err.message || 'No matching profile found.' });
    } finally {
      setPeerBusy(false);
    }
  };

  const handleSendFriendReq = async (targetProfile = null) => {
    const profileToUse = targetProfile || peerProfile;
    if (!sendFriendRequest || !profileToUse || peerBusy) return;
    setPeerBusy(true);
    setPeerFeedback(null);
    try {
      const res = await sendFriendRequest(profileToUse);
      if (res?.profile) {
        if (peerProfile && (peerProfile.name === profileToUse.name || peerProfile.handle === profileToUse.handle)) {
          setPeerProfile(res.profile);
        }
      }
      setPeerFeedback({
        type: res?.accepted ? 'ok' : 'warn',
        text: res?.message || (res?.accepted ? 'Friend request accepted!' : 'Request pending.'),
      });
      if (res?.accepted && onRefreshCodex) {
        onRefreshCodex();
      }
    } catch (err) {
      setPeerFeedback({ type: 'error', text: err.message || 'Could not send friend request.' });
    } finally {
      setPeerBusy(false);
    }
  };

  useEffect(() => {
    if (!isOpen || activeApp !== 'shop' || !session?.id || !user?.user_id) {
      if (shopAbortRef.current) {
        try {
          shopAbortRef.current.abort();
        } catch {}
        shopAbortRef.current = null;
      }
      return;
    }
    if (shopAbortRef.current) {
      try {
        shopAbortRef.current.abort();
      } catch {}
    }
    const seq = ++shopSeqRef.current;
    const controller = new AbortController();
    shopAbortRef.current = controller;
    setLoadingShop(true);
    setShopFeedback(null);
    apiCall(`/api/merchant/${session.id}?user_id=${user.user_id}&is_phone_shop=true`, {
      signal: controller.signal,
    })
      .then((data) => {
        if (seq === shopSeqRef.current) {
          setShopData(data);
        }
      })
      .catch((err) => {
        if (err?.isUserAbort || err?.name === 'AbortError' || seq !== shopSeqRef.current) return;
        setShopFeedback({
          type: 'error',
          text: err?.message || t('phone.shop_load_failed', 'Failed to load shop catalogue.'),
        });
      })
      .finally(() => {
        if (seq === shopSeqRef.current) {
          setLoadingShop(false);
          if (shopAbortRef.current === controller) {
            shopAbortRef.current = null;
          }
        }
      });
    return () => {
      try {
        controller.abort();
      } catch {}
    };
  }, [isOpen, activeApp, session?.id, user?.user_id, t]);

  const handleBuyDeliveryItem = async (item) => {
    if (!session?.id || !user?.user_id || buyingItem) return;
    setBuyingItem(item.name);
    setShopFeedback(null);
    try {
      const data = await apiCall('/api/merchant/buy', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: session.id,
          item_name: item.name,
          is_phone_shop: true,
        }),
      });
      setShopFeedback({ type: 'ok', text: data.message || `Ordered ${item.name}!` });
      setShopData((prev) =>
        prev
          ? {
              ...prev,
              gold: data.gold ?? prev.gold,
              inventory: Array.isArray(data.stock) ? data.stock : prev.inventory,
              stock: Array.isArray(data.stock) ? data.stock : prev.stock,
            }
          : prev
      );
      if (onRefreshInventory) onRefreshInventory();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setShopFeedback({ type: 'error', text: err.message || 'Order failed.' });
    } finally {
      setBuyingItem(null);
    }
  };

  const handleRefreshBounties = async (factionId = null) => {
    if (generatingBounties || !codexHook?.generateBounties) return;
    setGeneratingBounties(true);
    setBountyActionBanner(null);
    try {
      const targetFaction =
        factionId !== undefined ? factionId : selectedFactionFilter !== 'all' ? selectedFactionFilter : null;
      await codexHook.generateBounties(true, targetFaction);
      setBountyActionBanner({ type: 'ok', text: 'Requests updated from bulletin board!' });
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Failed to refresh requests.' });
    } finally {
      setGeneratingBounties(false);
    }
  };

  const handleAcceptBounty = async (questId, questTitle) => {
    if (!codexHook?.bountyAction || busyBountyId) return;
    setBusyBountyId(questId);
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'accept');
      setBountyActionBanner({
        type: 'ok',
        text: `✅ Accepted "${questTitle}" — Moved to Active Tasks!`,
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not accept request.' });
    } finally {
      setBusyBountyId(null);
    }
  };

  const handleAbandonBounty = async (questId, questTitle) => {
    if (!codexHook?.bountyAction || busyBountyId) return;
    setBusyBountyId(questId);
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'abandon');
      setBountyActionBanner({
        type: 'warn',
        text: `Dropped task "${questTitle}".`,
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not abandon request.' });
    } finally {
      setBusyBountyId(null);
    }
  };

  let displayTime = formatClockTime(581, clockFormat);
  if (session && session.current_minute !== undefined) {
    displayTime = formatClockTime(session.current_minute, clockFormat);
  }

  // Unique contact names in media gallery
  const galleryContacts = Array.from(
    new Set((mediaGallery || []).map((m) => m.contact_name).filter(Boolean))
  ).sort();

  const filteredGallery = (mediaGallery || []).filter((m) => {
    const isVideo = isVideoMediaItem(m);
    const isIntimate = isIntimateMediaItem(m);
    if (photoCategory === 'video' && !isVideo) return false;
    if (photoCategory === 'intimate' && !isIntimate) return false;
    if (photoCategory === 'photo' && (isVideo || isIntimate)) return false;
    if (photoContactFilter !== '__all__' && m.contact_name !== photoContactFilter) return false;
    return true;
  });

  // Build strictly unlocked personal DM contacts directory
  const dmDirectory = [];
  const seenIds = new Set();
  (contacts || []).forEach((c) => {
    if (c.is_dispatch_channel) return;
    const id = String(c.npc_id ?? c.name ?? '');
    if (id && !seenIds.has(id.toLowerCase())) {
      seenIds.add(id.toLowerCase());
      const scoreVal = c.relationship_score ?? 0;
      dmDirectory.push({
        npc_id: c.npc_id || c.name,
        name: c.name || c.npc_id,
        role: c.basic_info?.role || c.basic_info?.occupation || 'Contact',
        score: scoreVal,
        is_blocked_contact: Boolean(c.is_blocked_contact || scoreVal <= -50),
        anomalous_npc_tag: c.anomalous_npc_tag || c.basic_info?.anomalous_npc_tag || null,
        deceased: Boolean(c.deceased || c.basic_info?.deceased),
      });
    }
  });

  // Build read-only automated Alerts / Dispatch directory
  const dispatchDirectory = [];
  const seenDispatchIds = new Set();
  [...(dispatchChannels || []), ...(contacts || []).filter((c) => c.is_dispatch_channel)].forEach((ch) => {
    const id = String(ch.npc_id ?? ch.name ?? '');
    if (id && !seenDispatchIds.has(id.toLowerCase())) {
      seenDispatchIds.add(id.toLowerCase());
      dispatchDirectory.push({
        npc_id: ch.npc_id || ch.name,
        name: ch.name || ch.npc_id,
        role: ch.role || ch.basic_info?.role || ch.basic_info?.occupation || 'Automated Broadcast Channel',
        is_dispatch_channel: true,
      });
    }
  });

  const showDispatchTab =
    dispatchDirectory.length > 0 || String(session?.scenario || '').toLowerCase().includes('anomalous');
  const activeChatKeyLow = String(activeChatNpc ?? '').toLowerCase();
  const activeDispatchEntry = dispatchDirectory.find(
    (d) => String(d.npc_id).toLowerCase() === activeChatKeyLow || String(d.name).toLowerCase() === activeChatKeyLow
  );
  const activeContactEntry = dmDirectory.find(
    (c) => String(c.npc_id).toLowerCase() === activeChatKeyLow || String(c.name).toLowerCase() === activeChatKeyLow
  );
  const isDispatchThread = Boolean(activeDispatchEntry);
  const isBlockedContact =
    !isDispatchThread &&
    Boolean(activeContactEntry?.is_blocked_contact || (activeContactEntry?.score ?? 0) <= -50);
  const activeDisplayTitle = activeDispatchEntry?.name || activeContactEntry?.name || activeChatNpc;

  const allAvailableBounties = codexHook?.availableBounties || [];
  const factionsList = codexHook?.factions || [];

  const availableBounties = allAvailableBounties.filter((b) => {
    if (selectedFactionFilter === 'all') return true;
    const bFaction = String(b.faction_id || b.faction_name || b.faction || '').toLowerCase();
    const bSource = String(b.board_source || '').toLowerCase();
    const targetF = factionsList.find(
      (f) => f.faction_id === selectedFactionFilter || f.name === selectedFactionFilter
    );
    const targetId = String(targetF?.faction_id || selectedFactionFilter || '').toLowerCase();
    const targetName = String(targetF?.name || '').toLowerCase();
    const targetArch = String(targetF?.archetype_key || '').toLowerCase();
    return (
      (targetArch && bSource === targetArch) ||
      bFaction === targetId ||
      (targetName && bFaction.includes(targetName)) ||
      (b.title && targetName && b.title.toLowerCase().includes(targetName)) ||
      (b.objective && targetName && b.objective.toLowerCase().includes(targetName))
    );
  });

  const activeBounties = (codexHook?.quests || []).filter(
    (q) =>
      q.status === 'Active' &&
      ((q.quest_id && (q.quest_id.startsWith('BNT-') || q.quest_id.startsWith('FBNT-'))) ||
        (q.quest_type &&
          (q.quest_type.includes('Bounty') ||
            q.quest_type.includes('Request') ||
            q.quest_type.includes('Commission') ||
            q.quest_type.includes('Gig'))))
  );

  const autoBountiesAttemptedRef = useRef(false);
  const codexGenerateBountiesRef = useRef(codexHook?.generateBounties);
  codexGenerateBountiesRef.current = codexHook?.generateBounties;
  const autoFeedAttemptedRef = useRef(false);
  const handleRefreshFeedRef = useRef(null);
  const hasRefreshFeed = Boolean(refreshFeed);

  // Auto-generate bounties when opening requests app if none exist
  useEffect(() => {
    if (!isOpen || activeApp !== 'bounties') {
      autoBountiesAttemptedRef.current = false;
      return;
    }
    if (
      allAvailableBounties.length === 0 &&
      !generatingBounties &&
      !autoBountiesAttemptedRef.current &&
      codexGenerateBountiesRef.current
    ) {
      autoBountiesAttemptedRef.current = true;
      setGeneratingBounties(true);
      Promise.resolve(codexGenerateBountiesRef.current())
        .catch(() => {})
        .finally(() => setGeneratingBounties(false));
    }
  }, [isOpen, activeApp, allAvailableBounties.length, generatingBounties]);

  // Auto-refresh feed when opening feed app if empty
  handleRefreshFeedRef.current = handleRefreshFeed;
  useEffect(() => {
    if (!isOpen || activeApp !== 'feed') {
      autoFeedAttemptedRef.current = false;
      return;
    }
    if ((!gossipFeed || gossipFeed.length === 0) && !feedBusy && hasRefreshFeed && !autoFeedAttemptedRef.current) {
      autoFeedAttemptedRef.current = true;
      handleRefreshFeedRef.current?.();
    }
  }, [isOpen, activeApp, gossipFeed, feedBusy, hasRefreshFeed]);

  const apps = [
    {
      id: 'photos',
      name: branding.gallery_app_name || t('phone.apps.photos', 'Photo Vault'),
      shortName: t('phone.apps.photos_short', 'Photos'),
      subtitle: t('phone.apps.photos_sub', 'Vault & Media'),
      icon: Camera,
      gradient: 'from-pink-500 via-rose-500 to-pink-600',
      badge: (mediaGallery || []).length > 0 ? mediaGallery.length : null,
      badgeColor: 'bg-pink-500',
    },
    {
      id: 'dms',
      name: branding.dm_app_name || t('phone.apps.dms', 'Messages'),
      shortName: t('phone.apps.dms_short', 'Messages'),
      subtitle: t('phone.apps.dms_sub', 'Chats & Meetups'),
      icon: MessageSquare,
      gradient: 'from-emerald-500 via-teal-500 to-cyan-600',
      badge: (appointments || []).length > 0 ? appointments.length : null,
      badgeColor: 'bg-emerald-500',
    },
    {
      id: 'feed',
      name: branding.feed_app_name || t('phone.apps.feed', 'PeerPulse'),
      shortName:
        branding.feed_app_name && branding.feed_app_name.length <= 10
          ? branding.feed_app_name
          : t('phone.apps.feed_short', 'Social'),
      subtitle: t('phone.apps.feed_sub', 'Radar & Social'),
      icon: Rss,
      gradient: 'from-violet-500 via-purple-600 to-indigo-600',
      badge: (gossipFeed || []).length > 0 ? gossipFeed.length : null,
      badgeColor: 'bg-purple-500',
    },
    {
      id: 'shop',
      name: branding.shop_app_name || t('phone.apps.shop', 'SchoolMart Delivery'),
      subtitle: branding.shop_subtitle || t('phone.apps.shop_sub', 'Online Courier'),
      icon: ShoppingBag,
      gradient: 'from-amber-500 via-orange-500 to-amber-600',
      badge: null,
      badgeColor: 'bg-amber-500',
    },
    {
      id: 'planner',
      name: branding.planner_app_name || t('phone.apps.planner', 'Planner & Agenda'),
      subtitle: t('phone.apps.planner_sub', 'Schedule & Rendezvous'),
      icon: Calendar,
      gradient: 'from-blue-500 via-indigo-500 to-sky-600',
      badge: plannerItems.length > 0 ? plannerItems.length : null,
      badgeColor: 'bg-blue-500',
    },
    {
      id: 'bounties',
      name: branding.bounty_app_name || branding.bounties_app_name || t('phone.apps.bounties', 'Campus Requests'),
      subtitle: branding.bounty_subtitle || t('phone.apps.bounties_sub', 'Student Bulletin'),
      icon: ShieldAlert,
      gradient: 'from-rose-500 via-red-600 to-rose-700',
      badge: availableBounties.length > 0 ? availableBounties.length : null,
      badgeColor: 'bg-rose-500',
    },
    {
      id: 'settings',
      name: t('phone.apps.settings', 'Settings'),
      shortName: t('phone.apps.settings', 'Settings'),
      subtitle: t('phone.apps.settings_sub', 'Wallpaper & Theme'),
      icon: Settings,
      gradient: 'from-slate-500 via-zinc-600 to-neutral-700',
      badge: null,
      badgeColor: 'bg-sky-500',
    },
  ];

  const scenLowForRealty = String(session?.scenario || '').toLowerCase();
  const isAnomalousRealtyScenario =
    Boolean(session?.realty?.enabled) ||
    Boolean(realtyData?.enabled) ||
    scenLowForRealty.includes('anomalous_incursion') ||
    scenLowForRealty.includes('anomalous_high_school') ||
    scenLowForRealty.includes('urban_anomalies');

  const fetchRealty = useCallback(async () => {
    if (!session?.id) return;
    if (realtyAbortRef.current) {
      try {
        realtyAbortRef.current.abort();
      } catch {}
    }
    const seq = ++realtySeqRef.current;
    const controller = new AbortController();
    realtyAbortRef.current = controller;
    setLoadingRealty(true);
    setRealtyBanner(null);
    try {
      const uidQuery = user?.user_id ? `?user_id=${user.user_id}` : '';
      const data = await apiCall(`/api/realty/${session.id}${uidQuery}`, {
        signal: controller.signal,
      });
      if (seq === realtySeqRef.current) {
        setRealtyData(data);
      }
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || seq !== realtySeqRef.current) return;
      setRealtyBanner({ type: 'error', text: err.message || 'Failed to load Realty listings.' });
    } finally {
      if (seq === realtySeqRef.current) {
        setLoadingRealty(false);
        if (realtyAbortRef.current === controller) {
          realtyAbortRef.current = null;
        }
      }
    }
  }, [session?.id, user?.user_id]);

  useEffect(() => {
    if (isOpen && activeApp === 'realty' && session?.id) {
      fetchRealty();
      return () => {
        if (realtyAbortRef.current) {
          try {
            realtyAbortRef.current.abort();
          } catch {}
        }
      };
    }
    if (realtyAbortRef.current) {
      try {
        realtyAbortRef.current.abort();
      } catch {}
      realtyAbortRef.current = null;
    }
    return undefined;
  }, [isOpen, activeApp, session?.id, fetchRealty]);

  useEffect(() => {
    if (session?.realty && session.realty.enabled) {
      setRealtyData(session.realty);
    }
  }, [session?.realty]);

  const handleBuyProperty = async (propertyId) => {
    if (!session?.id || realtyBusy) return;
    setRealtyBusy(true);
    setRealtyBanner(null);
    try {
      const res = await apiCall(`/api/realty/${session.id}/purchase`, {
        method: 'POST',
        body: JSON.stringify({ user_id: user?.user_id, property_id: propertyId }),
      });
      setRealtyData(res);
      setRealtyBanner({ type: 'success', text: res.message || t('realty.purchased_ok', 'Deed purchased!') });
      if (onRefreshInventory) onRefreshInventory();
      if (onRefreshCharacter) onRefreshCharacter();
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setRealtyBanner({ type: 'error', text: err.message || t('realty.purchase_failed', 'Purchase failed.') });
    } finally {
      setRealtyBusy(false);
    }
  };

  const handleSetPrimaryProperty = async (propertyId) => {
    if (!session?.id || realtyBusy) return;
    setRealtyBusy(true);
    setRealtyBanner(null);
    try {
      const res = await apiCall(`/api/realty/${session.id}/primary`, {
        method: 'POST',
        body: JSON.stringify({ user_id: user?.user_id, property_id: propertyId }),
      });
      setRealtyData(res);
      setRealtyBanner({ type: 'success', text: res.message || t('realty.primary_updated', 'Primary Home updated.') });
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setRealtyBanner({ type: 'error', text: err.message || 'Failed to update Primary Home.' });
    } finally {
      setRealtyBusy(false);
    }
  };

  const handleManageSpareKey = async (propertyId, npcId, revoke = false) => {
    if (!session?.id || !npcId || realtyBusy) return;
    setRealtyBusy(true);
    setRealtyBanner(null);
    try {
      const res = await apiCall(`/api/realty/${session.id}/spare-key`, {
        method: 'POST',
        body: JSON.stringify({ user_id: user?.user_id, property_id: propertyId, npc_id: npcId, revoke }),
      });
      setRealtyData(res);
      setRealtyBanner({
        type: 'success',
        text:
          res.message ||
          (revoke ? t('realty.key_revoked', 'Spare key revoked.') : t('realty.key_granted', 'Spare key granted!')),
      });
    } catch (err) {
      setRealtyBanner({ type: 'error', text: err.message || 'Failed to update spare key.' });
    } finally {
      setRealtyBusy(false);
    }
  };

  if (isAnomalousRealtyScenario) {
    apps.push({
      id: 'realty',
      name: t('realty.app_name', 'Realty & Deeds'),
      subtitle: t('realty.app_sub', 'Safehouses & Keys'),
      icon: Home,
      gradient: 'from-emerald-600 via-teal-600 to-cyan-700',
      badge: realtyData?.owned_properties?.length ? realtyData.owned_properties.length : null,
      badgeColor: 'bg-emerald-500',
    });
  }

  const processDmOutcome = (res) => {
    const replyObj = res?.reply && typeof res.reply === 'object' ? res.reply : res;
    if (
      replyObj &&
      (replyObj.check ||
        replyObj.check_result ||
        replyObj.affinity_delta !== undefined ||
        replyObj.rendezvous_location ||
        replyObj.media_dropped ||
        replyObj.daily_digestion_capped ||
        (Array.isArray(replyObj.discovered_facts) && replyObj.discovered_facts.length > 0))
    ) {
      setDmOutcomeBanner({
        check: replyObj.check || replyObj.check_result,
        affinity_delta: replyObj.affinity_delta,
        rendezvous_location: replyObj.rendezvous_location,
        media_dropped: replyObj.media_dropped,
        daily_digestion_capped: Boolean(replyObj.daily_digestion_capped),
        discovered_facts: Array.isArray(replyObj.discovered_facts) ? replyObj.discovered_facts : [],
      });
      if (Array.isArray(replyObj.discovered_facts) && replyObj.discovered_facts.length > 0 && onRefreshCodex) {
        onRefreshCodex();
      }
    }
  };

  const handleSendDm = async (e) => {
    e.preventDefault();
    if (!dmInput.trim() || !activeChatNpc || sendingChat) return;
    const text = dmInput.trim();
    setDmInput('');
    setDmOutcomeBanner(null);
    try {
      const res = await sendMessage(activeChatNpc, text, selectedIntent === 'auto' ? null : selectedIntent);
      processDmOutcome(res);
      if (onRefreshInventory) onRefreshInventory();
      if (onRefreshCodex) onRefreshCodex();
    } catch {
      setDmInput(text);
    }
  };

  const handleInstantIntentSend = async (intentId) => {
    if (!activeChatNpc || sendingChat) return;
    setSelectedIntent(intentId);
    setDmOutcomeBanner(null);
    try {
      const res = await sendMessage(activeChatNpc, '__auto__', intentId);
      processDmOutcome(res);
      if (onRefreshInventory) onRefreshInventory();
      if (onRefreshCodex) onRefreshCodex();
    } catch (err) {
      setDmOutcomeBanner({
        error: err?.message || t('phone.dms.send_failed', 'Failed to send message.'),
      });
    }
  };

  const scenarioKey = session?.scenario || 'fantasy';
  const uiStyle = phonePrefs?.uiStyle === 'glass' ? 'glass' : 'classic';
  const isGlass = uiStyle === 'glass';
  const focalCls = FOCAL_OBJECT_CLASS[phonePrefs?.wallpaperFocal || 'center'] || 'object-center';
  const dimAlpha = Math.max(0, Math.min(0.7, (phonePrefs?.wallpaperDim ?? 25) / 100));
  const timePhase = resolveTimeOfDayPhase(displayTime, session?.current_minute);
  const timeGrade = TIME_OF_DAY_GRADES[timePhase] || 'none';

  const activeWallpaper = useMemo(
    () =>
      resolveActivePhoneWallpaper({
        phonePrefs,
        session,
        mediaGallery,
        activeCarouselEntry,
      }),
    [phonePrefs, session, mediaGallery, activeCarouselEntry]
  );

  const liveSelectedPhoto = useMemo(() => {
    if (!selectedPhoto) return null;
    if (selectedPhoto.id) {
      const fresh = (mediaGallery || []).find(
        (m) => m?.id != null && String(m.id) === String(selectedPhoto.id)
      );
      if (fresh) return fresh;
    }
    return selectedPhoto;
  }, [selectedPhoto, mediaGallery]);

  const showWallpaperBackdrop = isGlass || activeApp === 'home';
  const blurWallpaperNow = isGlass && activeApp !== 'home' && phonePrefs?.blurInApps !== false;

  const isSelectedPhotoActiveWallpaper = Boolean(
    liveSelectedPhoto?.image_url &&
      session?.id != null &&
      phonePrefs?.sessionWallpapers?.[String(session.id)]?.type === 'npc_photo' &&
      (String(phonePrefs.sessionWallpapers[String(session.id)].id) === String(liveSelectedPhoto.id) ||
        phonePrefs.sessionWallpapers[String(session.id)].url === liveSelectedPhoto.image_url)
  );

  const handleSetPhotoAsWallpaper = (photo) => {
    if (!session?.id || !photo?.image_url) return;
    setSessionPhoneWallpaper(session.id, {
      type: 'npc_photo',
      id: photo.id ?? null,
      url: photo.image_url,
      label: photo.contact_name || photo.name || 'NPC Photo',
    });
    if (phonePrefs?.carouselEnabled) {
      setPhonePref('carouselEnabled', false);
    }
  };

  const modalContent = (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          data-motion="true"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduced ? 0.12 : 0.2, ease: EASE_OUT }}
          onClick={(e) => {
            if (e.target === e.currentTarget) onClose();
          }}
          className="fixed inset-0 z-50 flex flex-col md:items-center md:justify-center md:p-4 hk-phone-backdrop md:backdrop-blur-md text-gray-100 select-none overflow-hidden"
        >
          {/* Phone Shell: Full-screen on mobile, centered phone shell on desktop */}
          <motion.div
            ref={phoneDialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={branding?.device_name || t('nav.smartphone', 'Smartphone')}
            data-phone-style={uiStyle}
            tabIndex={-1}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 18, scale: 0.96 }}
            animate={reduced ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, y: 14, scale: 0.96 }}
            transition={reduced ? { duration: 0.14 } : SPRING_PANEL}
            className="hk-phone-shell w-full h-full md:max-w-[420px] md:h-[840px] md:max-h-[calc(var(--app-height,100dvh)-1.5rem)] md:rounded-[44px] md:border-[6px] md:border-neutral-800 md:shadow-[0_0_50px_rgba(0,0,0,0.85)] md:ring-1 md:ring-neutral-700/50 flex flex-col bg-neutral-950 overflow-hidden relative pb-[max(0.6rem,env(safe-area-inset-bottom))] md:pb-0 focus:outline-none"
          >
            {/* Full-Bleed Wallpaper Layer */}
            {showWallpaperBackdrop && (
              <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
                <div
                  className={`w-full h-full transition-all duration-300 ${
                    blurWallpaperNow ? 'blur-[14px] scale-[1.06]' : 'scale-100'
                  }`}
                >
                  {activeWallpaper?.url ? (
                    <img
                      key={activeWallpaper.url}
                      src={activeWallpaper.url}
                      alt=""
                      className={`w-full h-full object-cover ${focalCls}`}
                    />
                  ) : (
                    <div className="w-full h-full hk-phone-wp-iphone" />
                  )}
                </div>

                {phonePrefs?.dynamicTimeTint && timeGrade !== 'none' && (
                  <div
                    className="absolute inset-0 pointer-events-none"
                    style={{ backgroundImage: timeGrade }}
                  />
                )}
                <div
                  className="absolute inset-0 pointer-events-none transition-opacity duration-200"
                  style={{ backgroundColor: `rgba(0, 0, 0, ${dimAlpha})` }}
                />
              </div>
            )}

            {/* Dynamic Island / Speaker Notch & Status Bar */}
            <div
              className={`hidden md:flex relative px-6 pt-3 pb-2 justify-between items-center text-xs font-semibold z-20 shrink-0 ${
                isGlass
                  ? 'hk-phone-chrome border-b text-gray-100'
                  : activeApp === 'home'
                    ? 'bg-transparent hk-phone-home-text'
                    : 'text-gray-200 bg-neutral-950/90'
              }`}
            >
              <span className="font-mono tabular-nums text-[11px] tracking-tight select-none">{displayTime}</span>

              <div className="absolute left-1/2 -translate-x-1/2 top-1/2 -translate-y-1/2 w-24 h-4 bg-black rounded-full flex items-center justify-center gap-1.5 border border-neutral-800/80 shadow-inner pointer-events-none">
                <span className="w-2 h-2 rounded-full bg-neutral-800" />
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-950/80" />
              </div>

              <div className="flex items-center gap-1.5 select-none">
                <Wifi size={12} />
                <span className="text-[10px] font-mono">{t('phone.status_bar.network', '5G')}</span>
                <div
                  className="flex items-center gap-[1px]"
                  title={t('phone.status_bar.battery_title', 'Battery: 88%', { percent: 88 })}
                >
                  <div className="w-[18px] h-[9.5px] rounded-[3px] border border-emerald-400/90 p-[1px] flex items-center bg-black/40">
                    <div className="h-full w-[88%] bg-emerald-400 rounded-[1px]" />
                  </div>
                  <div className="w-[1.5px] h-[4px] bg-emerald-400/90 rounded-r-[1px]" />
                </div>
              </div>
            </div>

            {/* In-App Header */}
            {activeApp !== 'home' && (
              <div
                className={`relative z-10 px-4 py-2 flex items-center justify-between border-b shrink-0 select-none ${
                  isGlass
                    ? 'hk-phone-chrome'
                    : 'border-neutral-900 bg-neutral-950/95'
                }`}
              >
                <button
                  type="button"
                  onClick={() => {
                    setActiveApp('home');
                    setSelectedPhoto(null);
                    if (closeChat) closeChat();
                  }}
                  className="hk-phone-header-accent flex items-center gap-1 text-xs font-semibold text-pink-400 hover:text-pink-300 transition-colors cursor-pointer"
                >
                  <ChevronLeft size={16} />
                  <span>{t('phone.nav.back_to_apps', 'Back to Apps')}</span>
                </button>

                <button
                  type="button"
                  onClick={onClose}
                  className="p-1.5 rounded-full text-gray-400 hover:text-white hover:bg-neutral-800 transition-colors cursor-pointer"
                  title={t('phone.nav.close', 'Close Phone')}
                >
                  <X size={18} />
                </button>
              </div>
            )}

            {/* Screen Canvas */}
            <div
              data-phone-app={activeApp}
              className={`hk-phone-canvas flex-1 overflow-y-auto custom-scrollbar px-3.5 py-2.5 relative z-10 flex flex-col min-h-0 ${
                !isGlass && activeApp !== 'home' ? 'bg-gradient-to-b from-neutral-900/40 to-black' : ''
              }`}
            >
              {activeApp === 'home' && (
                <PhoneHomeApp
                  displayTime={displayTime}
                  session={session}
                  appointments={appointments}
                  availableBounties={availableBounties}
                  mediaGallery={mediaGallery}
                  apps={apps}
                  onSelectApp={(appId) => {
                    setActiveApp(appId);
                    setSelectedPhoto(null);
                  }}
                  clockStyle={phonePrefs?.clockStyle || 'modern'}
                  uiStyle={uiStyle}
                  t={t}
                />
              )}

              {activeApp === 'settings' && (
                <PhoneSettingsApp
                  displayTime={displayTime}
                  session={session}
                  mediaGallery={mediaGallery}
                  phonePrefs={phonePrefs}
                  setPhonePref={setPhonePref}
                  setSessionPhoneWallpaper={setSessionPhoneWallpaper}
                  clockFormat={clockFormat}
                  setClockFormat={setClockFormat}
                  activeWallpaper={activeWallpaper}
                  onShuffleCarousel={advanceCarousel}
                  t={t}
                />
              )}

              {activeApp === 'realty' && (
                <PhoneRealtyApp
                  realtyData={realtyData}
                  loadingRealty={loadingRealty}
                  realtyBusy={realtyBusy}
                  realtyBanner={realtyBanner}
                  onClearBanner={() => setRealtyBanner(null)}
                  realtySubTab={realtySubTab}
                  onChangeSubTab={setRealtySubTab}
                  selectedSpareKeyNpc={selectedSpareKeyNpc}
                  onSelectSpareKeyNpc={(propId, npcId) =>
                    setSelectedSpareKeyNpc((prev) => ({ ...prev, [propId]: npcId }))
                  }
                  onRefreshRealty={fetchRealty}
                  onSetPrimaryProperty={handleSetPrimaryProperty}
                  onManageSpareKey={handleManageSpareKey}
                  onBuyProperty={handleBuyProperty}
                  scenario={scenarioKey}
                  t={t}
                />
              )}

              {activeApp === 'planner' && (
                <PhonePlannerApp
                  branding={branding}
                  session={session}
                  plannerItems={plannerItems}
                  cancellingCommitmentId={cancellingCommitmentId}
                  onCancelPlannerItem={handleCancelPlannerItem}
                  onOpenMessages={() => setActiveApp('dms')}
                  onOpenChatWithContact={handleOpenChatWithContact}
                  clockFormat={clockFormat}
                  t={t}
                />
              )}

              {activeApp === 'photos' && (
                <PhonePhotosApp
                  branding={branding}
                  mediaGallery={mediaGallery}
                  filteredGallery={filteredGallery}
                  galleryContacts={galleryContacts}
                  photoCategory={photoCategory}
                  onChangePhotoCategory={setPhotoCategory}
                  photoContactFilter={photoContactFilter}
                  onChangePhotoContactFilter={setPhotoContactFilter}
                  onSelectPhoto={(photo) => {
                    setPhotoActionError(null);
                    setSelectedPhoto(photo);
                  }}
                  clockFormat={clockFormat}
                  t={t}
                />
              )}

              {activeApp === 'dms' && (
                <PhoneDmsApp
                  branding={branding}
                  activeChatNpc={activeChatNpc}
                  activeDisplayTitle={activeDisplayTitle}
                  isDispatchThread={isDispatchThread}
                  isBlockedContact={isBlockedContact}
                  dmOutcomeBanner={dmOutcomeBanner}
                  onClearOutcomeBanner={() => setDmOutcomeBanner(null)}
                  loadingChat={loadingChat}
                  chatMessages={chatMessages}
                  sendingChat={sendingChat}
                  dailyLimits={dailyLimits}
                  activeContactEntry={activeContactEntry}
                  selectedIntent={selectedIntent}
                  onInstantIntentSend={handleInstantIntentSend}
                  dmInput={dmInput}
                  onChangeDmInput={setDmInput}
                  onSendDm={handleSendDm}
                  onCloseChat={closeChat}
                  appointments={appointments}
                  showDispatchTab={showDispatchTab}
                  messagesSubTab={messagesSubTab}
                  onChangeMessagesSubTab={setMessagesSubTab}
                  dmDirectory={dmDirectory}
                  dispatchDirectory={dispatchDirectory}
                  onLoadChatMessages={loadChatMessages}
                  mediaGallery={mediaGallery}
                  imageGenEnabled={effectiveImageGenMode}
                  onSelectPhoto={(photo) => {
                    setPhotoActionError(null);
                    setSelectedPhoto(photo);
                  }}
                  onGenerateMediaPhoto={(itemId) => handleGenerateMediaPhoto(itemId)}
                  clockFormat={clockFormat}
                  t={t}
                />
              )}

              {activeApp === 'feed' && (
                <PhoneFeedApp
                  branding={branding}
                  socialState={socialState}
                  feedSubTab={feedSubTab}
                  onChangeFeedSubTab={setFeedSubTab}
                  feedBusy={feedBusy}
                  feedBanner={feedBanner}
                  onClearFeedBanner={() => setFeedBanner(null)}
                  onScourRumor={handleScourRumor}
                  onRefreshFeed={handleRefreshFeed}
                  gossipFeed={gossipFeed}
                  peerQuery={peerQuery}
                  onChangePeerQuery={setPeerQuery}
                  peerBusy={peerBusy}
                  peerFeedback={peerFeedback}
                  onClearPeerFeedback={() => setPeerFeedback(null)}
                  peerProfile={peerProfile}
                  onSelectPeerProfile={setPeerProfile}
                  onDiscoverPeer={handleDiscoverPeer}
                  onSendFriendRequest={handleSendFriendReq}
                  suggestedPeers={suggestedPeers}
                  contacts={contacts}
                  onOpenChatWithContact={handleOpenChatWithContact}
                  t={t}
                />
              )}

              {activeApp === 'shop' && (
                <PhoneShopApp
                  branding={branding}
                  shopData={shopData}
                  loadingShop={loadingShop}
                  buyingItem={buyingItem}
                  shopFeedback={shopFeedback}
                  onClearFeedback={() => setShopFeedback(null)}
                  onBuyDeliveryItem={handleBuyDeliveryItem}
                  scenario={scenarioKey}
                  t={t}
                />
              )}

              {activeApp === 'bounties' && (
                <PhoneBountiesApp
                  branding={branding}
                  generatingBounties={generatingBounties}
                  onRefreshBounties={handleRefreshBounties}
                  bountySubTab={bountySubTab}
                  onChangeBountySubTab={setBountySubTab}
                  allAvailableBounties={allAvailableBounties}
                  availableBounties={availableBounties}
                  activeBounties={activeBounties}
                  factionsList={factionsList}
                  selectedFactionFilter={selectedFactionFilter}
                  onSelectFactionFilter={setSelectedFactionFilter}
                  bountyActionBanner={bountyActionBanner}
                  onClearBanner={() => setBountyActionBanner(null)}
                  onAcceptBounty={handleAcceptBounty}
                  onAbandonBounty={handleAbandonBounty}
                  busyBountyId={busyBountyId}
                  scenario={scenarioKey}
                  t={t}
                />
              )}
            </div>

            {/* Expanded Photo Preview Overlay */}
            {liveSelectedPhoto && (
              <div
                data-phone-style="classic"
                className="absolute inset-0 hk-phone-lightbox z-30 flex flex-col p-4"
              >
                <div className="flex justify-between items-center border-b border-neutral-800 pb-2 mb-3 shrink-0">
                  <span className="font-bold text-xs text-pink-300 truncate">{liveSelectedPhoto.contact_name}</span>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedPhoto(null);
                      setPhotoActionError(null);
                    }}
                    className="p-1 text-gray-400 hover:text-gray-100 cursor-pointer"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col items-center justify-center p-3 text-center space-y-3 bg-neutral-950 border border-neutral-800 rounded-2xl min-h-0">
                  {(() => {
                    const isVideo = isVideoMediaItem(liveSelectedPhoto);
                    const isGenerating =
                      liveSelectedPhoto.image_status === 'generating' ||
                      (liveSelectedPhoto.id && String(generatingPhotoId) === String(liveSelectedPhoto.id));
                    const hasImage = Boolean(liveSelectedPhoto.image_url);

                    return (
                      <>
                        {hasImage ? (
                          <div className="relative w-full max-w-[270px] rounded-xl overflow-hidden border border-white/15 hk-phone-media-frame shadow-lg shrink-0">
                            <img
                              src={liveSelectedPhoto.image_url}
                              alt={liveSelectedPhoto.caption || liveSelectedPhoto.name}
                              className="w-full max-h-[340px] object-cover object-top"
                            />
                            {isVideo && (
                              <span className="absolute inset-0 m-auto w-11 h-11 rounded-full hk-phone-play-badge flex items-center justify-center hk-phone-icon-glyph">
                                <Play size={18} className="ml-0.5" />
                              </span>
                            )}
                          </div>
                        ) : isGenerating ? (
                          <div className="w-full max-w-[240px] h-52 rounded-xl border border-pink-500/40 bg-pink-950/20 flex flex-col items-center justify-center gap-2 animate-pulse shrink-0">
                            <Loader2 size={26} className="animate-spin text-pink-400" />
                            <span className="text-xs font-semibold text-pink-200">
                              {t('phone.vault.generating', 'Developing...')}
                            </span>
                          </div>
                        ) : (
                          <div className="w-16 h-16 rounded-full bg-pink-950/60 border border-pink-700/60 flex items-center justify-center text-pink-300 shrink-0">
                            {isVideo ? <Video size={28} /> : <Camera size={28} />}
                          </div>
                        )}

                        <h5 className="font-bold text-sm text-gray-100">{liveSelectedPhoto.name}</h5>
                        <p className="text-xs text-gray-300 leading-relaxed max-w-xs italic bg-neutral-900/80 p-3 rounded-xl border border-neutral-800">
                          &ldquo;{liveSelectedPhoto.caption}&rdquo;
                        </p>

                        {photoActionError && (
                          <p className="text-[11px] text-red-300 bg-red-950/50 border border-red-800/60 rounded-lg px-2.5 py-1.5 max-w-xs">
                            {photoActionError}
                          </p>
                        )}

                        <div className="flex flex-wrap gap-1 justify-center">
                          {liveSelectedPhoto.tags?.map((tag, i) => (
                            <span key={i} className="text-[10px] px-2 py-0.5 bg-neutral-800 text-gray-400 rounded-full font-mono">
                              #{tag}
                            </span>
                          ))}
                        </div>

                        <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
                          {liveSelectedPhoto.id && isImgGenActive && (
                            <button
                              type="button"
                              disabled={isGenerating}
                              onClick={() =>
                                handleGenerateMediaPhoto(liveSelectedPhoto.id, { forceRegenerate: hasImage })
                              }
                              className="px-3 py-1.5 rounded-xl bg-pink-600/30 hover:bg-pink-600/50 text-pink-200 border border-pink-500/50 text-xs font-bold transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
                            >
                              {isGenerating ? (
                                <Loader2 size={13} className="animate-spin" />
                              ) : hasImage ? (
                                <RefreshCw size={13} />
                              ) : (
                                <Sparkles size={13} />
                              )}
                              <span>
                                {hasImage
                                  ? t('phone.vault.regenerate', 'Regenerate')
                                  : t('phone.vault.generate_photo', 'Generate Photo')}
                              </span>
                            </button>
                          )}

                          {hasImage && !isVideo && session?.id && (
                            <button
                              type="button"
                              onClick={() => handleSetPhotoAsWallpaper(liveSelectedPhoto)}
                              className={`px-3 py-1.5 rounded-xl border text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5 ${
                                isSelectedPhotoActiveWallpaper
                                  ? 'bg-emerald-600/35 text-emerald-200 border-emerald-400/60'
                                  : 'bg-sky-600/30 hover:bg-sky-600/50 text-sky-200 border-sky-500/50'
                              }`}
                            >
                              {isSelectedPhotoActiveWallpaper ? <Check size={13} /> : <ImageIcon size={13} />}
                              <span>
                                {isSelectedPhotoActiveWallpaper
                                  ? t('phone.vault.active_wallpaper', 'Active Wallpaper')
                                  : t('phone.vault.set_wallpaper', 'Set as Wallpaper')}
                              </span>
                            </button>
                          )}

                          {liveSelectedPhoto.id && (
                            <button
                              type="button"
                              disabled={deletingPhoto}
                              onClick={() => handleDeleteMedia(liveSelectedPhoto)}
                              className="px-3 py-1.5 rounded-xl bg-red-950/60 hover:bg-red-900/70 text-red-300 border border-red-800/60 text-xs font-bold transition-colors cursor-pointer"
                            >
                              {deletingPhoto
                                ? t('phone.vault.deleting', 'Deleting...')
                                : t('phone.vault.delete_media', '🗑️ Delete Media')}
                            </button>
                          )}
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {/* Gesture Navigation Bar */}
            <div
              className={`relative z-10 px-5 py-2.5 border-t flex items-center justify-between shrink-0 select-none ${
                isGlass
                  ? 'hk-phone-chrome'
                  : 'bg-neutral-950/95 border-neutral-800/70'
              }`}
            >
              <button
                type="button"
                onClick={() => {
                  if (selectedPhoto) {
                    setSelectedPhoto(null);
                    setPhotoActionError(null);
                  } else if (activeApp === 'dms' && activeChatNpc) {
                    setDmOutcomeBanner(null);
                    closeChat();
                  } else if (activeApp !== 'home') {
                    setActiveApp('home');
                  } else {
                    onClose();
                  }
                }}
                className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold text-gray-400 hover:text-white hover:bg-neutral-800/70 transition-all active:scale-95 cursor-pointer"
                title={t('phone.nav.back_tooltip', 'Back / Previous Screen')}
              >
                <ChevronLeft size={16} />
                <span className="text-[11px]">{t('phone.nav.back', 'Back')}</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  if (activeApp !== 'home' || selectedPhoto || activeChatNpc) {
                    setActiveApp('home');
                    setSelectedPhoto(null);
                    setPhotoActionError(null);
                    setDmOutcomeBanner(null);
                    if (closeChat) closeChat();
                  } else {
                    onClose();
                  }
                }}
                className="group py-2 px-6 flex items-center justify-center cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/80 rounded-full"
                title={activeApp !== 'home' ? t('phone.nav.tap_home', 'Tap for Home') : t('phone.nav.tap_lock', 'Tap to Lock Phone')}
              >
                <div className="w-28 h-1.5 bg-neutral-600 group-hover:bg-neutral-300 rounded-full transition-all group-active:scale-95 group-hover:h-2" />
              </button>

              <button
                type="button"
                onClick={onClose}
                className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold text-gray-400 hover:text-white hover:bg-neutral-800/70 transition-all active:scale-95 cursor-pointer"
                title={t('phone.nav.lock_tooltip', 'Lock & Sleep Phone')}
              >
                <span className="text-[11px]">{t('phone.nav.lock', 'Lock')}</span>
                <X size={14} />
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  return typeof document !== 'undefined'
    ? createPortal(modalContent, document.body)
    : modalContent;
};

export default PhoneModal;
