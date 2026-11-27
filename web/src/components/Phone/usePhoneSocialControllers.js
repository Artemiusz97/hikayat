import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { apiCall } from '../../api/client';
import {
  buildCarouselCandidates,
  isIntimateMediaItem,
  isVideoMediaItem,
  pickNextCarouselWallpaper,
} from './phoneWallpapers';

export function usePhoneSocialControllers({
  isOpen,
  activeApp,
  setActiveApp,
  session,
  user,
  phoneHook,
  phonePrefs,
  setPhonePref,
  setSessionPhoneWallpaper,
  onRefreshInventory,
  onRefreshCodex,
  commsOffline = false,
  t,
}) {
  const {
    appointments,
    commitments: phoneCommitments = [],
    gossipFeed,
    mediaGallery,
    contacts,
    dispatchChannels = [],
    activeChatNpc,
    sendingChat,
    generateMediaPhoto,
    loadChatMessages,
    sendMessage,
    refreshFeed,
    scourFeed,
    discoverPeer,
    sendFriendRequest,
    refreshPhoneData,
    cancelCommitment,
  } = phoneHook;

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
  const [cancellingCommitmentId, setCancellingCommitmentId] = useState(null);

  // Feed & PeerPulse state
  const [feedSubTab, setFeedSubTab] = useState('timeline'); // 'timeline' | 'peerpulse'
  const [feedBusy, setFeedBusy] = useState(false);
  const [feedBanner, setFeedBanner] = useState(null);
  const [peerQuery, setPeerQuery] = useState('');
  const [peerProfile, setPeerProfile] = useState(null);
  const [peerBusy, setPeerBusy] = useState(false);
  const [peerFeedback, setPeerFeedback] = useState(null);

  const prevSessionIdRef = useRef(session?.id ?? null);
  const lastCarouselKeyRef = useRef(null);
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

  const plannerItems =
    phoneCommitments && phoneCommitments.length > 0 ? phoneCommitments : appointments || [];

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

  const autoFeedAttemptedRef = useRef(false);
  const handleRefreshFeedRef = useRef(null);
  const hasRefreshFeed = Boolean(refreshFeed);
  handleRefreshFeedRef.current = handleRefreshFeed;

  useEffect(() => {
    if (!isOpen || activeApp !== 'feed' || commsOffline) {
      autoFeedAttemptedRef.current = false;
      return;
    }
    if ((!gossipFeed || gossipFeed.length === 0) && !feedBusy && hasRefreshFeed && !autoFeedAttemptedRef.current) {
      autoFeedAttemptedRef.current = true;
      handleRefreshFeedRef.current?.();
    }
  }, [isOpen, activeApp, commsOffline, gossipFeed, feedBusy, hasRefreshFeed]);

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
        spirit_relay_unlocked: Boolean(c.spirit_relay_unlocked || c.basic_info?.spirit_relay_unlocked),
        anomalous_npc_tag: c.anomalous_npc_tag || c.basic_info?.anomalous_npc_tag || null,
        deceased: Boolean(c.deceased || c.basic_info?.deceased),
      });
    }
  });

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
    } catch (err) {
      setDmInput(text);
      setDmOutcomeBanner({
        error: err?.message || t('phone.dms.send_failed', 'Failed to send message.'),
      });
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

  return {
    activeCarouselEntry,
    advanceCarousel,

    selectedPhoto,
    setSelectedPhoto,
    liveSelectedPhoto,
    photoCategory,
    setPhotoCategory,
    photoContactFilter,
    setPhotoContactFilter,
    deletingPhoto,
    generatingPhotoId,
    photoActionError,
    setPhotoActionError,
    galleryContacts,
    filteredGallery,
    isSelectedPhotoActiveWallpaper,
    handleDeleteMedia,
    handleGenerateMediaPhoto,
    handleSetPhotoAsWallpaper,

    feedSubTab,
    setFeedSubTab,
    feedBusy,
    feedBanner,
    setFeedBanner,
    peerQuery,
    setPeerQuery,
    peerProfile,
    setPeerProfile,
    peerBusy,
    peerFeedback,
    setPeerFeedback,
    handleRefreshFeed,
    handleScourRumor,
    handleDiscoverPeer,
    handleSendFriendReq,

    messagesSubTab,
    setMessagesSubTab,
    dmInput,
    setDmInput,
    selectedIntent,
    dmOutcomeBanner,
    setDmOutcomeBanner,
    cancellingCommitmentId,
    plannerItems,
    dmDirectory,
    dispatchDirectory,
    showDispatchTab,
    activeContactEntry,
    isDispatchThread,
    isBlockedContact,
    activeDisplayTitle,
    handleOpenChatWithContact,
    handleCancelPlannerItem,
    handleSendDm,
    handleInstantIntentSend,
  };
}
