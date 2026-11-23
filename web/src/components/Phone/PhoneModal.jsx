import { useState, useEffect, useRef, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import {
  X, Camera, MessageSquare, Rss, Wifi,
  Calendar, ChevronLeft, ShoppingBag, ShieldAlert, Home,
  Settings,
} from 'lucide-react';
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
import PhonePhotoLightbox from './PhonePhotoLightbox';
import {
  FOCAL_OBJECT_CLASS,
  isImageGenModeActive,
  resolveActivePhoneWallpaper,
} from './phoneWallpapers';
import { usePhoneSocialControllers } from './usePhoneSocialControllers';
import { usePhoneCommerceControllers } from './usePhoneCommerceControllers';

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

  const {
    branding,
    appointments,
    gossipFeed,
    mediaGallery,
    contacts,
    suggestedPeers = [],
    socialState,
    activeChatNpc,
    chatMessages,
    dailyLimits,
    loadingChat,
    sendingChat,
    imageGenEnabled = 0,
    loadChatMessages,
    closeChat,
  } = phoneHook;

  const effectiveImageGenMode =
    session?.image_gen_enabled ?? imageGenMode ?? imageGenEnabled ?? 0;
  const isImgGenActive = isImageGenModeActive(effectiveImageGenMode);

  const social = usePhoneSocialControllers({
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
    t,
  });

  const commerce = usePhoneCommerceControllers({
    isOpen,
    activeApp,
    session,
    user,
    codexHook,
    onRefreshInventory,
    onRefreshCharacter,
    onRefreshCodex,
    t,
  });

  const wasOpenRef = useRef(false);
  const prevSessionIdRef = useRef(session?.id ?? null);
  const phoneDialogRef = useRef(null);
  const previousFocusRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const phonePrefsRef = useRef(phonePrefs);
  phonePrefsRef.current = phonePrefs;

  useEffect(() => {
    const nextSid = session?.id ?? null;
    if (prevSessionIdRef.current === nextSid) return;
    prevSessionIdRef.current = nextSid;
    setActiveApp('home');
  }, [session?.id]);

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
  const socialSettersRef = useRef(null);
  socialSettersRef.current = social;

  // Open requested DM thread (or home screen on false -> true transition) when modal opens
  useEffect(() => {
    const justOpened = isOpen && !wasOpenRef.current;
    wasOpenRef.current = isOpen;
    if (!isOpen) return;

    const s = socialSettersRef.current;
    if (justOpened && phonePrefsRef.current?.carouselEnabled) {
      s.advanceCarousel();
    }

    if (initialChatNpc) {
      s.setSelectedPhoto(null);
      s.setPhotoActionError(null);
      setActiveApp('dms');
      s.setMessagesSubTab('contacts');
      s.setDmOutcomeBanner(null);
      if (loadChatMessagesRef.current) {
        loadChatMessagesRef.current(initialChatNpc);
      }
      if (onClearInitialChatNpcRef.current) {
        onClearInitialChatNpcRef.current();
      }
    } else if (justOpened) {
      s.setSelectedPhoto(null);
      s.setPhotoActionError(null);
      setActiveApp('home');
    }
  }, [isOpen, initialChatNpc]);

  let displayTime = formatClockTime(581, clockFormat);
  if (session && session.current_minute !== undefined) {
    displayTime = formatClockTime(session.current_minute, clockFormat);
  }

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
      badge: social.plannerItems.length > 0 ? social.plannerItems.length : null,
      badgeColor: 'bg-blue-500',
    },
    {
      id: 'bounties',
      name: branding.bounty_app_name || branding.bounties_app_name || t('phone.apps.bounties', 'Campus Requests'),
      subtitle: branding.bounty_subtitle || t('phone.apps.bounties_sub', 'Student Bulletin'),
      icon: ShieldAlert,
      gradient: 'from-rose-500 via-red-600 to-rose-700',
      badge: commerce.availableBounties.length > 0 ? commerce.availableBounties.length : null,
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
    Boolean(commerce.realtyData?.enabled) ||
    scenLowForRealty.includes('anomalous_incursion') ||
    scenLowForRealty.includes('anomalous_high_school') ||
    scenLowForRealty.includes('urban_anomalies');

  if (isAnomalousRealtyScenario) {
    apps.push({
      id: 'realty',
      name: t('realty.app_name', 'Realty & Deeds'),
      subtitle: t('realty.app_sub', 'Safehouses & Keys'),
      icon: Home,
      gradient: 'from-emerald-600 via-teal-600 to-cyan-700',
      badge: commerce.realtyData?.owned_properties?.length
        ? commerce.realtyData.owned_properties.length
        : null,
      badgeColor: 'bg-emerald-500',
    });
  }

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
        activeCarouselEntry: social.activeCarouselEntry,
      }),
    [phonePrefs, session, mediaGallery, social.activeCarouselEntry]
  );

  const showWallpaperBackdrop = isGlass || activeApp === 'home';
  const blurWallpaperNow = isGlass && activeApp !== 'home' && phonePrefs?.blurInApps !== false;

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
                    social.setSelectedPhoto(null);
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
                  availableBounties={commerce.availableBounties}
                  mediaGallery={mediaGallery}
                  apps={apps}
                  onSelectApp={(appId) => {
                    setActiveApp(appId);
                    social.setSelectedPhoto(null);
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
                  onShuffleCarousel={social.advanceCarousel}
                  t={t}
                />
              )}

              {activeApp === 'realty' && (
                <PhoneRealtyApp
                  realtyData={commerce.realtyData}
                  loadingRealty={commerce.loadingRealty}
                  realtyBusy={commerce.realtyBusy}
                  realtyBanner={commerce.realtyBanner}
                  onClearBanner={() => commerce.setRealtyBanner(null)}
                  realtySubTab={commerce.realtySubTab}
                  onChangeSubTab={commerce.setRealtySubTab}
                  selectedSpareKeyNpc={commerce.selectedSpareKeyNpc}
                  onSelectSpareKeyNpc={(propId, npcId) =>
                    commerce.setSelectedSpareKeyNpc((prev) => ({ ...prev, [propId]: npcId }))
                  }
                  onRefreshRealty={commerce.fetchRealty}
                  onSetPrimaryProperty={commerce.handleSetPrimaryProperty}
                  onManageSpareKey={commerce.handleManageSpareKey}
                  onBuyProperty={commerce.handleBuyProperty}
                  scenario={scenarioKey}
                  t={t}
                />
              )}

              {activeApp === 'planner' && (
                <PhonePlannerApp
                  branding={branding}
                  session={session}
                  plannerItems={social.plannerItems}
                  cancellingCommitmentId={social.cancellingCommitmentId}
                  onCancelPlannerItem={social.handleCancelPlannerItem}
                  onOpenMessages={() => setActiveApp('dms')}
                  onOpenChatWithContact={social.handleOpenChatWithContact}
                  clockFormat={clockFormat}
                  t={t}
                />
              )}

              {activeApp === 'photos' && (
                <PhonePhotosApp
                  branding={branding}
                  mediaGallery={mediaGallery}
                  filteredGallery={social.filteredGallery}
                  galleryContacts={social.galleryContacts}
                  photoCategory={social.photoCategory}
                  onChangePhotoCategory={social.setPhotoCategory}
                  photoContactFilter={social.photoContactFilter}
                  onChangePhotoContactFilter={social.setPhotoContactFilter}
                  onSelectPhoto={(photo) => {
                    social.setPhotoActionError(null);
                    social.setSelectedPhoto(photo);
                  }}
                  clockFormat={clockFormat}
                  t={t}
                />
              )}

              {activeApp === 'dms' && (
                <PhoneDmsApp
                  branding={branding}
                  activeChatNpc={activeChatNpc}
                  activeDisplayTitle={social.activeDisplayTitle}
                  isDispatchThread={social.isDispatchThread}
                  isBlockedContact={social.isBlockedContact}
                  dmOutcomeBanner={social.dmOutcomeBanner}
                  onClearOutcomeBanner={() => social.setDmOutcomeBanner(null)}
                  loadingChat={loadingChat}
                  chatMessages={chatMessages}
                  sendingChat={sendingChat}
                  dailyLimits={dailyLimits}
                  activeContactEntry={social.activeContactEntry}
                  selectedIntent={social.selectedIntent}
                  onInstantIntentSend={social.handleInstantIntentSend}
                  dmInput={social.dmInput}
                  onChangeDmInput={social.setDmInput}
                  onSendDm={social.handleSendDm}
                  onCloseChat={closeChat}
                  appointments={appointments}
                  showDispatchTab={social.showDispatchTab}
                  messagesSubTab={social.messagesSubTab}
                  onChangeMessagesSubTab={social.setMessagesSubTab}
                  dmDirectory={social.dmDirectory}
                  dispatchDirectory={social.dispatchDirectory}
                  onLoadChatMessages={loadChatMessages}
                  mediaGallery={mediaGallery}
                  imageGenEnabled={effectiveImageGenMode}
                  onSelectPhoto={(photo) => {
                    social.setPhotoActionError(null);
                    social.setSelectedPhoto(photo);
                  }}
                  onGenerateMediaPhoto={(itemId) => social.handleGenerateMediaPhoto(itemId)}
                  clockFormat={clockFormat}
                  t={t}
                />
              )}

              {activeApp === 'feed' && (
                <PhoneFeedApp
                  branding={branding}
                  socialState={socialState}
                  feedSubTab={social.feedSubTab}
                  onChangeFeedSubTab={social.setFeedSubTab}
                  feedBusy={social.feedBusy}
                  feedBanner={social.feedBanner}
                  onClearFeedBanner={() => social.setFeedBanner(null)}
                  onScourRumor={social.handleScourRumor}
                  onRefreshFeed={social.handleRefreshFeed}
                  gossipFeed={gossipFeed}
                  peerQuery={social.peerQuery}
                  onChangePeerQuery={social.setPeerQuery}
                  peerBusy={social.peerBusy}
                  peerFeedback={social.peerFeedback}
                  onClearPeerFeedback={() => social.setPeerFeedback(null)}
                  peerProfile={social.peerProfile}
                  onSelectPeerProfile={social.setPeerProfile}
                  onDiscoverPeer={social.handleDiscoverPeer}
                  onSendFriendRequest={social.handleSendFriendReq}
                  suggestedPeers={suggestedPeers}
                  contacts={contacts}
                  onOpenChatWithContact={social.handleOpenChatWithContact}
                  t={t}
                />
              )}

              {activeApp === 'shop' && (
                <PhoneShopApp
                  branding={branding}
                  shopData={commerce.shopData}
                  loadingShop={commerce.loadingShop}
                  buyingItem={commerce.buyingItem}
                  shopFeedback={commerce.shopFeedback}
                  onClearFeedback={() => commerce.setShopFeedback(null)}
                  onBuyDeliveryItem={commerce.handleBuyDeliveryItem}
                  scenario={scenarioKey}
                  t={t}
                />
              )}

              {activeApp === 'bounties' && (
                <PhoneBountiesApp
                  branding={branding}
                  generatingBounties={commerce.generatingBounties}
                  onRefreshBounties={commerce.handleRefreshBounties}
                  bountySubTab={commerce.bountySubTab}
                  onChangeBountySubTab={commerce.setBountySubTab}
                  allAvailableBounties={commerce.allAvailableBounties}
                  availableBounties={commerce.availableBounties}
                  activeBounties={commerce.activeBounties}
                  factionsList={commerce.factionsList}
                  selectedFactionFilter={commerce.selectedFactionFilter}
                  onSelectFactionFilter={commerce.setSelectedFactionFilter}
                  bountyActionBanner={commerce.bountyActionBanner}
                  onClearBanner={() => commerce.setBountyActionBanner(null)}
                  onAcceptBounty={commerce.handleAcceptBounty}
                  onAbandonBounty={commerce.handleAbandonBounty}
                  busyBountyId={commerce.busyBountyId}
                  scenario={scenarioKey}
                  t={t}
                />
              )}
            </div>

            {/* Expanded Photo Preview Overlay */}
            <PhonePhotoLightbox
              photo={social.liveSelectedPhoto}
              sessionId={session?.id}
              isImgGenActive={isImgGenActive}
              generatingPhotoId={social.generatingPhotoId}
              deletingPhoto={social.deletingPhoto}
              photoActionError={social.photoActionError}
              isSelectedPhotoActiveWallpaper={social.isSelectedPhotoActiveWallpaper}
              onClosePhoto={() => {
                social.setSelectedPhoto(null);
                social.setPhotoActionError(null);
              }}
              onGenerateMediaPhoto={social.handleGenerateMediaPhoto}
              onSetPhotoAsWallpaper={social.handleSetPhotoAsWallpaper}
              onDeleteMedia={social.handleDeleteMedia}
              t={t}
            />

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
                  if (social.selectedPhoto) {
                    social.setSelectedPhoto(null);
                    social.setPhotoActionError(null);
                  } else if (activeApp === 'dms' && activeChatNpc) {
                    social.setDmOutcomeBanner(null);
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
                  if (activeApp !== 'home' || social.selectedPhoto || activeChatNpc) {
                    setActiveApp('home');
                    social.setSelectedPhoto(null);
                    social.setPhotoActionError(null);
                    social.setDmOutcomeBanner(null);
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
