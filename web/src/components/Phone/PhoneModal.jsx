import React, { useState, useEffect } from 'react';
import {
  X, Camera, Video, MessageSquare, Rss, Wifi, Battery,
  MapPin, Calendar, Sparkles, ChevronLeft, Send, User, Image as ImageIcon, Heart, ShoppingBag,
  Search, RefreshCw, UserPlus, Users, ShieldAlert
} from 'lucide-react';

const formatTimestamp = (ts) => {
  if (!ts) return 'Just now';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const PhoneModal = ({ isOpen, onClose, phoneHook, session, user, onRefreshInventory, onRefreshCodex, onRefreshCharacter }) => {
  const [activeApp, setActiveApp] = useState('photos'); // 'photos' | 'dms' | 'feed' | 'shop'
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

  const {
    branding, appointments, gossipFeed, mediaGallery, contacts, socialState,
    activeChatNpc, chatMessages, loadingChat, sendingChat,
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

  const handleSendFriendReq = async () => {
    if (!sendFriendRequest || !peerProfile || peerBusy) return;
    setPeerBusy(true);
    setPeerFeedback(null);
    try {
      const res = await sendFriendRequest(peerProfile);
      if (res?.profile) setPeerProfile(res.profile);
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

  if (!isOpen) return null;

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

  const processDmOutcome = (res) => {
    const replyObj = res?.reply && typeof res.reply === 'object' ? res.reply : res;
    if (replyObj && (replyObj.check || replyObj.affinity_delta !== undefined || replyObj.rendezvous_location || replyObj.media_dropped)) {
      setDmOutcomeBanner({
        check: replyObj.check,
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

  const handleQuickSendDm = async () => {
    if (!activeChatNpc || sendingChat) return;
    setDmOutcomeBanner(null);
    try {
      const res = await sendMessage(activeChatNpc, '__auto__', selectedIntent);
      processDmOutcome(res);
      if (onRefreshInventory) onRefreshInventory();
      if (onRefreshCodex) onRefreshCodex();
    } catch {
      // ignore
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 select-none">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/85 backdrop-blur-md transition-opacity"
        onClick={onClose}
      />

      {/* Phone Hardware Shell */}
      <div className="relative w-full max-w-sm h-[720px] max-h-[92vh] bg-neutral-950 rounded-[44px] border-[6px] border-neutral-800 shadow-2xl flex flex-col overflow-hidden ring-1 ring-white/10 z-10">

        {/* Dynamic Island / Speaker Notch & Status Bar */}
        <div className="relative px-6 pt-3 pb-1 flex justify-between items-center text-xs font-semibold text-gray-200 bg-neutral-950/80 z-20 shrink-0">
          <span className="font-mono text-[11px] tracking-tight">{displayTime}</span>

          <div className="w-24 h-4 bg-black rounded-full flex items-center justify-center gap-1.5 border border-neutral-800/80 shadow-inner">
            <span className="w-2 h-2 rounded-full bg-neutral-800" />
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-950/80" />
          </div>

          <div className="flex items-center gap-1.5 text-gray-300">
            <Wifi size={12} />
            <span className="text-[10px] font-mono">5G</span>
            <Battery size={14} className="text-emerald-400" />
          </div>
        </div>

        {/* OS Top Header */}
        <div className="px-5 py-2 border-b border-neutral-800/80 flex justify-between items-center bg-neutral-900/60 shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm">{branding.emoji || '📱'}</span>
            <span className="font-bold text-xs text-gray-200 tracking-wide font-sans">{branding.os_name || 'Mobile OS'}</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-full text-gray-400 hover:text-gray-100 hover:bg-neutral-800 transition-colors"
            title="Lock Phone"
          >
            <X size={15} />
          </button>
        </div>

        {/* Screen Canvas */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-3.5 bg-gradient-to-b from-neutral-900/40 to-black relative">

          {/* 1. PHOTOS / MEDIA GALLERY APP */}
          {activeApp === 'photos' && (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
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
                <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
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
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold transition-colors shrink-0 border ${
                        photoCategory === cat.id
                          ? 'bg-pink-600/30 text-pink-300 border-pink-500/50'
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
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                  <MessageSquare size={15} className="text-cyan-400" />
                  <span>{branding.dm_app_name || 'Messages'}</span>
                </h4>
                {appointments.length > 0 && (
                  <span className="text-[10px] font-bold px-1.5 py-0.2 bg-amber-500/20 text-amber-300 rounded border border-amber-500/40">
                    {appointments.length} Rendezvous
                  </span>
                )}
              </div>

              {/* Pending Appointments Banner */}
              {appointments.length > 0 && !activeChatNpc && (
                <div className="space-y-1.5">
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
                        <span className="text-[9px] font-mono px-1 bg-amber-900/60 text-amber-300 rounded uppercase font-bold">
                          Pending
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

              {/* Active Chat Thread or Contacts Directory */}
              {activeChatNpc ? (
                <div className="space-y-2 bg-neutral-900/70 border border-neutral-800 rounded-2xl p-3 flex flex-col h-[485px]">
                  <div className="flex items-center justify-between border-b border-neutral-800 pb-2 shrink-0">
                    <button
                      onClick={() => { setDmOutcomeBanner(null); closeChat(); }}
                      className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300"
                    >
                      <ChevronLeft size={14} />
                      <span>Back</span>
                    </button>
                    <span className="font-bold text-xs text-gray-200 truncate">{activeChatNpc}</span>
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

                  {/* Messages Bubble Canvas */}
                  <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2 py-2 pr-1">
                    {loadingChat ? (
                      <p className="text-[11px] text-gray-500 italic text-center py-8">Loading history...</p>
                    ) : chatMessages.length === 0 ? (
                      <p className="text-[11px] text-gray-500 italic text-center py-8">
                        Send a message below to start texting {activeChatNpc}!
                      </p>
                    ) : (
                      chatMessages.map((msg, idx) => {
                        const isPlayer = msg.sender === 'player' || msg.sender === 'Player' || msg.sender === 'You';
                        return (
                          <div
                            key={msg.id || idx}
                            className={`flex flex-col ${isPlayer ? 'items-end' : 'items-start'}`}
                          >
                            <div className={`max-w-[82%] rounded-2xl px-3 py-1.5 text-xs ${
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

                  {/* 6 Intent Selector Pills */}
                  <div className="flex items-center gap-1 pt-1 border-t border-neutral-800/80 overflow-x-auto shrink-0">
                    {[
                      { id: 'chat', label: '💬 Chat' },
                      { id: 'flirt', label: '💕 Flirt' },
                      { id: 'meetup', label: '📍 Meetup' },
                      { id: 'photo', label: '📸 Photo' },
                      { id: 'photo_nsfw', label: '🔥 Spicy' },
                      { id: 'rumor', label: '🕵️ Rumor' },
                    ].map(opt => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setSelectedIntent(opt.id)}
                        className={`px-2 py-0.5 rounded-full text-[10px] font-medium transition-colors shrink-0 ${
                          selectedIntent === opt.id
                            ? 'bg-cyan-600/30 text-cyan-300 border border-cyan-500/50'
                            : 'bg-neutral-950 text-gray-400 border border-neutral-800'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>

                  {/* Interactive 2-Way Message Composer + Quick Send */}
                  <form onSubmit={handleSendDm} className="flex items-center gap-1.5 pt-1 shrink-0">
                    <button
                      type="button"
                      disabled={sendingChat}
                      onClick={handleQuickSendDm}
                      title="Auto-compose & send message for selected intent"
                      className="px-2 py-1.5 rounded-full bg-purple-950/70 hover:bg-purple-900/80 text-purple-200 border border-purple-700/60 text-[10px] font-bold shrink-0 disabled:opacity-40 transition-colors"
                    >
                      ⚡ Quick
                    </button>
                    <input
                      type="text"
                      value={dmInput}
                      onChange={(e) => setDmInput(e.target.value)}
                      disabled={sendingChat}
                      placeholder={`Message ${activeChatNpc}...`}
                      className="flex-1 bg-neutral-950 border border-neutral-800 focus:border-cyan-500 rounded-full px-3 py-1.5 text-xs text-gray-200 focus:outline-none disabled:opacity-50"
                    />
                    <button
                      type="submit"
                      disabled={!dmInput.trim() || sendingChat}
                      className="p-1.5 rounded-full bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-40 transition-colors"
                    >
                      <Send size={13} />
                    </button>
                  </form>
                </div>
              ) : (
                <div className="space-y-2">
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
              )}
            </div>
          )}

          {/* 3. FEED / GOSSIP NET & PEERPULSE SOCIAL GRAPH APP */}
          {activeApp === 'feed' && (
            <div className="space-y-3">
              {/* Header + Rumor Charges */}
              <div className="flex items-center justify-between">
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
                      {gossipFeed.map((post, idx) => (
                        <div
                          key={post.id || idx}
                          className="bg-neutral-900/70 border border-neutral-800 rounded-xl p-3 space-y-1.5"
                        >
                          <div className="flex justify-between items-start">
                            <div>
                              <span className="font-bold text-xs text-gray-200 block">{post.author_name}</span>
                              {post.author_handle && (
                                <span className="text-[10px] text-purple-400 font-mono block">
                                  {post.author_handle.startsWith('@') ? post.author_handle : `@${post.author_handle}`}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-1.5">
                              {post.tag && (
                                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40">
                                  {post.tag}
                                </span>
                              )}
                              {post.time_ago && (
                                <span className="text-[9px] font-mono text-gray-500">{post.time_ago}</span>
                              )}
                            </div>
                          </div>

                          <p className="text-xs text-gray-300 leading-snug">{post.content}</p>

                          <div className="flex items-center justify-between pt-1">
                            {post.clue_hook ? (
                              <div className="text-[10px] text-cyan-300 flex items-center gap-1">
                                <Sparkles size={10} />
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
                      ))}
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
                            onClick={handleSendFriendReq}
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
                  ) : (
                    <div className="text-center py-10 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-1">
                      <Users size={26} className="mx-auto opacity-30 text-cyan-400" />
                      <p className="text-xs text-gray-400">Discover Peers & Mutual Connections</p>
                      <p className="text-[10px] text-gray-500">
                        Search by name or click "Discover Suggested Peer" to view social profiles and send Friend Requests.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}


          {/* 4. E-SHOP / DELIVERY APP */}
          {activeApp === 'shop' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                  <ShoppingBag size={15} className="text-amber-400" />
                  <span>{shopData?.flavor_name || 'Express Delivery'}</span>
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
                <p className="text-[11px] text-gray-400 italic bg-neutral-900/60 p-2.5 rounded-xl border border-neutral-800">
                  "{shopData.greeting}"
                </p>
              )}

              {shopFeedback && (
                <div className={`px-3 py-1.5 rounded-xl text-xs border flex items-center justify-between ${
                  shopFeedback.type === 'error'
                    ? 'bg-red-950/60 border-red-800/60 text-red-200'
                    : 'bg-emerald-950/60 border-emerald-800/60 text-emerald-200'
                }`}>
                  <span>{shopFeedback.text}</span>
                  <button
                    onClick={() => setShopFeedback(null)}
                    className="text-[10px] opacity-70 hover:opacity-100 ml-2"
                  >
                    ✕
                  </button>
                </div>
              )}

              {loadingShop ? (
                <p className="text-xs text-gray-500 italic text-center py-12">Connecting to courier network...</p>
              ) : !shopData || !shopData.inventory || shopData.inventory.length === 0 ? (
                <div className="text-center py-14 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
                  <ShoppingBag size={28} className="mx-auto opacity-30 text-amber-400 mb-1" />
                  <p className="text-xs">No courier catalog available right now.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {shopData.inventory.map((item, idx) => {
                    const finalPrice = item.final_price ?? item.price ?? 0;
                    const basePrice = item.base_price ?? item.price ?? finalPrice;
                    const canAfford = (shopData.gold ?? 0) >= finalPrice;
                    return (
                      <div
                        key={item.name || idx}
                        className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-2.5 space-y-1.5"
                      >
                        <div className="flex justify-between items-start gap-2">
                          <div className="min-w-0">
                            <span className="font-bold text-xs text-gray-200 block truncate">
                              {item.emoji || '📦'} {item.name}
                            </span>
                            <span className="text-[10px] text-gray-400 block leading-snug mt-0.5">
                              {item.description || item.effect || 'Courier delivery item'}
                            </span>
                          </div>
                          <div className="text-right shrink-0">
                            {basePrice > finalPrice && (
                              <span className="text-[10px] font-mono text-gray-500 line-through mr-1">
                                {basePrice}
                              </span>
                            )}
                            <span className="text-[11px] font-mono font-bold text-amber-300">
                              {shopData.currency_emoji || '💰'} {finalPrice}
                            </span>
                          </div>
                        </div>

                        <div className="flex justify-end pt-1">
                          <button
                            disabled={!canAfford || buyingItem === item.name}
                            onClick={() => handleBuyDeliveryItem(item)}
                            className={`px-3 py-1 rounded-lg text-[11px] font-bold transition-all ${
                              canAfford
                                ? 'bg-amber-600/30 hover:bg-amber-500/40 text-amber-200 border border-amber-500/50'
                                : 'bg-neutral-950 text-gray-600 border border-neutral-800 cursor-not-allowed'
                            }`}
                          >
                            {buyingItem === item.name ? 'Ordering...' : canAfford ? 'Order Delivery' : 'Insufficient Funds'}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}


        {/* 5. BOUNTIES APP */}
        {activeApp === 'bounties' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
                <ShieldAlert size={15} className="text-rose-400" />
                <span>{branding.bounties_app_name || 'Bounties'}</span>
              </h4>
            </div>

            {!codexHook?.availableBounties || codexHook.availableBounties.length === 0 ? (
              <div className="text-center py-14 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
                <ShieldAlert size={28} className="mx-auto opacity-30 text-rose-400 mb-1" />
                <p className="text-xs">No active bounty postings.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {codexHook.availableBounties.map((bounty, idx) => (
                  <div key={bounty.quest_id || idx} className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-2.5 space-y-1.5">
                    <div className="flex justify-between items-start gap-2">
                      <span className="font-bold text-xs text-gray-200">{bounty.title}</span>
                      <span className="text-[10px] font-mono text-rose-300 whitespace-nowrap">Target: {bounty.target_name}</span>
                    </div>
                    <p className="text-[10px] text-gray-400">{bounty.description}</p>
                    <div className="flex justify-end pt-1">
                      <button
                        onClick={() => codexHook.bountyAction && codexHook.bountyAction(bounty.quest_id, 'accept')}
                        className="px-3 py-1 rounded-lg text-[11px] font-bold bg-rose-600/30 hover:bg-rose-500/40 text-rose-200 border border-rose-500/50"
                      >
                        Accept Bounty
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
                className="p-1 text-gray-400 hover:text-gray-100"
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
                  className="mt-3 px-3 py-1.5 rounded-xl bg-red-950/60 hover:bg-red-900/70 text-red-300 border border-red-800/60 text-xs font-bold transition-colors"
                >
                  {deletingPhoto ? 'Deleting...' : '🗑️ Delete Media'}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Bottom OS Navigation Dock */}
        <div className="px-4 py-2.5 bg-neutral-950 border-t border-neutral-800/80 flex justify-around items-center shrink-0">
          <button
            onClick={() => { setActiveApp('photos'); setSelectedPhoto(null); }}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeApp === 'photos'
                ? 'text-pink-400 bg-pink-950/30'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <Camera size={18} />
            <span className="text-[9px] font-semibold tracking-tight">{branding.gallery_app_name || 'Photos'}</span>
          </button>

          <button
            onClick={() => { setActiveApp('dms'); setSelectedPhoto(null); }}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all relative ${
              activeApp === 'dms'
                ? 'text-cyan-400 bg-cyan-950/30'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <MessageSquare size={18} />
            <span className="text-[9px] font-semibold tracking-tight">{branding.dm_app_name || 'DMs'}</span>
            {appointments.length > 0 && (
              <span className="absolute top-0 right-2 w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            )}
          </button>

          <button
            onClick={() => { setActiveApp('feed'); setSelectedPhoto(null); }}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeApp === 'feed'
                ? 'text-purple-400 bg-purple-950/30'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <Rss size={18} />
            <span className="text-[9px] font-semibold tracking-tight">{branding.feed_app_name || 'Feed'}</span>
          </button>

          <button
            onClick={() => { setActiveApp('shop'); setSelectedPhoto(null); }}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeApp === 'shop'
                ? 'text-amber-400 bg-amber-950/30'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <ShoppingBag size={18} />
            <span className="text-[9px] font-semibold tracking-tight">{branding.shop_app_name || 'E-Shop'}</span>
          </button>

          <button
            onClick={() => { setActiveApp('bounties'); setSelectedPhoto(null); }}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeApp === 'bounties'
                ? 'text-rose-400 bg-rose-950/30'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <ShieldAlert size={18} />
            <span className="text-[9px] font-semibold tracking-tight">{branding.bounties_app_name || 'Bounties'}</span>
          </button>
        </div>

        {/* Hardware Home Indicator Bar */}
        <div className="pb-2 pt-1 flex justify-center bg-neutral-950 shrink-0">
          <div
            onClick={onClose}
            className="w-32 h-1 bg-neutral-600 hover:bg-neutral-400 rounded-full cursor-pointer transition-colors"
            title="Swipe up to close"
          />
        </div>

      </div>
    </div>
  );
};

export default PhoneModal;
