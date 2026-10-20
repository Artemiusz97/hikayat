import React, { useState, useEffect, useRef } from 'react';
import {
  X, Camera, Video, MessageSquare, Rss, Wifi,
  MapPin, Calendar, Sparkles, ChevronLeft, Send, User, Image as ImageIcon, Heart, ShoppingBag,
  Search, RefreshCw, UserPlus, Users, ShieldAlert, GripHorizontal
} from 'lucide-react';

const formatTimestamp = (ts) => {
  if (!ts) return 'Just now';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const PhoneModal = ({ isOpen, onClose, phoneHook, codexHook, session, user, onRefreshInventory, onRefreshCodex, onRefreshCharacter }) => {
  const [activeApp, setActiveApp] = useState('home'); // 'home' | 'photos' | 'dms' | 'feed' | 'shop' | 'bounties'
  const [selectedPhoto, setSelectedPhoto] = useState(null);
  const [photoCategory, setPhotoCategory] = useState('all'); // 'all' | 'photo' | 'intimate' | 'video'
  const [photoContactFilter, setPhotoContactFilter] = useState('__all__');
  const [deletingPhoto, setDeletingPhoto] = useState(false);
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

  const [shopData, setShopData] = useState(null);
  const [loadingShop, setLoadingShop] = useState(false);
  const [buyingItem, setBuyingItem] = useState(null);
  const [shopFeedback, setShopFeedback] = useState(null);

  // Requests / Bounties state
  const [bountySubTab, setBountySubTab] = useState('available'); // 'available' | 'active'
  const [selectedFactionFilter, setSelectedFactionFilter] = useState('all');
  const [generatingBounties, setGeneratingBounties] = useState(false);
  const [bountyActionBanner, setBountyActionBanner] = useState(null);

  // Draggable window state
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef({ startX: 0, startY: 0, initialX: 0, initialY: 0 });

  // Reset to centered position and home screen when opened
  useEffect(() => {
    if (isOpen) {
      setPosition({ x: 0, y: 0 });
      setActiveApp('home');
      setSelectedPhoto(null);
    }
  }, [isOpen]);

  const handleStartDrag = (clientX, clientY) => {
    setIsDragging(true);
    dragRef.current = {
      startX: clientX,
      startY: clientY,
      initialX: position.x,
      initialY: position.y,
    };
  };

  const handleMouseDown = (e) => {
    if (e.button !== 0) return;
    if (e.target.closest('button, input, textarea, select, a, [role="button"]')) return;
    handleStartDrag(e.clientX, e.clientY);
  };

  const handleTouchStart = (e) => {
    if (e.target.closest('button, input, textarea, select, a, [role="button"]')) return;
    const touch = e.touches[0];
    if (touch) {
      handleStartDrag(touch.clientX, touch.clientY);
    }
  };

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e) => {
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      const nextX = dragRef.current.initialX + dx;
      const nextY = dragRef.current.initialY + dy;

      const limitX = Math.max(80, (window.innerWidth - 320) / 2);
      const limitY = Math.max(80, (window.innerHeight - 320) / 2);

      setPosition({
        x: Math.max(-limitX, Math.min(limitX, nextX)),
        y: Math.max(-limitY, Math.min(limitY, nextY)),
      });
    };

    const handleTouchMove = (e) => {
      const touch = e.touches[0];
      if (!touch) return;
      const dx = touch.clientX - dragRef.current.startX;
      const dy = touch.clientY - dragRef.current.startY;
      const nextX = dragRef.current.initialX + dx;
      const nextY = dragRef.current.initialY + dy;

      const limitX = Math.max(80, (window.innerWidth - 320) / 2);
      const limitY = Math.max(80, (window.innerHeight - 320) / 2);

      setPosition({
        x: Math.max(-limitX, Math.min(limitX, nextX)),
        y: Math.max(-limitY, Math.min(limitY, nextY)),
      });
    };

    const handleEndDrag = () => {
      setIsDragging(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleEndDrag);
    window.addEventListener('touchmove', handleTouchMove);
    window.addEventListener('touchend', handleEndDrag);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleEndDrag);
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleEndDrag);
    };
  }, [isDragging]);

  const {
    branding, appointments, gossipFeed, mediaGallery, contacts, suggestedPeers = [], socialState,
    activeChatNpc, chatMessages, dailyLimits, loadingChat, sendingChat,
    loadChatMessages, sendMessage, closeChat,
    refreshFeed, scourFeed, discoverPeer, sendFriendRequest, refreshPhoneData
  } = phoneHook;

  const handleDeleteMedia = async (photo) => {
    if (!photo?.id || !user?.user_id || deletingPhoto) return;
    setDeletingPhoto(true);
    try {
      await fetch('/api/inventory/drop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: user.user_id,
          item_id: photo.id,
        }),
      });
      setSelectedPhoto(null);
      if (refreshPhoneData) await refreshPhoneData();
      if (onRefreshInventory) onRefreshInventory();
    } catch {
      // ignore
    } finally {
      setDeletingPhoto(false);
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
    if (isOpen && activeApp === 'shop' && session?.id && user?.user_id) {
      setLoadingShop(true);
      setShopFeedback(null);
      fetch(`/api/merchant/${session.id}?user_id=${user.user_id}&is_phone_shop=true`)
        .then(res => res.json())
        .then(data => setShopData(data))
        .catch(() => {})
        .finally(() => setLoadingShop(false));
    }
  }, [isOpen, activeApp, session?.id, user?.user_id]);

  const handleBuyDeliveryItem = async (item) => {
    if (!session?.id || !user?.user_id || buyingItem) return;
    setBuyingItem(item.name);
    setShopFeedback(null);
    try {
      const res = await fetch('/api/merchant/buy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: session.id,
          item_name: item.name,
          is_phone_shop: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setShopFeedback({ type: 'error', text: data.detail || 'Order failed.' });
      } else {
        setShopFeedback({ type: 'ok', text: data.message || `Ordered ${item.name}!` });
        setShopData(prev => prev ? { ...prev, gold: data.gold } : prev);
        if (onRefreshInventory) onRefreshInventory();
        if (onRefreshCharacter) onRefreshCharacter();
      }
    } catch (err) {
      setShopFeedback({ type: 'error', text: err.message });
    } finally {
      setBuyingItem(null);
    }
  };

  const handleRefreshBounties = async (factionId = null) => {
    if (generatingBounties || !codexHook?.generateBounties) return;
    setGeneratingBounties(true);
    setBountyActionBanner(null);
    try {
      const targetFaction = factionId !== undefined ? factionId : (selectedFactionFilter !== 'all' ? selectedFactionFilter : null);
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
    if (!codexHook?.bountyAction) return;
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'accept');
      setBountyActionBanner({
        type: 'ok',
        text: `✅ Accepted "${questTitle}" — Moved to Active Tasks!`
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not accept request.' });
    }
  };

  const handleAbandonBounty = async (questId, questTitle) => {
    if (!codexHook?.bountyAction) return;
    setBountyActionBanner(null);
    try {
      await codexHook.bountyAction(questId, 'abandon');
      setBountyActionBanner({
        type: 'warn',
        text: `Dropped task "${questTitle}".`
      });
      if (onRefreshCodex) onRefreshCodex();
      if (onRefreshCharacter) onRefreshCharacter();
    } catch (err) {
      setBountyActionBanner({ type: 'error', text: err.message || 'Could not abandon request.' });
    }
  };

  let displayTime = '9:41';
  if (session && session.current_minute !== undefined) {
    const hours = Math.floor(session.current_minute / 60) % 24;
    const mins = session.current_minute % 60;
    displayTime = `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
  }

  // Unique contact names in media gallery
  const galleryContacts = Array.from(
    new Set((mediaGallery || []).map(m => m.contact_name).filter(Boolean))
  ).sort();

  const filteredGallery = (mediaGallery || []).filter(m => {
    const mType = (m.media_type || '').toLowerCase();
    const isVideo = mType.includes('video');
    const isIntimate = mType.includes('nsfw') || mType.includes('intimate');
    if (photoCategory === 'video' && !isVideo) return false;
    if (photoCategory === 'intimate' && !isIntimate) return false;
    if (photoCategory === 'photo' && (isVideo || isIntimate)) return false;
    if (photoContactFilter !== '__all__' && m.contact_name !== photoContactFilter) return false;
    return true;
  });

  // Build unified DM contact list from contacts + appointments
  const dmDirectory = [];
  const seenIds = new Set();
  (contacts || []).forEach(c => {
    const id = c.npc_id || c.name;
    if (id && !seenIds.has(id.toLowerCase())) {
      seenIds.add(id.toLowerCase());
      dmDirectory.push({
        npc_id: c.npc_id || c.name,
        name: c.name || c.npc_id,
        role: c.basic_info?.role || c.basic_info?.occupation || 'Contact',
        score: c.relationship_score ?? 0
      });
    }
  });
  (appointments || []).forEach(appt => {
    const id = appt.npc_id || appt.npc_name;
    if (id && !seenIds.has(id.toLowerCase())) {
      seenIds.add(id.toLowerCase());
      dmDirectory.push({
        npc_id: appt.npc_id || appt.npc_name,
        name: appt.npc_name || appt.npc_id,
        role: `Rendezvous: ${appt.rendezvous_location}`,
        score: null
      });
    }
  });

  const allAvailableBounties = codexHook?.availableBounties || [];
  const factionsList = codexHook?.factions || [];

  const availableBounties = allAvailableBounties.filter(b => {
    if (selectedFactionFilter === 'all') return true;
    const bFaction = (b.faction_id || b.faction_name || b.faction || '').toLowerCase();
    const targetF = factionsList.find(f => f.faction_id === selectedFactionFilter || f.name === selectedFactionFilter);
    const targetId = (targetF?.faction_id || selectedFactionFilter).toLowerCase();
    const targetName = (targetF?.name || '').toLowerCase();
    return (
      bFaction === targetId ||
      (targetName && bFaction.includes(targetName)) ||
      (b.title && targetName && b.title.toLowerCase().includes(targetName)) ||
      (b.objective && targetName && b.objective.toLowerCase().includes(targetName))
    );
  });

  const activeBounties = (codexHook?.quests || []).filter(q => q.status === 'Active' && (
    (q.quest_id && (q.quest_id.startsWith('BNT-') || q.quest_id.startsWith('FBNT-'))) ||
    (q.quest_type && (q.quest_type.includes('Bounty') || q.quest_type.includes('Request') || q.quest_type.includes('Commission') || q.quest_type.includes('Gig')))
  ));

  // Auto-generate bounties when opening requests app if none exist
  useEffect(() => {
    if (isOpen && activeApp === 'bounties' && allAvailableBounties.length === 0 && !generatingBounties && codexHook?.generateBounties) {
      setGeneratingBounties(true);
      codexHook.generateBounties().finally(() => setGeneratingBounties(false));
    }
  }, [isOpen, activeApp, allAvailableBounties.length]);

  // Auto-refresh feed when opening feed app if empty
  useEffect(() => {
    if (isOpen && activeApp === 'feed' && (!gossipFeed || gossipFeed.length === 0) && !feedBusy && refreshFeed) {
      refreshFeed();
    }
  }, [isOpen, activeApp, gossipFeed?.length]);

  const apps = [
    {
      id: 'photos',
      name: branding.gallery_app_name || 'Photo Vault',
      subtitle: 'Vault & Media',
      icon: Camera,
      gradient: 'from-pink-500 via-rose-500 to-pink-600',
      badge: (mediaGallery || []).length > 0 ? mediaGallery.length : null,
      badgeColor: 'bg-pink-500',
    },
    {
      id: 'dms',
      name: branding.dm_app_name || 'Messages',
      subtitle: 'Chats & Meetups',
      icon: MessageSquare,
      gradient: 'from-emerald-500 via-teal-500 to-cyan-600',
      badge: (appointments || []).length > 0 ? appointments.length : null,
      badgeColor: 'bg-emerald-500',
    },
    {
      id: 'feed',
      name: branding.feed_app_name || 'PeerPulse',
      subtitle: 'Radar & Social',
      icon: Rss,
      gradient: 'from-violet-500 via-purple-600 to-indigo-600',
      badge: (gossipFeed || []).length > 0 ? gossipFeed.length : null,
      badgeColor: 'bg-purple-500',
    },
    {
      id: 'shop',
      name: branding.shop_app_name || 'SchoolMart Delivery',
      subtitle: branding.shop_subtitle || 'Online Courier',
      icon: ShoppingBag,
      gradient: 'from-amber-500 via-orange-500 to-amber-600',
      badge: null,
      badgeColor: 'bg-amber-500',
    },
    {
      id: 'planner',
      name: branding.planner_app_name || 'Planner & Agenda',
      subtitle: 'Schedule & Rendezvous',
      icon: Calendar,
      gradient: 'from-blue-500 via-indigo-500 to-sky-600',
      badge: (appointments || []).length > 0 ? appointments.length : null,
      badgeColor: 'bg-blue-500',
    },
    {
      id: 'bounties',
      name: branding.bounty_app_name || branding.bounties_app_name || 'Campus Requests',
      subtitle: branding.bounty_subtitle || 'Student Bulletin',
      icon: ShieldAlert,
      gradient: 'from-rose-500 via-red-600 to-rose-700',
      badge: availableBounties.length > 0 ? availableBounties.length : null,
      badgeColor: 'bg-rose-500',
    },
  ];

  const processDmOutcome = (res) => {
    const replyObj = res?.reply && typeof res.reply === 'object' ? res.reply : res;
    if (replyObj && (replyObj.check || replyObj.check_result || replyObj.affinity_delta !== undefined || replyObj.rendezvous_location || replyObj.media_dropped)) {
      setDmOutcomeBanner({
        check: replyObj.check || replyObj.check_result,
        affinity_delta: replyObj.affinity_delta,
        rendezvous_location: replyObj.rendezvous_location,
        media_dropped: replyObj.media_dropped,
      });
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
    } catch {
      // ignore
    }
  };

  if (!isOpen) return null;

  return (
    <div 
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="fixed inset-0 z-50 flex flex-col md:items-center md:justify-center md:p-4 bg-neutral-950 md:bg-black/80 md:backdrop-blur-md text-gray-100 select-none overflow-hidden"
    >
      {/* Phone Shell: Full-screen on mobile, centered phone shell on desktop */}
      <div className="w-full h-full md:max-w-[420px] md:h-[840px] md:max-h-[92vh] md:rounded-[44px] md:border-[6px] md:border-neutral-800 md:shadow-[0_0_50px_rgba(0,0,0,0.85)] md:ring-1 md:ring-neutral-700/50 flex flex-col bg-neutral-950 overflow-hidden relative pb-[max(0.6rem,env(safe-area-inset-bottom))] md:pb-0">
        
        {/* Dynamic Island / Speaker Notch & Status Bar (Restored for desktop browser version, hidden on mobile) */}
        <div className="hidden md:flex relative px-6 pt-3 pb-2 justify-between items-center text-xs font-semibold text-gray-200 bg-neutral-950/90 z-20 shrink-0">
          <span className="font-mono text-[11px] tracking-tight select-none">{displayTime}</span>

          {/* Truly Centered Dynamic Island / Camera Notch */}
          <div className="absolute left-1/2 -translate-x-1/2 top-1/2 -translate-y-1/2 w-24 h-4 bg-black rounded-full flex items-center justify-center gap-1.5 border border-neutral-800/80 shadow-inner pointer-events-none">
            <span className="w-2 h-2 rounded-full bg-neutral-800" />
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-950/80" />
          </div>

          <div className="flex items-center gap-1.5 text-gray-300 select-none">
            <Wifi size={12} className="text-gray-300" />
            <span className="text-[10px] font-mono text-gray-300">5G</span>

            {/* Almost-full battery indicator (~88%) */}
            <div className="flex items-center gap-[1px]" title="Battery: 88%">
              <div className="w-[18px] h-[9.5px] rounded-[3px] border border-emerald-400/90 p-[1px] flex items-center bg-black/40">
                <div className="h-full w-[88%] bg-emerald-400 rounded-[1px]" />
              </div>
              <div className="w-[1.5px] h-[4px] bg-emerald-400/90 rounded-r-[1px]" />
            </div>
          </div>
        </div>

        {/* In-App Header (Only rendered when inside an app; hidden on home screen to eliminate useless smartphone label) */}
        {activeApp !== 'home' && (
          <div className="px-4 py-2 flex items-center justify-between border-b border-neutral-900 bg-neutral-950/95 shrink-0 select-none">
            <button
              type="button"
              onClick={() => {
                setActiveApp('home');
                setSelectedPhoto(null);
                if (closeChat) closeChat();
              }}
              className="flex items-center gap-1 text-xs font-semibold text-pink-400 hover:text-pink-300 transition-colors cursor-pointer"
            >
              <ChevronLeft size={16} />
              <span>Back to Apps</span>
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-full text-gray-400 hover:text-white hover:bg-neutral-800 transition-colors cursor-pointer"
              title="Close Phone"
            >
              <X size={18} />
            </button>
          </div>
        )}

        {/* Screen Canvas */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-3.5 py-2.5 bg-gradient-to-b from-neutral-900/40 to-black relative flex flex-col min-h-0">

          {/* 0. SMARTPHONE HOME MENU */}
          {activeApp === 'home' && (
            <div className="flex flex-col h-full space-y-4 select-none pb-2">
              {/* Lockscreen / Clock Widget */}
              <div className="pt-2 pb-1 flex flex-col items-center">
                <span className="font-sans font-light text-5xl text-white tracking-tight drop-shadow-md">
                  {displayTime}
                </span>
                <span className="text-xs text-neutral-400 font-medium mt-1 flex items-center gap-1.5">
                  <Sparkles size={12} className="text-pink-400" />
                  <span>{session?.scenario_display_name || session?.scenario || 'Connected OS'}</span>
                  {session?.day && <span className="font-mono text-neutral-500">• Day {session.day}</span>}
                  {session?.time_of_day && <span className="text-amber-400/80">• {session.time_of_day}</span>}
                </span>
              </div>

              {/* Quick Glance Notification Banner */}
              {(appointments.length > 0 || availableBounties.length > 0) && (
                <div className="bg-neutral-900/80 border border-neutral-800 rounded-2xl p-2.5 flex items-center justify-between shadow-lg">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-7 h-7 rounded-full bg-pink-500/20 text-pink-300 flex items-center justify-center shrink-0">
                      {appointments.length > 0 ? <MessageSquare size={13} /> : <ShieldAlert size={13} />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-[11px] font-bold text-gray-200 truncate">
                        {appointments.length > 0
                          ? `${appointments.length} Rendezvous Planned`
                          : `${availableBounties.length} Requests Posted`}
                      </p>
                      <p className="text-[10px] text-gray-400 truncate">
                        {appointments.length > 0
                          ? 'Check Messages for meetup details'
                          : 'Visit Campus Requests for active tasks'}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setActiveApp(appointments.length > 0 ? 'dms' : 'bounties')}
                    className="px-2.5 py-1 rounded-full bg-pink-600/30 hover:bg-pink-600/50 text-pink-300 text-[10px] font-bold shrink-0 transition-colors border border-pink-500/40"
                  >
                    Open
                  </button>
                </div>
              )}

              {/* Main App Grid (iOS / Android Style) */}
              <div className="space-y-2 flex-1 pt-2">
                <div className="flex items-center justify-between px-1">
                  <span className="text-[10px] uppercase font-bold tracking-wider text-neutral-500 font-mono">Applications</span>
                  <span className="text-[10px] font-mono text-neutral-600">{apps.length} Installed</span>
                </div>

                <div className="grid grid-cols-3 gap-y-5 gap-x-3 p-1">
                  {apps.map(app => {
                    const Icon = app.icon;
                    return (
                      <button
                        key={app.id}
                        type="button"
                        onClick={() => { setActiveApp(app.id); setSelectedPhoto(null); }}
                        className="flex flex-col items-center group cursor-pointer focus:outline-none transition-transform duration-150 active:scale-95"
                      >
                        <div className={`w-15 h-15 rounded-2xl bg-gradient-to-br ${app.gradient} flex items-center justify-center text-white shadow-lg shadow-black/50 group-hover:shadow-pink-500/20 group-hover:scale-105 transition-all relative border border-white/20`}>
                          <Icon size={27} className="drop-shadow-md text-white" />
                          {app.badge !== null && app.badge > 0 && (
                            <span className={`absolute -top-1.5 -right-1.5 min-w-5 h-5 px-1 rounded-full ${app.badgeColor} text-white text-[10px] font-bold flex items-center justify-center border-2 border-neutral-950 shadow-md`}>
                              {app.badge}
                            </span>
                          )}
                        </div>
                        <span className="text-xs font-semibold text-gray-200 mt-1.5 text-center truncate max-w-[88px] group-hover:text-pink-300 transition-colors">
                          {app.name}
                        </span>
                        <span className="text-[9px] text-gray-500 text-center truncate max-w-[88px]">
                          {app.subtitle}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* 7. PLANNER & RENDEZVOUS APP */}
          {activeApp === 'planner' && (
            <div className="flex-1 flex flex-col min-h-0 bg-neutral-950 text-neutral-100 overflow-hidden">
              {/* App Subheader */}
              <div className="px-4 py-3 bg-neutral-900/90 border-b border-neutral-800 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-blue-500 to-sky-600 flex items-center justify-center text-white shadow-sm">
                    <Calendar size={16} />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-neutral-200 uppercase tracking-wider">{branding.planner_app_name || 'Planner & Agenda'}</h3>
                    <p className="text-[10px] text-neutral-400 font-mono">Day {session?.current_day || 1} • In-Game Timeline</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] font-mono">
                    {appointments.length} Active
                  </span>
                </div>
              </div>

              {/* Appointments List */}
              <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
                {appointments.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-52 text-center text-neutral-500 space-y-2">
                    <div className="w-12 h-12 rounded-full bg-neutral-900 border border-neutral-800 flex items-center justify-center text-neutral-600">
                      <Calendar size={22} />
                    </div>
                    <div className="text-xs font-medium text-neutral-400">No Upcoming Meetups</div>
                    <p className="text-[10px] max-w-[220px] text-neutral-500 leading-relaxed">
                      Message a contact or agree on plans in conversation to schedule physical rendezvous.
                    </p>
                    <button
                      type="button"
                      onClick={() => setActiveApp('dms')}
                      className="mt-2 px-3 py-1.5 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 text-[11px] font-medium transition-colors cursor-pointer"
                    >
                      Open Messages
                    </button>
                  </div>
                ) : (
                  appointments.map((appt, i) => {
                    const isArrived = appt.status === 'arrived';
                    const isConfidential = Boolean(appt.is_confidential);
                    const shortLoc = (appt.rendezvous_location || appt.target_location || '').split('➔').pop().trim();
                    const npcName = appt.npc_name || appt.target_entity || 'Contact';

                    const hasOverlapConflict = appointments.some(other => {
                      if (!other || (other.id && other.id === appt.id) || (other.npc_id && other.npc_id === appt.npc_id)) return false;
                      const sameDay = (other.scheduled_day || 1) === (appt.scheduled_day || 1);
                      if (!sameDay) return false;
                      const oStart = other.start_minute ?? (other.created_minute ? other.created_minute % 1440 : 0);
                      const oEnd = other.end_minute ?? (other.expiry_minute ? other.expiry_minute % 1440 : 1439);
                      const aStart = appt.start_minute ?? (appt.created_minute ? appt.created_minute % 1440 : 0);
                      const aEnd = appt.end_minute ?? (appt.expiry_minute ? appt.expiry_minute % 1440 : 1439);
                      return Math.max(oStart, aStart) < Math.min(oEnd, aEnd);
                    });

                    return (
                      <div
                        key={appt.id || i}
                        className={`p-3.5 rounded-2xl border transition-all ${
                          isArrived
                            ? 'bg-emerald-950/20 border-emerald-500/40 shadow-sm shadow-emerald-950/50'
                            : 'bg-neutral-900/60 border-neutral-800/80 hover:border-neutral-700'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                              isArrived ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-neutral-800 text-neutral-300'
                            }`}>
                              {npcName.slice(0, 2).toUpperCase()}
                            </div>
                            <div>
                              <div className="text-xs font-bold text-neutral-100 flex items-center gap-1.5 flex-wrap">
                                {npcName}
                                {isConfidential && (
                                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40">
                                    Private 1-on-1
                                  </span>
                                )}
                                {hasOverlapConflict && (
                                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40">
                                    ⚠️ Overlap
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-neutral-400 flex items-center gap-1 mt-0.5">
                                <MapPin size={10} className="text-neutral-500" />
                                <span className="truncate max-w-[180px]">{shortLoc || 'Scheduled Venue'}</span>
                              </div>
                            </div>
                          </div>

                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-medium ${
                            isArrived
                              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                              : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                          }`}>
                            {isArrived ? 'Arrived & Waiting' : 'Scheduled'}
                          </span>
                        </div>

                        {appt.topic && (
                          <p className="mt-2.5 text-[11px] text-neutral-300 bg-neutral-950/60 p-2 rounded-xl border border-neutral-800/60 italic">
                            "{appt.topic}"
                          </p>
                        )}

                        <div className="mt-3 pt-2.5 border-t border-neutral-800/60 flex items-center justify-between text-[10px]">
                          <span className="text-neutral-500 font-mono">
                            {appt.created_minute ? `Window: ${Math.floor(appt.created_minute % 1440 / 60)}:${String(appt.created_minute % 60).padStart(2, '0')}` : 'Flexible Window'}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              openChat(appt.npc_id || npcName);
                            }}
                            className="px-2.5 py-1 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-[10px] font-medium transition-colors cursor-pointer"
                          >
                            Message Contact
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          {/* 1. PHOTOS / MEDIA GALLERY APP */}
          {activeApp === 'photos' && (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80">
                <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                  <Camera size={15} className="text-pink-400" />
                  <span>{branding.gallery_app_name || 'Photo Vault'}</span>
                </h4>
                <span className="text-[11px] font-mono text-gray-400 font-medium">
                  {filteredGallery.length} / {mediaGallery.length} Items
                </span>
              </div>

              {/* Category Filter Pills & Contact Dropdown */}
              <div className="space-y-1.5">
                <div className="grid grid-cols-4 gap-1.5 pb-0.5">
                  {[
                    { id: 'all', label: 'All' },
                    { id: 'photo', label: '📸 Photos' },
                    { id: 'intimate', label: '🔥 Intimate' },
                    { id: 'video', label: '🎥 Videos' },
                  ].map(cat => (
                    <button
                      key={cat.id}
                      type="button"
                      onClick={() => setPhotoCategory(cat.id)}
                      className={`py-1.5 rounded-xl text-[11px] font-bold transition-colors text-center border cursor-pointer ${
                        photoCategory === cat.id
                          ? 'bg-pink-600/30 text-pink-300 border-pink-500/50 shadow-xs'
                          : 'bg-neutral-900 text-gray-400 border-neutral-800 hover:text-gray-200'
                      }`}
                    >
                      {cat.label}
                    </button>
                  ))}
                </div>

                {galleryContacts.length > 0 && (
                  <select
                    value={photoContactFilter}
                    onChange={e => setPhotoContactFilter(e.target.value)}
                    className="w-full bg-neutral-900 border border-neutral-800 rounded-xl px-2.5 py-1 text-[11px] text-gray-200 focus:outline-none focus:border-pink-500"
                  >
                    <option value="__all__">👤 All Contacts ({mediaGallery.length})</option>
                    {galleryContacts.map(cName => (
                      <option key={cName} value={cName}>👤 {cName}</option>
                    ))}
                  </select>
                )}
              </div>

              {filteredGallery.length === 0 ? (
                <div className="text-center py-14 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-2">
                  <ImageIcon size={32} className="mx-auto opacity-30 text-pink-400" />
                  <p className="text-xs font-medium text-gray-400">No matching media in vault.</p>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    Capture photos, selfies, and videos through narrative choices or DMs to collect digital memories!
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2.5">
                  {filteredGallery.map((media) => {
                    const isVideo = media.media_type?.includes('video');
                    const isIntimate = media.media_type?.includes('nsfw') || media.media_type?.includes('intimate');

                    return (
                      <div
                        key={media.id || media.name}
                        onClick={() => setSelectedPhoto(media)}
                        className="bg-neutral-900/80 border border-neutral-800 hover:border-pink-500/50 rounded-xl p-2.5 space-y-1.5 cursor-pointer transition-all hover:scale-[1.02] shadow-sm relative group overflow-hidden"
                      >
                        <div className="h-24 rounded-lg bg-neutral-950 border border-neutral-800/80 flex flex-col items-center justify-center relative overflow-hidden text-center p-1.5">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center mb-1 ${
                            isIntimate
                              ? 'bg-pink-950/60 text-pink-400'
                              : isVideo
                                ? 'bg-cyan-950/60 text-cyan-400'
                                : 'bg-purple-950/60 text-purple-400'
                          }`}>
                            {isVideo ? <Video size={16} /> : <Camera size={16} />}
                          </div>
                          <span className="text-[10px] font-semibold text-gray-300 truncate max-w-full">
                            {media.contact_name}
                          </span>
                          {isIntimate && (
                            <span className="absolute top-1 right-1 text-[8px] px-1 bg-red-950/80 text-red-300 rounded border border-red-800 font-bold">
                              18+
                            </span>
                          )}
                        </div>

                        <div className="min-w-0">
                          <span className="text-[10px] text-gray-400 truncate block">
                            {media.caption || media.name}
                          </span>
                          <span className="text-[9px] font-mono text-gray-500 block">
                            {formatTimestamp(media.timestamp)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* 2. DMs & APPOINTMENTS APP */}
          {activeApp === 'dms' && (
            <div className="flex-1 flex flex-col h-full min-h-0">
              {/* Active Chat Thread */}
              {activeChatNpc ? (
                <div className="flex-1 flex flex-col h-full min-h-0 space-y-2">
                  {/* Single Clean Chat Header */}
                  <div className="flex items-center justify-between pb-2 border-b border-neutral-800/80 shrink-0">
                    <button
                      type="button"
                      onClick={() => { setDmOutcomeBanner(null); closeChat(); }}
                      className="p-1 rounded-full text-cyan-400 hover:text-cyan-300 hover:bg-neutral-800/80 transition-colors flex items-center gap-0.5 text-xs font-semibold cursor-pointer"
                    >
                      <ChevronLeft size={16} />
                      <span>DMs</span>
                    </button>
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-6 h-6 rounded-full bg-cyan-950 border border-cyan-800/60 flex items-center justify-center text-cyan-300 font-bold text-[10px] shrink-0">
                        <User size={12} />
                      </div>
                      <span className="font-bold text-xs text-gray-100 truncate">{activeChatNpc}</span>
                    </div>
                    <div className="w-8" />
                  </div>

                  {/* DM Reply Outcome Banner */}
                  {dmOutcomeBanner && (
                    <div className="bg-neutral-950/90 border border-cyan-700/50 rounded-xl p-2 text-[10px] space-y-1 shrink-0">
                      <div className="flex items-center justify-between">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {dmOutcomeBanner.check && (
                            <span className="px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-700/50 font-mono font-bold">
                              🎲 {dmOutcomeBanner.check.stat || 'CHA'}: {dmOutcomeBanner.check.tier_label || dmOutcomeBanner.check.tier}
                            </span>
                          )}
                          {dmOutcomeBanner.affinity_delta !== undefined && dmOutcomeBanner.affinity_delta !== 0 && (
                            <span className={`px-1.5 py-0.5 rounded font-mono font-bold ${
                              dmOutcomeBanner.affinity_delta > 0
                                ? 'bg-pink-950/60 text-pink-300 border border-pink-700/50'
                                : 'bg-red-950/60 text-red-300 border border-red-700/50'
                            }`}>
                              {dmOutcomeBanner.affinity_delta > 0 ? `+${dmOutcomeBanner.affinity_delta}` : dmOutcomeBanner.affinity_delta} Affinity
                            </span>
                          )}
                        </div>
                        <button onClick={() => setDmOutcomeBanner(null)} className="text-gray-500 hover:text-gray-300">✕</button>
                      </div>
                      {dmOutcomeBanner.rendezvous_location && (
                        <div className="text-amber-300">📍 Meetup Scheduled: <strong>{dmOutcomeBanner.rendezvous_location}</strong></div>
                      )}
                      {dmOutcomeBanner.media_dropped && (
                        <div className="text-pink-300">📸 Media Received: <strong>{dmOutcomeBanner.media_dropped.name || 'Saved to Photo Vault!'}</strong></div>
                      )}
                    </div>
                  )}

                  {/* Messages Bubble Canvas - Edge to Edge */}
                  <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2 py-1 pr-1 min-h-0">
                    {loadingChat ? (
                      <p className="text-[11px] text-gray-500 italic text-center py-8">Loading history...</p>
                    ) : chatMessages.length === 0 ? (
                      <p className="text-[11px] text-gray-500 italic text-center py-8">
                        Pick a message topic below to text {activeChatNpc}!
                      </p>
                    ) : (
                      chatMessages.map((msg, idx) => {
                        const isPlayer = msg.sender === 'player' || msg.sender === 'Player' || msg.sender === 'You';
                        return (
                          <div
                            key={msg.id || idx}
                            className={`flex flex-col ${isPlayer ? 'items-end' : 'items-start'}`}
                          >
                            <div className={`max-w-[85%] rounded-2xl px-3 py-1.5 text-xs ${
                              isPlayer
                                ? 'bg-cyan-600 text-white rounded-tr-none'
                                : 'bg-neutral-800 text-gray-200 rounded-tl-none border border-neutral-700/50'
                            }`}>
                              <p className="leading-snug whitespace-pre-line">{msg.message}</p>
                            </div>
                            <span className="text-[9px] font-mono text-gray-500 mt-0.5 px-1">
                              {formatTimestamp(msg.timestamp)}
                            </span>
                          </div>
                        );
                      })
                    )}
                    {sendingChat && (
                      <div className="flex items-start">
                        <div className="bg-neutral-800 text-cyan-300 rounded-2xl rounded-tl-none px-3 py-1.5 text-[11px] animate-pulse border border-neutral-700/50">
                          Typing reply...
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 1-Click Intent Action Grid: 4 Columns x 2 Rows, NO SCROLLBAR, NEVER CUT OFF */}
                  {(() => {
                    const isMeetupAccepted = dailyLimits?.meetup?.status === 'accepted';
                    const flirtLocked = !!(dailyLimits?.flirt?.locked || (dailyLimits?.flirt?.used >= 3));
                    const meetupLocked = !!(dailyLimits?.meetup?.locked || (isMeetupAccepted ? ((dailyLimits?.meetup?.relocations_left ?? 2) <= 0) : ((dailyLimits?.meetup?.used ?? 0) >= 1)));
                    const rumorLocked = !!(dailyLimits?.rumor?.locked || ((dailyLimits?.rumor?.used ?? 0) >= 1));
                    const photoLocked = !!(dailyLimits?.photo?.locked || ((dailyLimits?.photo?.used ?? 0) >= 3));
                    const spicyLocked = !!(dailyLimits?.spicy?.locked || ((dailyLimits?.spicy?.used ?? 0) >= 3));

                    const intentOptions = [
                      {
                        id: 'chat',
                        label: 'Chat',
                        icon: '💬',
                        badge: '∞',
                        locked: false,
                        disabled: sendingChat,
                        color: 'hover:border-cyan-500/50 hover:bg-cyan-950/40 text-cyan-200',
                        title: 'Send a friendly chat message'
                      },
                      {
                        id: 'flirt',
                        label: 'Flirt',
                        icon: '💕',
                        badge: dailyLimits ? (flirtLocked ? '🔒' : `${Math.max(0, 3 - (dailyLimits?.flirt?.used ?? 0))}/3`) : '3/3',
                        locked: flirtLocked,
                        disabled: sendingChat || flirtLocked,
                        color: 'hover:border-pink-500/50 hover:bg-pink-950/40 text-pink-200',
                        title: 'Flirt with contact (3 attempts/day)'
                      },
                      {
                        id: 'meetup',
                        label: isMeetupAccepted ? 'Move' : 'Meetup',
                        icon: '📍',
                        badge: dailyLimits ? (isMeetupAccepted ? (meetupLocked ? '🔒' : `${dailyLimits?.meetup?.relocations_left ?? 2} left`) : (meetupLocked ? '🔒' : '1/1')) : '1/1',
                        locked: meetupLocked,
                        disabled: sendingChat || meetupLocked,
                        color: 'hover:border-amber-500/50 hover:bg-amber-950/40 text-amber-200',
                        title: isMeetupAccepted ? 'Relocate meetup spot (up to 2 times)' : 'Propose to meet up (1 attempt/day)'
                      },
                      {
                        id: 'rumor',
                        label: 'Rumor',
                        icon: '🕵️',
                        badge: dailyLimits ? (rumorLocked ? '🔒' : '1/1') : '1/1',
                        locked: rumorLocked,
                        disabled: sendingChat || rumorLocked,
                        color: 'hover:border-emerald-500/50 hover:bg-emerald-950/40 text-emerald-200',
                        title: 'Ask for rumors and gossip (1 attempt/day)'
                      },
                      {
                        id: 'photo_ask',
                        label: 'Ask Pic',
                        icon: '📸',
                        badge: dailyLimits ? (photoLocked ? '🔒' : `${Math.max(0, 3 - (dailyLimits?.photo?.used ?? 0))}/3`) : '3/3',
                        locked: photoLocked,
                        disabled: sendingChat || photoLocked,
                        color: 'hover:border-purple-500/50 hover:bg-purple-950/40 text-purple-200',
                        title: 'Ask contact for a casual photo (shared 3/day)'
                      },
                      {
                        id: 'photo_send',
                        label: 'Send Pic',
                        icon: '📤',
                        badge: dailyLimits ? (photoLocked ? '🔒' : `${Math.max(0, 3 - (dailyLimits?.photo?.used ?? 0))}/3`) : '3/3',
                        locked: photoLocked,
                        disabled: sendingChat || photoLocked,
                        color: 'hover:border-teal-500/50 hover:bg-teal-950/40 text-teal-200',
                        title: 'Send contact a casual photo (shared 3/day)'
                      },
                      {
                        id: 'spicy_ask',
                        label: 'Ask Spicy',
                        icon: '🔥',
                        badge: dailyLimits ? (spicyLocked ? '🔒' : `${Math.max(0, 3 - (dailyLimits?.spicy?.used ?? 0))}/3`) : '3/3',
                        locked: spicyLocked,
                        disabled: sendingChat || spicyLocked,
                        color: 'hover:border-rose-500/50 hover:bg-rose-950/40 text-rose-200',
                        title: 'Ask contact for a spicy photo (shared 3/day)'
                      },
                      {
                        id: 'spicy_send',
                        label: 'Send Spicy',
                        icon: '💋',
                        badge: dailyLimits ? (spicyLocked ? '🔒' : `${Math.max(0, 3 - (dailyLimits?.spicy?.used ?? 0))}/3`) : '3/3',
                        locked: spicyLocked,
                        disabled: sendingChat || spicyLocked,
                        color: 'hover:border-red-500/50 hover:bg-red-950/40 text-red-200',
                        title: 'Send contact a spicy photo of yourself (shared 3/day)'
                      },
                    ];

                    return (
                      <div className="grid grid-cols-4 gap-1.5 pt-2 border-t border-neutral-800/80 shrink-0">
                        {intentOptions.map(opt => (
                          <button
                            key={opt.id}
                            type="button"
                            disabled={opt.disabled}
                            onClick={() => handleInstantIntentSend(opt.id)}
                            className={`flex flex-col items-center justify-center py-1.5 px-1 rounded-xl transition-all cursor-pointer select-none active:scale-95 border shadow-xs ${
                              opt.disabled
                                ? 'opacity-40 cursor-not-allowed bg-neutral-900/40 border-neutral-800/40 text-neutral-500'
                                : selectedIntent === opt.id
                                  ? 'bg-cyan-600/30 text-cyan-100 border-cyan-400 ring-1 ring-cyan-500/40 shadow-sm'
                                  : `bg-neutral-900/95 border-neutral-800/90 ${opt.color}`
                            }`}
                            title={opt.title}
                          >
                            <div className="flex items-center gap-1 leading-tight">
                              <span className="text-xs shrink-0">{opt.icon}</span>
                              <span className="text-[10px] font-bold truncate">{opt.label}</span>
                            </div>
                            {opt.badge && (
                              <span className={`text-[8px] font-mono leading-none mt-0.5 px-1 rounded ${
                                opt.locked ? 'text-red-400/90 bg-red-950/40' : 'text-neutral-400'
                              }`}>
                                {opt.badge}
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    );
                  })()}

                  {/* Custom Message Composer */}
                  <form onSubmit={handleSendDm} className="flex items-center gap-2 pt-1.5 shrink-0">
                    <input
                      type="text"
                      value={dmInput}
                      onChange={(e) => setDmInput(e.target.value)}
                      disabled={sendingChat}
                      placeholder={`Custom message to ${activeChatNpc}...`}
                      className="flex-1 bg-neutral-900 border border-neutral-800 focus:border-cyan-500 rounded-xl px-3.5 py-2.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none disabled:opacity-50 transition-colors"
                    />
                    <button
                      type="submit"
                      disabled={!dmInput.trim() || sendingChat}
                      className="p-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-40 transition-colors cursor-pointer shrink-0 shadow-sm"
                      title="Send Custom Message"
                    >
                      <Send size={16} />
                    </button>
                  </form>
                </div>
              ) : (
                <div className="space-y-3 flex-1 flex flex-col min-h-0">
                  {/* Single Clean Directory Header */}
                  <div className="flex items-center justify-between pb-2 border-b border-neutral-800/80 shrink-0">
                    <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                      <MessageSquare size={15} className="text-cyan-400" />
                      <span>{branding.dm_app_name || 'Messages'}</span>
                    </h4>
                    {appointments.length > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 bg-amber-500/20 text-amber-300 rounded-full border border-amber-500/40">
                        {appointments.length} Rendezvous
                      </span>
                    )}
                  </div>

                  {/* Pending Appointments Banner */}
                  {appointments.length > 0 && (
                    <div className="space-y-1.5 shrink-0">
                      <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider flex items-center gap-1">
                        <Calendar size={11} />
                        <span>Scheduled Meetups</span>
                      </span>
                      {appointments.map((appt, i) => (
                        <div
                          key={appt.id || i}
                          className="bg-amber-950/30 border border-amber-600/40 rounded-xl p-2.5 space-y-1"
                        >
                          <div className="flex justify-between items-center">
                            <span className="font-bold text-xs text-amber-200">{appt.npc_name}</span>
                            <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded uppercase font-bold border ${
                              appt.status === 'arrived'
                                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
                                : 'bg-amber-900/60 text-amber-300 border-amber-700/60'
                            }`}>
                              {appt.status === 'arrived' ? 'Arrived' : 'Pending'}
                            </span>
                          </div>
                          <div className="flex items-center gap-1 text-[11px] text-gray-300">
                            <MapPin size={11} className="text-amber-400 shrink-0" />
                            <span>Rendezvous: <strong>{appt.rendezvous_location}</strong></span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Contacts List */}
                  <div className="space-y-2 flex-1 overflow-y-auto custom-scrollbar pr-0.5 min-h-0">
                    <span className="text-[10px] uppercase font-bold text-gray-500 tracking-wider block">
                      Contacts ({dmDirectory.length})
                    </span>
                    {dmDirectory.length === 0 ? (
                      <div className="text-center py-10 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
                        <MessageSquare size={24} className="mx-auto opacity-30 text-cyan-400 mb-1" />
                        <p className="text-xs">No contacts discovered yet.</p>
                        <p className="text-[10px] text-gray-500 mt-1">
                          Meet characters in the story to unlock their contact numbers!
                        </p>
                      </div>
                    ) : (
                      dmDirectory.map((c) => (
                        <div
                          key={c.npc_id}
                          onClick={() => loadChatMessages(c.npc_id)}
                          className="bg-neutral-900/60 border border-neutral-800 hover:border-cyan-500/50 rounded-xl p-2.5 flex items-center justify-between cursor-pointer transition-colors"
                        >
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div className="w-8 h-8 rounded-full bg-cyan-950/60 border border-cyan-800/60 flex items-center justify-center text-cyan-300 font-bold text-xs shrink-0">
                              <User size={14} />
                            </div>
                            <div className="min-w-0">
                              <span className="font-semibold text-xs text-gray-200 block truncate">{c.name}</span>
                              <span className="text-[10px] text-gray-400 block truncate">{c.role}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            {c.score !== null && (
                              <span className="text-[10px] font-mono text-pink-400 flex items-center gap-0.5">
                                <Heart size={10} /> {c.score}
                              </span>
                            )}
                            <ChevronLeft size={14} className="text-gray-500 rotate-180" />
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 3. FEED / GOSSIP NET & PEERPULSE SOCIAL GRAPH APP */}
          {activeApp === 'feed' && (
            <div className="space-y-2.5">
              {/* Header + Rumor Charges */}
              <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80">
                <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                  <Rss size={15} className="text-purple-400" />
                  <span>{branding.feed_app_name || 'NetWire Feed'}</span>
                </h4>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-950/50 text-purple-300 border border-purple-700/50 font-semibold">
                  ⚡ {socialState?.charges ?? 3}/3 Rumors
                </span>
              </div>

              {/* Sub-view Switcher: Timeline vs PeerPulse People Discovery */}
              <div className="flex bg-neutral-900 p-1 rounded-xl border border-neutral-800 gap-1">
                <button
                  onClick={() => setFeedSubTab('timeline')}
                  className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                    feedSubTab === 'timeline'
                      ? 'bg-purple-600/30 text-purple-200 border border-purple-500/50'
                      : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  <Rss size={12} />
                  <span>Timeline & Rumors</span>
                </button>
                <button
                  onClick={() => setFeedSubTab('peerpulse')}
                  className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                    feedSubTab === 'peerpulse'
                      ? 'bg-cyan-600/30 text-cyan-200 border border-cyan-500/50'
                      : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  <Users size={12} />
                  <span>PeerPulse Graph</span>
                </button>
              </div>

              {/* SUB-VIEW A: TIMELINE & SCOUR RUMORS */}
              {feedSubTab === 'timeline' && (
                <div className="space-y-2.5">
                  {/* Action Bar */}
                  <div className="flex items-center gap-1.5">
                    <button
                      disabled={feedBusy || (socialState?.charges ?? 3) <= 0}
                      onClick={handleScourRumor}
                      className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2.5 rounded-xl text-[11px] font-bold border transition-all ${
                        (socialState?.charges ?? 3) > 0
                          ? 'bg-purple-950/60 hover:bg-purple-900/70 text-purple-200 border-purple-600/50'
                          : 'bg-neutral-900 text-gray-600 border-neutral-800 cursor-not-allowed'
                      }`}
                    >
                      <Sparkles size={12} className="text-purple-400" />
                      <span>{feedBusy ? 'Investigating...' : `Scour Rumors (${socialState?.charges ?? 3}/3)`}</span>
                    </button>

                    <button
                      disabled={feedBusy}
                      onClick={handleRefreshFeed}
                      className="p-1.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-gray-300 border border-neutral-800 transition-colors"
                      title="Refresh Timeline"
                    >
                      <RefreshCw size={13} className={feedBusy ? 'animate-spin text-purple-400' : ''} />
                    </button>
                  </div>

                  {/* Rumor Scour Result Banner */}
                  {feedBanner && (
                    <div className={`p-2.5 rounded-xl text-xs border space-y-1 ${
                      feedBanner.type === 'ok'
                        ? 'bg-emerald-950/50 border-emerald-700/60 text-emerald-200'
                        : feedBanner.type === 'error'
                          ? 'bg-red-950/50 border-red-800/60 text-red-200'
                          : 'bg-amber-950/40 border-amber-700/50 text-amber-200'
                    }`}>
                      {feedBanner.title && (
                        <div className="font-bold text-[11px] flex justify-between items-center">
                          <span>{feedBanner.title}</span>
                          <button onClick={() => setFeedBanner(null)} className="text-[10px] opacity-70">✕</button>
                        </div>
                      )}
                      <p className="text-[11px] leading-snug">{feedBanner.text}</p>
                    </div>
                  )}

                  {gossipFeed.length === 0 ? (
                    <div className="text-center py-12 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
                      <Rss size={28} className="mx-auto opacity-30 text-purple-400 mb-1" />
                      <p className="text-xs">Feed is quiet right now.</p>
                      <p className="text-[10px] text-gray-500 mt-1">Click Refresh or Scour Rumors to pull live whispers.</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {gossipFeed.map((post, idx) => {
                        const isLead = post.is_lead || post.tag === '#VerifiedLead';
                        const isNoise = post.is_noise || post.tag === '#CampusChat' || post.tag === '#Noise';
                        return (
                          <div
                            key={post.id || idx}
                            className={`rounded-xl p-3 space-y-1.5 transition-all ${
                              isLead
                                ? 'bg-emerald-950/40 border border-emerald-500/60 shadow-[0_0_15px_rgba(16,185,129,0.15)] ring-1 ring-emerald-500/30'
                                : isNoise
                                ? 'bg-neutral-900/80 border border-neutral-700/60'
                                : 'bg-neutral-900/70 border border-neutral-800'
                            }`}
                          >
                            <div className="flex justify-between items-start">
                              <div className="flex items-center gap-2">
                                <div className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs ${
                                  isLead
                                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                    : 'bg-purple-900/30 text-purple-300 border border-purple-700/40'
                                }`}>
                                  {isLead ? '⚡' : (post.author_name ? post.author_name[0] : '?')}
                                </div>
                                <div>
                                  <div className="flex items-center gap-1.5">
                                    <span className={`font-bold text-xs ${isLead ? 'text-emerald-300' : 'text-gray-200'}`}>
                                      {post.author_name}
                                    </span>
                                    {isLead && (
                                      <span className="text-[9px] font-mono px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold">
                                        VERIFIED LEAD
                                      </span>
                                    )}
                                  </div>
                                  {post.author_handle && (
                                    <span className="text-[10px] text-purple-400 font-mono block">
                                      {post.author_handle.startsWith('@') ? post.author_handle : `@${post.author_handle}`}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <div className="flex items-center gap-1.5">
                                {post.tag && (
                                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                                    isLead
                                      ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 font-semibold'
                                      : 'bg-purple-950/60 text-purple-300 border border-purple-800/40'
                                  }`}>
                                    {post.tag}
                                  </span>
                                )}
                                {post.time_ago && (
                                  <span className="text-[9px] font-mono text-gray-500">{post.time_ago}</span>
                                )}
                              </div>
                            </div>

                            <p className={`text-xs leading-snug ${isLead ? 'text-emerald-100 font-medium' : 'text-gray-300'}`}>
                              {post.content}
                            </p>

                            <div className="flex items-center justify-between pt-1">
                              {post.clue_hook ? (
                                <div className="text-[10px] text-cyan-300 flex items-center gap-1 font-medium bg-cyan-950/40 px-2 py-0.5 rounded-lg border border-cyan-800/40">
                                  <Sparkles size={11} className="text-cyan-400" />
                                  <span>Lead: {post.clue_hook}</span>
                                </div>
                              ) : <span />}
                              {post.likes !== undefined && (
                                <span className="text-[10px] font-mono text-pink-400 flex items-center gap-1">
                                  <Heart size={10} /> {post.likes}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* SUB-VIEW B: PEERPULSE PEOPLE DISCOVERY & FRIEND REQUESTS */}
              {feedSubTab === 'peerpulse' && (
                <div className="space-y-3">
                  {/* Search & Suggested Peer Controls */}
                  <div className="flex gap-1.5">
                    <div className="relative flex-1">
                      <Search size={12} className="absolute left-2.5 top-2 text-gray-500" />
                      <input
                        type="text"
                        value={peerQuery}
                        onChange={(e) => setPeerQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleDiscoverPeer(peerQuery)}
                        placeholder="Search name or @handle..."
                        className="w-full bg-neutral-900 border border-neutral-800 pl-7 pr-2.5 py-1.5 rounded-xl text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                    <button
                      disabled={peerBusy}
                      onClick={() => handleDiscoverPeer(peerQuery)}
                      className="px-2.5 py-1.5 rounded-xl bg-cyan-600/30 hover:bg-cyan-600/40 text-cyan-200 border border-cyan-500/50 text-[11px] font-bold transition-colors shrink-0"
                    >
                      Lookup
                    </button>
                  </div>

                  <button
                    disabled={peerBusy}
                    onClick={() => handleDiscoverPeer('')}
                    className="w-full py-1.5 px-3 rounded-xl bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-xs font-semibold text-cyan-300 flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <Sparkles size={12} />
                    <span>{peerBusy ? 'Scanning Directory...' : 'Discover Suggested Peer'}</span>
                  </button>

                  {peerFeedback && (
                    <div className={`p-2.5 rounded-xl text-xs border ${
                      peerFeedback.type === 'ok'
                        ? 'bg-emerald-950/50 border-emerald-700/60 text-emerald-200'
                        : peerFeedback.type === 'error'
                          ? 'bg-red-950/50 border-red-800/60 text-red-200'
                          : 'bg-amber-950/50 border-amber-700/60 text-amber-200'
                    }`}>
                      <p className="text-[11px] leading-snug">{peerFeedback.text}</p>
                    </div>
                  )}

                  {/* Discovered Profile Card */}
                  {peerProfile ? (
                    <div className="space-y-2">
                      <button
                        onClick={() => { setPeerProfile(null); setPeerFeedback(null); }}
                        className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-semibold cursor-pointer transition-colors"
                      >
                        <ChevronLeft size={14} />
                        <span>Back to Suggestions</span>
                      </button>

                      <div className="bg-neutral-900/90 border border-neutral-800 rounded-2xl p-3.5 space-y-2.5">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h5 className="font-bold text-xs text-gray-100">{peerProfile.name}</h5>
                            <span className="text-[10px] font-mono text-cyan-400 block">{peerProfile.handle}</span>
                          </div>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-neutral-800 text-gray-300 border border-neutral-700 font-semibold">
                            {peerProfile.grade || peerProfile.role}
                          </span>
                        </div>

                        {peerProfile.personality && (
                          <p className="text-[11px] text-gray-300 leading-snug italic bg-neutral-950/80 p-2.5 rounded-xl border border-neutral-800/80">
                            "{peerProfile.personality}"
                          </p>
                        )}

                        <div className="flex flex-wrap gap-1.5 text-[10px]">
                          {peerProfile.role && (
                            <span className="px-2 py-0.5 rounded-lg bg-neutral-950 text-gray-300 border border-neutral-800">
                              Role: {peerProfile.role}
                            </span>
                          )}
                          {peerProfile.club && peerProfile.club !== 'None' && (
                            <span className="px-2 py-0.5 rounded-lg bg-purple-950/50 text-purple-300 border border-purple-800/50">
                              Club: {peerProfile.club}
                            </span>
                          )}
                          {peerProfile.facility && (
                            <span className="px-2 py-0.5 rounded-lg bg-neutral-950 text-gray-400 border border-neutral-800">
                              📍 {peerProfile.facility}
                            </span>
                          )}
                        </div>

                        {/* Social Graph Ties & Mutual Friends */}
                        {(peerProfile.is_sibling_friend || peerProfile.shared_club || (peerProfile.mutual_friends && peerProfile.mutual_friends.length > 0)) && (
                          <div className="pt-1.5 border-t border-neutral-800 space-y-1 text-[10px]">
                            <span className="font-bold uppercase tracking-wider text-cyan-400 block">
                              Social Graph Synergies (CHA Bonus)
                            </span>
                            {peerProfile.is_sibling_friend && (
                              <p className="text-emerald-300">• +4 CHA: Sibling of your contact {peerProfile.sibling_name}</p>
                            )}
                            {peerProfile.shared_club && (
                              <p className="text-purple-300">• +2 CHA: Shared affiliation ({peerProfile.shared_club})</p>
                            )}
                            {peerProfile.mutual_friends?.length > 0 && (
                              <p className="text-cyan-300">
                                • Mutual Friends: {peerProfile.mutual_friends.join(', ')}
                              </p>
                            )}
                          </div>
                        )}

                        {/* Friend Request Action */}
                        <div className="pt-1">
                          {peerProfile.is_already_contact ? (
                            <button
                              onClick={() => {
                                setActiveApp('dms');
                                loadChatMessages(peerProfile.npc_id || peerProfile.name);
                              }}
                              className="w-full py-2 rounded-xl bg-emerald-950/60 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-700/60 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
                            >
                              <MessageSquare size={13} />
                              <span>Connected — Open Direct Message</span>
                            </button>
                          ) : peerProfile.is_faculty ? (
                            <div className="text-center py-1.5 px-2 rounded-xl bg-neutral-950 border border-neutral-800 text-[10px] text-gray-500">
                              🔒 Faculty/Staff accounts cannot be added to student friend circles
                            </div>
                          ) : (
                            <button
                              disabled={peerBusy || (peerProfile.cooldown_turns_left || 0) > 0}
                              onClick={() => handleSendFriendReq(peerProfile)}
                              className={`w-full py-2 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 border transition-all ${
                                (peerProfile.cooldown_turns_left || 0) > 0
                                  ? 'bg-neutral-950 text-gray-600 border-neutral-800 cursor-not-allowed'
                                  : 'bg-cyan-600/30 hover:bg-cyan-600/45 text-cyan-200 border-cyan-500/60'
                              }`}
                            >
                              <UserPlus size={13} />
                              <span>
                                {(peerProfile.cooldown_turns_left || 0) > 0
                                  ? `Cooldown (${peerProfile.cooldown_turns_left} turns left)`
                                  : 'Send Friend Request (CHA Check)'}
                              </span>
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between pb-1 border-b border-neutral-800">
                        <div>
                          <h5 className="font-bold text-xs text-gray-200 flex items-center gap-1.5">
                            <Users size={14} className="text-cyan-400" />
                            <span>Suggested Peers & Classmates</span>
                          </h5>
                          <p className="text-[10px] text-gray-500">
                            Classmates and mutual peers eligible for friend requests.
                          </p>
                        </div>
                        {suggestedPeers.length > 0 && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950/60 text-cyan-300 border border-cyan-800/50">
                            {suggestedPeers.length} eligible
                          </span>
                        )}
                      </div>

                      {suggestedPeers.length === 0 ? (
                        <div className="text-center py-10 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-1">
                          <Users size={26} className="mx-auto opacity-30 text-cyan-400" />
                          <p className="text-xs text-gray-400">Discover Peers & Mutual Connections</p>
                          <p className="text-[10px] text-gray-500">
                            Search by name or click "Discover Suggested Peer" to view social profiles and send Friend Requests.
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-2 max-h-[360px] overflow-y-auto pr-0.5 custom-scrollbar">
                          {suggestedPeers.map((peer, idx) => {
                            const isConnected = peer.is_already_contact || contacts.some(c => (c.name === peer.name || c.id === peer.npc_id));
                            const cooldownLeft = peer.cooldown_turns_left || 0;
                            return (
                              <div
                                key={peer.handle || peer.name || idx}
                                className="bg-neutral-900/90 hover:bg-neutral-900 border border-neutral-800 hover:border-neutral-700/80 rounded-2xl p-3 transition-colors space-y-2"
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <div className="flex items-center gap-2.5 min-w-0">
                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-900/50 to-blue-900/50 border border-cyan-700/40 flex items-center justify-center font-bold text-xs text-cyan-200 shrink-0">
                                      {peer.name ? peer.name[0] : '?'}
                                    </div>
                                    <div className="min-w-0">
                                      <h6 className="font-bold text-xs text-gray-100 truncate">{peer.name}</h6>
                                      <span className="text-[10px] font-mono text-cyan-400/90 block truncate">{peer.handle}</span>
                                    </div>
                                  </div>
                                  <span className="text-[9px] px-2 py-0.5 rounded-full bg-neutral-800 text-gray-300 border border-neutral-700 font-semibold shrink-0">
                                    {peer.grade || peer.role}
                                  </span>
                                </div>

                                {peer.personality && (
                                  <p className="text-[10px] text-gray-400 italic line-clamp-1">
                                    "{peer.personality}"
                                  </p>
                                )}

                                {/* Synergies */}
                                <div className="flex flex-wrap gap-1 text-[9px]">
                                  {peer.shared_club && (
                                    <span className="px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/50">
                                      ★ Shared: {peer.shared_club} (+2 CHA)
                                    </span>
                                  )}
                                  {peer.is_sibling_friend && (
                                    <span className="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/50">
                                      ★ Sibling Contact (+4 CHA)
                                    </span>
                                  )}
                                  {peer.mutual_friends?.length > 0 && (
                                    <span className="px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800/50">
                                      ★ {peer.mutual_friends.length} Mutual{peer.mutual_friends.length > 1 ? 's' : ''}
                                    </span>
                                  )}
                                </div>

                                {/* Action Buttons */}
                                <div className="flex items-center gap-1.5 pt-1">
                                  <button
                                    onClick={() => {
                                      setPeerProfile(peer);
                                      setPeerFeedback(null);
                                    }}
                                    className="flex-1 py-1.5 rounded-xl bg-neutral-800 hover:bg-neutral-700/80 text-gray-300 border border-neutral-700 text-[11px] font-medium transition-colors"
                                  >
                                    View Bio
                                  </button>
                                  {isConnected ? (
                                    <button
                                      onClick={() => {
                                        setActiveApp('dms');
                                        loadChatMessages(peer.npc_id || peer.name);
                                      }}
                                      className="flex-1 py-1.5 rounded-xl bg-emerald-950/60 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-700/60 text-[11px] font-bold flex items-center justify-center gap-1 transition-colors"
                                    >
                                      <MessageSquare size={12} />
                                      <span>Message</span>
                                    </button>
                                  ) : (
                                    <button
                                      disabled={peerBusy || cooldownLeft > 0}
                                      onClick={() => handleSendFriendReq(peer)}
                                      className={`flex-1 py-1.5 rounded-xl text-[11px] font-bold flex items-center justify-center gap-1 border transition-all ${
                                        cooldownLeft > 0
                                          ? 'bg-neutral-950 text-gray-600 border-neutral-800 cursor-not-allowed'
                                          : 'bg-cyan-600/30 hover:bg-cyan-600/50 text-cyan-200 border-cyan-500/60'
                                      }`}
                                      title={cooldownLeft > 0 ? `Wait ${cooldownLeft} turns before re-attempting` : 'Send a friend request (CHA check)'}
                                    >
                                      <UserPlus size={12} />
                                      <span>{cooldownLeft > 0 ? `Wait (${cooldownLeft}t)` : 'Add Friend'}</span>
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}


          {/* 4. E-SHOP / DELIVERY APP */}
          {activeApp === 'shop' && (
            <div className="flex flex-col h-full space-y-2.5 min-h-0">
              <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80 shrink-0">
                <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                  <ShoppingBag size={15} className="text-amber-400" />
                  <span>{shopData?.flavor_name || branding.shop_app_name || 'E-Shop Delivery'}</span>
                </h4>
                {shopData && (
                  <div className="flex items-center gap-1.5">
                    {shopData.discount_pct > 0 && (
                      <span className="text-[10px] font-mono text-emerald-300 bg-emerald-950/50 px-1.5 py-0.5 rounded-full border border-emerald-700/50 font-bold">
                        -{shopData.discount_pct}% Off
                      </span>
                    )}
                    <span className="text-[11px] font-mono text-amber-300 bg-amber-950/40 px-2 py-0.5 rounded-full border border-amber-700/40 font-semibold">
                      {shopData.currency_emoji || '💰'} {shopData.gold ?? 0} {shopData.currency_name || 'Gold'}
                    </span>
                  </div>
                )}
              </div>

              {shopData?.greeting && (
                <p className="text-[10px] text-gray-400 italic bg-neutral-900/60 px-2.5 py-1.5 rounded-xl border border-neutral-800 shrink-0 line-clamp-2">
                  "{shopData.greeting}"
                </p>
              )}

              {shopFeedback && (
                <div className={`px-2.5 py-1.5 rounded-xl text-xs border flex items-center justify-between shrink-0 ${
                  shopFeedback.type === 'error'
                    ? 'bg-red-950/60 border-red-800/60 text-red-200'
                    : 'bg-emerald-950/60 border-emerald-800/60 text-emerald-200'
                }`}>
                  <span className="text-[11px]">{shopFeedback.text}</span>
                  <button
                    onClick={() => setShopFeedback(null)}
                    className="text-[10px] opacity-70 hover:opacity-100 ml-2"
                  >
                    ✕
                  </button>
                </div>
              )}

              {loadingShop ? (
                <div className="text-center py-16 text-gray-500 italic space-y-2">
                  <RefreshCw size={20} className="animate-spin text-amber-400 mx-auto" />
                  <p className="text-xs">Connecting to courier network...</p>
                </div>
              ) : !shopData || !shopData.inventory || shopData.inventory.length === 0 ? (
                <div className="text-center py-14 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
                  <ShoppingBag size={28} className="mx-auto opacity-30 text-amber-400 mb-1" />
                  <p className="text-xs">No courier catalog available right now.</p>
                </div>
              ) : (
                <div className="space-y-1.5 overflow-y-auto pr-0.5 flex-1 custom-scrollbar min-h-0">
                  {shopData.inventory.map((item, idx) => {
                    const finalPrice = item.final_price ?? item.price ?? 0;
                    const basePrice = item.base_price ?? item.price ?? finalPrice;
                    const canAfford = (shopData.gold ?? 0) >= finalPrice;
                    return (
                      <div
                        key={item.name || idx}
                        className="flex items-center justify-between gap-2 p-2 bg-neutral-900/80 hover:bg-neutral-900 border border-neutral-800 rounded-xl transition-all"
                      >
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          <div className="w-8 h-8 rounded-lg bg-neutral-800/80 border border-neutral-700/50 flex items-center justify-center text-base shrink-0">
                            {item.emoji || '📦'}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="font-bold text-[11px] text-gray-200 truncate">{item.name}</span>
                              {item.category && (
                                <span className="text-[9px] px-1 py-0.2 rounded bg-neutral-800 text-gray-400 shrink-0 font-mono">
                                  {item.category}
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-gray-400 truncate leading-tight">
                              {item.description || item.effect || 'Courier delivery item'}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <div className="text-right">
                            {basePrice > finalPrice && (
                              <span className="text-[9px] font-mono text-gray-500 line-through block leading-none">
                                {basePrice}
                              </span>
                            )}
                            <span className="text-[11px] font-mono font-bold text-amber-300 leading-tight block">
                              {shopData.currency_emoji || '💰'}{finalPrice}
                            </span>
                          </div>
                          <button
                            disabled={!canAfford || buyingItem === item.name}
                            onClick={() => handleBuyDeliveryItem(item)}
                            className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all shrink-0 ${
                              canAfford
                                ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 active:scale-95 cursor-pointer'
                                : 'bg-neutral-950 text-gray-600 border border-neutral-800 cursor-not-allowed'
                            }`}
                          >
                            {buyingItem === item.name ? '...' : canAfford ? 'Order' : 'Funds'}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}


        {/* 5. CAMPUS REQUESTS / BOUNTIES APP */}
        {activeApp === 'bounties' && (
          <div className="flex flex-col h-full space-y-2.5 min-h-0">
            {/* Header + Subtitle + Refresh */}
            <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80 shrink-0">
              <div>
                <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                  <ShieldAlert size={15} className="text-rose-400" />
                  <span>{branding.bounty_app_name || branding.bounties_app_name || 'Campus Requests'}</span>
                </h4>
                <p className="text-[10px] text-gray-400">
                  {branding.bounty_subtitle || 'Student Bulletin & Faction Gigs'}
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  disabled={generatingBounties}
                  onClick={() => handleRefreshBounties()}
                  className="p-1.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-gray-300 border border-neutral-800 transition-colors cursor-pointer"
                  title="Refresh Bulletin Requests"
                >
                  <RefreshCw size={13} className={generatingBounties ? 'animate-spin text-rose-400' : ''} />
                </button>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-950/50 text-rose-300 border border-rose-700/50 font-semibold">
                  {availableBounties.length} Available
                </span>
              </div>
            </div>

            {/* Sub-tabs: Available vs Active Tasks */}
            <div className="flex bg-neutral-900 p-1 rounded-xl border border-neutral-800 gap-1 shrink-0">
              <button
                onClick={() => setBountySubTab('available')}
                className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                  bountySubTab === 'available'
                    ? 'bg-rose-600/30 text-rose-200 border border-rose-500/50'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                <span>Available Tasks ({availableBounties.length})</span>
              </button>
              <button
                onClick={() => setBountySubTab('active')}
                className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                  bountySubTab === 'active'
                    ? 'bg-amber-600/30 text-amber-200 border border-amber-500/50'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                <span>Active Tasks ({activeBounties.length})</span>
              </button>
            </div>

            {/* Faction Filter Navigation Pills (Available tab only) - Flex Wrap, NO SCROLLBAR */}
            {bountySubTab === 'available' && factionsList.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 pb-0.5 shrink-0">
                <button
                  type="button"
                  onClick={() => setSelectedFactionFilter('all')}
                  className={`px-2.5 py-1 rounded-full text-xs font-bold transition-colors shrink-0 border cursor-pointer ${
                    selectedFactionFilter === 'all'
                      ? 'bg-rose-600/30 text-rose-200 border-rose-500/50'
                      : 'bg-neutral-900 text-gray-400 border-neutral-800 hover:text-gray-200'
                  }`}
                >
                  All ({allAvailableBounties.length})
                </button>
                {factionsList.map(f => (
                  <button
                    key={f.faction_id || f.name}
                    type="button"
                    onClick={() => setSelectedFactionFilter(f.faction_id || f.name)}
                    className={`px-2.5 py-1 rounded-full text-xs font-bold transition-colors shrink-0 border cursor-pointer ${
                      selectedFactionFilter === (f.faction_id || f.name)
                        ? 'bg-purple-600/30 text-purple-200 border-purple-500/50'
                        : 'bg-neutral-900 text-gray-400 border-neutral-800 hover:text-gray-200'
                    }`}
                  >
                    {f.name}
                  </button>
                ))}
              </div>
            )}

            {/* Feedback / Action Banner */}
            {bountyActionBanner && (
              <div className={`p-2.5 rounded-xl text-xs border flex items-center justify-between shrink-0 ${
                bountyActionBanner.type === 'ok'
                  ? 'bg-emerald-950/50 border-emerald-700/60 text-emerald-200'
                  : bountyActionBanner.type === 'warn'
                  ? 'bg-amber-950/50 border-amber-700/60 text-amber-200'
                  : 'bg-red-950/50 border-red-800/60 text-red-200'
              }`}>
                <p className="text-[11px] leading-snug">{bountyActionBanner.text}</p>
                <button onClick={() => setBountyActionBanner(null)} className="text-[10px] opacity-70 ml-2">✕</button>
              </div>
            )}

            {/* Content: Available Tab vs Active Tab */}
            <div className="flex-1 overflow-y-auto custom-scrollbar pr-0.5 min-h-0 space-y-2">
              {bountySubTab === 'available' ? (
                availableBounties.length === 0 ? (
                  <div className="text-center py-12 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-3">
                    <ShieldAlert size={28} className="mx-auto opacity-30 text-rose-400" />
                    <div>
                      <p className="text-xs text-gray-300 font-semibold">
                        {selectedFactionFilter !== 'all' ? 'No faction tasks currently posted' : 'Bulletin is quiet right now'}
                      </p>
                      <p className="text-[10px] text-gray-500 mt-0.5">
                        {selectedFactionFilter !== 'all' ? 'Request contracts directly from this faction.' : 'Generate live procedural requests for your campus.'}
                      </p>
                    </div>
                    <button
                      disabled={generatingBounties}
                      onClick={() => handleRefreshBounties(selectedFactionFilter !== 'all' ? selectedFactionFilter : null)}
                      className="px-3.5 py-1.5 rounded-xl bg-rose-600/30 hover:bg-rose-600/50 text-rose-200 border border-rose-500/40 text-xs font-bold transition-all active:scale-95 cursor-pointer"
                    >
                      {generatingBounties ? 'Generating...' : selectedFactionFilter !== 'all' ? 'Request Faction Tasks' : 'Generate New Requests'}
                    </button>
                  </div>
                ) : (
                  availableBounties.map((bounty, idx) => (
                    <div
                      key={bounty.quest_id || idx}
                      className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-3 space-y-2"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="min-w-0">
                          <span className="font-bold text-xs text-gray-100 block">{bounty.title}</span>
                          <span className="text-[10px] font-mono text-rose-400 block mt-0.5">
                            {bounty.quest_type || 'Campus Request'}
                            {bounty.target_name ? ` • Target: ${bounty.target_name}` : ''}
                          </span>
                        </div>
                        {bounty.status && (
                          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-neutral-800 text-gray-400 border border-neutral-700 shrink-0">
                            {bounty.status}
                          </span>
                        )}
                      </div>

                      <p className="text-[11px] text-gray-300 leading-snug">{bounty.objective || bounty.description}</p>

                      {/* Rewards row */}
                      <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono pt-0.5">
                        {bounty.reward_gold > 0 && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-800/40">
                            💰 {bounty.reward_gold} Gold
                          </span>
                        )}
                        {bounty.reward_xp > 0 && (
                          <span className="px-1.5 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40">
                            ⭐ {bounty.reward_xp} XP
                          </span>
                        )}
                        {bounty.reward_item && (
                          <span className="px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 truncate max-w-[150px]">
                            🎁 {bounty.reward_item}
                          </span>
                        )}
                        {bounty.faction_rep_reward > 0 && (
                          <span className="px-1.5 py-0.5 rounded bg-emerald-950/40 text-emerald-300 border border-emerald-800/40">
                            🏆 +{bounty.faction_rep_reward} Rep
                          </span>
                        )}
                      </div>

                      {/* Action: Accept in phone */}
                      <div className="flex justify-end pt-1">
                        <button
                          onClick={() => handleAcceptBounty(bounty.quest_id, bounty.title)}
                          className="px-3 py-1 rounded-lg text-[11px] font-bold bg-rose-600/30 hover:bg-rose-500/40 text-rose-200 border border-rose-500/50 transition-all active:scale-95 cursor-pointer"
                        >
                          Accept Request
                        </button>
                      </div>
                    </div>
                  ))
                )
              ) : (
                /* Active Tasks Tab */
                activeBounties.length === 0 ? (
                  <div className="text-center py-12 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-1">
                    <ShieldAlert size={28} className="mx-auto opacity-30 text-gray-500" />
                    <p className="text-xs text-gray-300 font-semibold">No active tasks in progress</p>
                    <p className="text-[10px] text-gray-500">
                      Switch to the Available tab and accept requests to track them here.
                    </p>
                  </div>
                ) : (
                  activeBounties.map((quest, idx) => (
                    <div
                      key={quest.quest_id || idx}
                      className="bg-neutral-900/90 border border-amber-700/40 rounded-xl p-3 space-y-2"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div>
                          <span className="font-bold text-xs text-amber-200 block">{quest.title}</span>
                          <span className="text-[10px] font-mono text-gray-400 block mt-0.5">
                            {quest.quest_type}
                            {quest.target_name ? ` • Target: ${quest.target_name}` : ''}
                          </span>
                        </div>
                        <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold shrink-0">
                          ⚡ Active
                        </span>
                      </div>

                      <p className="text-[11px] text-gray-300 leading-snug">{quest.objective}</p>

                      {quest.progress && (
                        <div className="bg-neutral-950/80 p-1.5 rounded-lg border border-neutral-800 text-[10px] font-mono text-cyan-300 flex items-center justify-between">
                          <span>Progress: {quest.progress}</span>
                        </div>
                      )}

                      <div className="flex items-center justify-between pt-1">
                        <div className="flex items-center gap-1.5 text-[10px] font-mono text-gray-400">
                          {quest.reward_gold > 0 && <span>💰 {quest.reward_gold}</span>}
                          {quest.reward_xp > 0 && <span>⭐ {quest.reward_xp} XP</span>}
                        </div>
                        <button
                          onClick={() => handleAbandonBounty(quest.quest_id, quest.title)}
                          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold text-gray-400 hover:text-red-300 hover:bg-red-950/40 border border-neutral-800 hover:border-red-800/60 transition-colors cursor-pointer"
                        >
                          Abandon Task
                        </button>
                      </div>
                    </div>
                  ))
                )
              )}
            </div>
          </div>
        )}

        </div>

        {/* Expanded Photo Preview Overlay */}
        {selectedPhoto && (
          <div className="absolute inset-0 bg-black/95 z-30 flex flex-col p-4">
            <div className="flex justify-between items-center border-b border-neutral-800 pb-2 mb-3">
              <span className="font-bold text-xs text-pink-300 truncate">{selectedPhoto.contact_name}</span>
              <button
                onClick={() => setSelectedPhoto(null)}
                className="p-1 text-gray-400 hover:text-gray-100 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 flex flex-col items-center justify-center p-3 text-center space-y-3 bg-neutral-950 border border-neutral-800 rounded-2xl">
              <div className="w-16 h-16 rounded-full bg-pink-950/60 border border-pink-700/60 flex items-center justify-center text-pink-300">
                {selectedPhoto.media_type?.includes('video') ? <Video size={28} /> : <Camera size={28} />}
              </div>
              <h5 className="font-bold text-sm text-gray-100">{selectedPhoto.name}</h5>
              <p className="text-xs text-gray-300 leading-relaxed max-w-xs italic bg-neutral-900/80 p-3 rounded-xl border border-neutral-800">
                "{selectedPhoto.caption}"
              </p>
              <div className="flex flex-wrap gap-1 justify-center pt-2">
                {selectedPhoto.tags?.map((tag, i) => (
                  <span key={i} className="text-[10px] px-2 py-0.5 bg-neutral-800 text-gray-400 rounded-full font-mono">
                    #{tag}
                  </span>
                ))}
              </div>

              {selectedPhoto.id && (
                <button
                  type="button"
                  disabled={deletingPhoto}
                  onClick={() => handleDeleteMedia(selectedPhoto)}
                  className="mt-3 px-3 py-1.5 rounded-xl bg-red-950/60 hover:bg-red-900/70 text-red-300 border border-red-800/60 text-xs font-bold transition-colors cursor-pointer"
                >
                  {deletingPhoto ? 'Deleting...' : '🗑️ Delete Media'}
                </button>
              )}
            </div>
          </div>
        )}

      {/* Sleek Modern Gesture Navigation Bar (Back, Home Pill, Lock) */}
      <div className="px-5 py-2.5 bg-neutral-950/95 border-t border-neutral-800/70 flex items-center justify-between shrink-0 select-none">
        {/* Back Gesture Button */}
        <button
          type="button"
          onClick={() => {
            if (selectedPhoto) {
              setSelectedPhoto(null);
            } else if (activeApp === 'dms' && activeChatNpc) {
              closeChat();
            } else if (activeApp !== 'home') {
              setActiveApp('home');
            } else {
              onClose();
            }
          }}
          className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold text-gray-400 hover:text-white hover:bg-neutral-800/70 transition-all active:scale-95 cursor-pointer"
          title="Back / Previous Screen"
        >
          <ChevronLeft size={16} />
          <span className="text-[11px]">Back</span>
        </button>

        {/* iOS / Android Style Center Home Pill */}
        <button
          type="button"
          onClick={() => {
            if (activeApp !== 'home' || selectedPhoto || activeChatNpc) {
              setActiveApp('home');
              setSelectedPhoto(null);
              if (closeChat) closeChat();
            } else {
              onClose();
            }
          }}
          className="group py-2 px-6 flex items-center justify-center cursor-pointer focus:outline-none"
          title={activeApp !== 'home' ? "Tap for Home" : "Tap to Lock Phone"}
        >
          <div className="w-28 h-1.5 bg-neutral-600 group-hover:bg-neutral-300 rounded-full transition-all group-active:scale-95 group-hover:h-2" />
        </button>

        {/* Lock / Sleep Gesture Button */}
        <button
          type="button"
          onClick={onClose}
          className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold text-gray-400 hover:text-white hover:bg-neutral-800/70 transition-all active:scale-95 cursor-pointer"
          title="Lock & Sleep Phone"
        >
          <span className="text-[11px]">Lock</span>
          <X size={14} />
        </button>
      </div>
      </div>
    </div>
  );
};

export default PhoneModal;
