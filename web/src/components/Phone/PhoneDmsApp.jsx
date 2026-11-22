import { useRef } from 'react';
import {
  Calendar,
  ChevronLeft,
  Heart,
  MapPin,
  MessageSquare,
  Send,
  ShieldAlert,
  User,
  Users,
} from 'lucide-react';
import { formatCleanLocation } from '../../utils/locationFormat';
import { formatTimestamp } from './phoneHelpers';

const PhoneDmsApp = ({
  branding,
  activeChatNpc,
  activeDisplayTitle,
  isDispatchThread,
  isBlockedContact,
  dmOutcomeBanner,
  onClearOutcomeBanner,
  loadingChat,
  chatMessages = [],
  sendingChat,
  dailyLimits,
  activeContactEntry,
  selectedIntent,
  onInstantIntentSend,
  dmInput,
  onChangeDmInput,
  onSendDm,
  onCloseChat,
  appointments = [],
  showDispatchTab,
  messagesSubTab,
  onChangeMessagesSubTab,
  dmDirectory = [],
  dispatchDirectory = [],
  onLoadChatMessages,
  clockFormat = '12h',
  t,
}) => {
  const msgTabRefs = useRef({});

  return (
    <div className="flex-1 flex flex-col h-full min-h-0">
      {/* Active Chat Thread */}
      {activeChatNpc ? (
        <div className="flex-1 flex flex-col h-full min-h-0 space-y-2">
          {/* Single Clean Chat Header */}
          <div className="flex items-center justify-between pb-2 border-b border-neutral-800/80 shrink-0 gap-2">
            <button
              type="button"
              onClick={() => {
                onClearOutcomeBanner();
                onCloseChat();
              }}
              className="p-1 rounded-full text-cyan-400 hover:text-cyan-300 hover:bg-neutral-800/80 transition-colors flex items-center gap-0.5 text-xs font-semibold cursor-pointer shrink-0"
            >
              <ChevronLeft size={16} />
              <span>{branding.dm_app_name || 'Messages'}</span>
            </button>
            <div className="flex items-center gap-2 min-w-0">
              <div
                className={`w-6 h-6 rounded-full border flex items-center justify-center font-bold text-[10px] shrink-0 ${
                  isDispatchThread
                    ? 'bg-indigo-950 border-indigo-700/60 text-indigo-300'
                    : isBlockedContact
                      ? 'bg-red-950 border-red-700/60 text-red-300'
                      : 'bg-cyan-950 border-cyan-800/60 text-cyan-300'
                }`}
              >
                {isDispatchThread ? '📡' : <User size={12} />}
              </div>
              <span className="font-bold text-xs text-gray-100 truncate">{activeDisplayTitle}</span>
              {isBlockedContact && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-950/80 text-red-300 border border-red-700/60 font-bold uppercase shrink-0">
                  🚫 {t('contacts.blocked_badge', 'Blocked')}
                </span>
              )}
            </div>
            <div className="w-6 shrink-0" />
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
                    <span
                      className={`px-1.5 py-0.5 rounded font-mono tabular-nums font-bold ${
                        dmOutcomeBanner.affinity_delta > 0
                          ? 'bg-pink-950/60 text-pink-300 border border-pink-700/50'
                          : 'bg-red-950/60 text-red-300 border border-red-700/50'
                      }`}
                    >
                      {dmOutcomeBanner.affinity_delta > 0
                        ? `+${dmOutcomeBanner.affinity_delta}`
                        : dmOutcomeBanner.affinity_delta}{' '}
                      Affinity
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={onClearOutcomeBanner}
                  className="text-gray-500 hover:text-gray-300"
                >
                  ✕
                </button>
              </div>
              {dmOutcomeBanner.daily_digestion_capped && (
                <div className="text-indigo-300">
                  💬{' '}
                  {t(
                    'social.bond_settling_dm',
                    'Bond Settling Today — further chats unlock facts without forcing affinity.'
                  )}
                </div>
              )}
              {Array.isArray(dmOutcomeBanner.discovered_facts) && dmOutcomeBanner.discovered_facts.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-0.5">
                  {dmOutcomeBanner.discovered_facts.map((df, dIdx) => (
                    <span
                      key={dIdx}
                      className="px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-700/50 font-medium"
                    >
                      ✨ {typeof df === 'string' ? df : df.fact_value || df.label || ''}
                    </span>
                  ))}
                </div>
              )}
              {dmOutcomeBanner.rendezvous_location && (
                <div className="text-amber-300">
                  {t('phone.dms.scheduled_meetup', '📍 Meetup Scheduled:')}{' '}
                  <strong>{formatCleanLocation(dmOutcomeBanner.rendezvous_location)}</strong>
                </div>
              )}
              {dmOutcomeBanner.media_dropped && (
                <div className="text-pink-300">
                  {t('phone.dms.media_received', '📸 Media Received:')}{' '}
                  <strong>{dmOutcomeBanner.media_dropped.name || t('phone.dms.saved_to_vault', 'Saved to Photo Vault!')}</strong>
                </div>
              )}
            </div>
          )}

          {/* Messages Bubble Canvas - Edge to Edge */}
          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2 py-1 pr-1 min-h-0">
            {loadingChat ? (
              <p className="text-[11px] text-gray-500 italic text-center py-8">
                {t('phone.dms.loading_history', 'Loading history...')}
              </p>
            ) : chatMessages.length === 0 ? (
              <p className="text-[11px] text-gray-500 italic text-center py-8">
                {isDispatchThread
                  ? 'No official dispatch alerts received yet.'
                  : `Pick a message topic below to text ${activeDisplayTitle}!`}
              </p>
            ) : (
              chatMessages.map((msg, idx) => {
                const isPlayer = msg.sender === 'player' || msg.sender === 'Player' || msg.sender === 'You';
                return (
                  <div key={msg.id || idx} className={`flex flex-col ${isPlayer ? 'items-end' : 'items-start'}`}>
                    <div
                      className={`max-w-[85%] rounded-2xl px-3 py-1.5 text-xs ${
                        isPlayer
                          ? 'bg-cyan-600 text-white rounded-tr-none'
                          : isDispatchThread
                            ? 'bg-indigo-950/60 text-indigo-100 rounded-tl-none border border-indigo-700/50'
                            : 'bg-neutral-800 text-gray-200 rounded-tl-none border border-neutral-700/50'
                      }`}
                    >
                      <p className="leading-snug whitespace-pre-line">{msg.message}</p>
                    </div>
                    <span className="text-[9px] font-mono tabular-nums text-gray-500 mt-0.5 px-1">
                      {formatTimestamp(msg.timestamp, clockFormat)}
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

          {/* Footer Controls: Read-Only Broadcast vs Blocked Contact vs Personal DM Composer */}
          {isDispatchThread ? (
            <div className="p-2.5 rounded-xl bg-indigo-950/35 border border-indigo-800/50 text-center text-[11px] text-indigo-200 font-medium shrink-0">
              📡 {t('phone.read_only_broadcast', 'Automated Official Broadcast Channel — Read-Only')}
            </div>
          ) : isBlockedContact ? (
            <div className="p-2.5 rounded-xl bg-red-950/40 border border-red-800/60 text-center text-[11px] text-red-200 leading-snug shrink-0">
              🚫{' '}
              {t(
                'phone.blocked_notice',
                'This contact has blocked your number due to hostility. Reconcile with them in person first.'
              )}
            </div>
          ) : (
            <>
              {/* 1-Click Intent Action Grid: 4 Columns x 2 Rows */}
              {(() => {
                const chatMax = dailyLimits?.chat?.max ?? ((activeContactEntry?.score ?? 0) >= 100 ? 5 : 3);
                const chatUsed = dailyLimits?.chat?.used ?? 0;
                const chatLeft = Math.max(0, chatMax - chatUsed);
                const isMeetupAccepted = dailyLimits?.meetup?.status === 'accepted';
                const flirtLocked = !!(dailyLimits?.flirt?.locked || dailyLimits?.flirt?.used >= 3);
                const meetupLocked = !!(
                  dailyLimits?.meetup?.locked ||
                  (isMeetupAccepted
                    ? (dailyLimits?.meetup?.relocations_left ?? 2) <= 0
                    : (dailyLimits?.meetup?.used ?? 0) >= 1)
                );
                const rumorLocked = !!(dailyLimits?.rumor?.locked || (dailyLimits?.rumor?.used ?? 0) >= 1);
                const photoLocked = !!(dailyLimits?.photo?.locked || (dailyLimits?.photo?.used ?? 0) >= 3);
                const spicyLocked = !!(dailyLimits?.spicy?.locked || (dailyLimits?.spicy?.used ?? 0) >= 3);

                const intentOptions = [
                  {
                    id: 'chat',
                    label: t('phone.dms.action_chat', 'Chat'),
                    icon: '💬',
                    badge: `${chatLeft}/${chatMax}`,
                    locked: chatLeft === 0,
                    disabled: sendingChat,
                    color: 'hover:border-cyan-500/50 hover:bg-cyan-950/40 text-cyan-200',
                    title: t(
                      'phone.dms.action_chat_title',
                      `Send a friendly chat message (${chatMax} affinity-granting chats/day)`,
                      { max: chatMax }
                    ),
                  },
                  {
                    id: 'flirt',
                    label: t('phone.dms.action_flirt', 'Flirt'),
                    icon: '💕',
                    badge: dailyLimits
                      ? flirtLocked
                        ? '🔒'
                        : `${Math.max(0, 3 - (dailyLimits?.flirt?.used ?? 0))}/3`
                      : '3/3',
                    locked: flirtLocked,
                    disabled: sendingChat || flirtLocked,
                    color: 'hover:border-pink-500/50 hover:bg-pink-950/40 text-pink-200',
                    title: t('phone.dms.action_flirt_title', 'Flirt with contact (3 attempts/day)'),
                  },
                  {
                    id: 'meetup',
                    label: isMeetupAccepted
                      ? t('phone.dms.action_move', 'Move')
                      : t('phone.dms.action_meetup', 'Meetup'),
                    icon: '📍',
                    badge: dailyLimits
                      ? isMeetupAccepted
                        ? meetupLocked
                          ? '🔒'
                          : `${dailyLimits?.meetup?.relocations_left ?? 2} left`
                        : meetupLocked
                          ? '🔒'
                          : '1/1'
                      : '1/1',
                    locked: meetupLocked,
                    disabled: sendingChat || meetupLocked,
                    color: 'hover:border-amber-500/50 hover:bg-amber-950/40 text-amber-200',
                    title: isMeetupAccepted
                      ? t('phone.dms.action_move_title', 'Relocate meetup spot (up to 2 times)')
                      : t('phone.dms.action_meetup_title', 'Propose to meet up (1 attempt/day)'),
                  },
                  {
                    id: 'rumor',
                    label: t('phone.dms.action_rumor', 'Rumor'),
                    icon: '🕵️',
                    badge: dailyLimits ? (rumorLocked ? '🔒' : '1/1') : '1/1',
                    locked: rumorLocked,
                    disabled: sendingChat || rumorLocked,
                    color: 'hover:border-emerald-500/50 hover:bg-emerald-950/40 text-emerald-200',
                    title: t('phone.dms.action_rumor_title', 'Ask for rumors and gossip (1 attempt/day)'),
                  },
                  {
                    id: 'photo_ask',
                    label: t('phone.dms.action_ask_pic', 'Ask Pic'),
                    icon: '📸',
                    badge: dailyLimits
                      ? photoLocked
                        ? '🔒'
                        : `${Math.max(0, 3 - (dailyLimits?.photo?.used ?? 0))}/3`
                      : '3/3',
                    locked: photoLocked,
                    disabled: sendingChat || photoLocked,
                    color: 'hover:border-purple-500/50 hover:bg-purple-950/40 text-purple-200',
                    title: t('phone.dms.action_ask_pic_title', 'Ask contact for a casual photo (shared 3/day)'),
                  },
                  {
                    id: 'photo_send',
                    label: t('phone.dms.action_send_pic', 'Send Pic'),
                    icon: '📤',
                    badge: dailyLimits
                      ? photoLocked
                        ? '🔒'
                        : `${Math.max(0, 3 - (dailyLimits?.photo?.used ?? 0))}/3`
                      : '3/3',
                    locked: photoLocked,
                    disabled: sendingChat || photoLocked,
                    color: 'hover:border-teal-500/50 hover:bg-teal-950/40 text-teal-200',
                    title: t('phone.dms.action_send_pic_title', 'Send contact a casual photo (shared 3/day)'),
                  },
                  {
                    id: 'spicy_ask',
                    label: t('phone.dms.action_ask_spicy', 'Ask Spicy'),
                    icon: '🔥',
                    badge: dailyLimits
                      ? spicyLocked
                        ? '🔒'
                        : `${Math.max(0, 3 - (dailyLimits?.spicy?.used ?? 0))}/3`
                      : '3/3',
                    locked: spicyLocked,
                    disabled: sendingChat || spicyLocked,
                    color: 'hover:border-rose-500/50 hover:bg-rose-950/40 text-rose-200',
                    title: t('phone.dms.action_ask_spicy_title', 'Ask contact for a spicy photo (shared 3/day)'),
                  },
                  {
                    id: 'spicy_send',
                    label: t('phone.dms.action_send_spicy', 'Send Spicy'),
                    icon: '💋',
                    badge: dailyLimits
                      ? spicyLocked
                        ? '🔒'
                        : `${Math.max(0, 3 - (dailyLimits?.spicy?.used ?? 0))}/3`
                      : '3/3',
                    locked: spicyLocked,
                    disabled: sendingChat || spicyLocked,
                    color: 'hover:border-red-500/50 hover:bg-red-950/40 text-red-200',
                    title: t(
                      'phone.dms.action_send_spicy_title',
                      'Send contact a spicy photo of yourself (shared 3/day)'
                    ),
                  },
                ];

                return (
                  <div className="grid grid-cols-4 gap-1.5 pt-2 border-t border-neutral-800/80 shrink-0">
                    {intentOptions.map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        disabled={opt.disabled}
                        onClick={() => onInstantIntentSend(opt.id)}
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
                          <span
                            className={`text-[8px] font-mono tabular-nums leading-none mt-0.5 px-1 rounded ${
                              opt.locked ? 'text-amber-300/90 bg-amber-950/40' : 'text-neutral-400'
                            }`}
                          >
                            {opt.badge}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                );
              })()}

              {/* Custom Message Composer */}
              <form onSubmit={onSendDm} className="flex items-center gap-2 pt-1.5 shrink-0">
                <input
                  type="text"
                  value={dmInput}
                  onChange={(e) => onChangeDmInput(e.target.value)}
                  disabled={sendingChat}
                  placeholder={`Custom message to ${activeDisplayTitle}...`}
                  className="flex-1 bg-neutral-900 border border-neutral-800 focus:border-cyan-500 rounded-xl px-3.5 py-2.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none disabled:opacity-50 transition-colors"
                />
                <button
                  type="submit"
                  disabled={!dmInput.trim() || sendingChat}
                  className="p-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-40 transition-colors cursor-pointer shrink-0 shadow-sm"
                  title={t('phone.dms.send_custom', 'Send Custom Message')}
                >
                  <Send size={16} />
                </button>
              </form>
            </>
          )}
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
              <span className="text-[10px] font-bold tabular-nums px-2 py-0.5 bg-amber-500/20 text-amber-300 rounded-full border border-amber-500/40">
                {appointments.length} Rendezvous
              </span>
            )}
          </div>

          {/* Contacts vs Alerts / Dispatch Sub-View Switcher */}
          {showDispatchTab && (
            <div
              role="tablist"
              aria-label={t('phone.dms.channels_aria', 'Message channels')}
              onKeyDown={(e) => {
                if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                  e.preventDefault();
                  const next = messagesSubTab === 'contacts' ? 'dispatch' : 'contacts';
                  onChangeMessagesSubTab(next);
                  msgTabRefs.current[next]?.focus();
                }
              }}
              className="flex bg-neutral-900 p-1 rounded-xl border border-neutral-800 gap-1 shrink-0"
            >
              <button
                ref={(el) => {
                  msgTabRefs.current.contacts = el;
                }}
                type="button"
                role="tab"
                aria-selected={messagesSubTab === 'contacts'}
                tabIndex={messagesSubTab === 'contacts' ? 0 : -1}
                onClick={() => onChangeMessagesSubTab('contacts')}
                className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors cursor-pointer ${
                  messagesSubTab === 'contacts'
                    ? 'bg-cyan-600/30 text-cyan-200 border border-cyan-500/50'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                <Users size={12} />
                <span>
                  {t('contacts.title', 'Contacts')} ({dmDirectory.length})
                </span>
              </button>
              <button
                ref={(el) => {
                  msgTabRefs.current.dispatch = el;
                }}
                type="button"
                role="tab"
                aria-selected={messagesSubTab === 'dispatch'}
                tabIndex={messagesSubTab === 'dispatch' ? 0 : -1}
                onClick={() => onChangeMessagesSubTab('dispatch')}
                className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors cursor-pointer ${
                  messagesSubTab === 'dispatch'
                    ? 'bg-indigo-600/30 text-indigo-200 border border-indigo-500/50'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                <ShieldAlert size={12} />
                <span>
                  {t('phone.alerts_dispatch', 'Alerts / Dispatch')} ({dispatchDirectory.length})
                </span>
              </button>
            </div>
          )}

          {/* Pending Appointments Banner (only in personal Contacts sub-tab) */}
          {messagesSubTab === 'contacts' && appointments.length > 0 && (
            <div className="space-y-1.5 shrink-0">
              <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider flex items-center gap-1">
                <Calendar size={11} />
                <span>{t('phone.dms.scheduled_meetups', 'Scheduled Meetups')}</span>
              </span>
              {appointments.map((appt, i) => (
                <div
                  key={appt.id || i}
                  className="bg-amber-950/30 border border-amber-600/40 rounded-xl p-2.5 space-y-1"
                >
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-xs text-amber-200">{appt.npc_name}</span>
                    <span
                      className={`text-[9px] font-mono px-1.5 py-0.5 rounded uppercase font-bold border ${
                        appt.status === 'arrived'
                          ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
                          : 'bg-amber-900/60 text-amber-300 border-amber-700/60'
                      }`}
                    >
                      {appt.status === 'arrived' ? 'Arrived' : 'Pending'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 text-[11px] text-gray-300">
                    <MapPin size={11} className="text-amber-400 shrink-0" />
                    <span>
                      {t('phone.dms.rendezvous', 'Rendezvous:')}{' '}
                      <strong>{formatCleanLocation(appt.rendezvous_location)}</strong>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Directory List */}
          <div className="space-y-2 flex-1 overflow-y-auto custom-scrollbar pr-0.5 min-h-0">
            {showDispatchTab && messagesSubTab === 'dispatch' ? (
              <>
                <span className="text-[10px] uppercase font-bold text-gray-500 tracking-wider block">
                  {t('phone.alerts_dispatch', 'Alerts / Dispatch')} ({dispatchDirectory.length})
                </span>
                {dispatchDirectory.length === 0 ? (
                  <div className="text-center py-10 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
                    <ShieldAlert size={24} className="mx-auto opacity-30 text-indigo-400 mb-1" />
                    <p className="text-xs">
                      {t('phone.dms.no_dispatches', 'No official dispatch broadcasts yet.')}
                    </p>
                  </div>
                ) : (
                  dispatchDirectory.map((ch) => (
                    <button
                      key={ch.npc_id}
                      type="button"
                      onClick={() => onLoadChatMessages(ch.npc_id)}
                      className="w-full text-left bg-indigo-950/25 border border-indigo-800/50 hover:border-indigo-500/60 rounded-xl p-2.5 flex items-center justify-between cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-8 h-8 rounded-full bg-indigo-950/80 border border-indigo-700/60 flex items-center justify-center text-indigo-300 font-bold text-xs shrink-0">
                          📡
                        </div>
                        <div className="min-w-0">
                          <span className="font-semibold text-xs text-indigo-100 block truncate">
                            {ch.name}
                          </span>
                          <span className="text-[10px] text-indigo-300/75 block truncate">{ch.role}</span>
                        </div>
                      </div>
                      <ChevronLeft size={14} className="text-indigo-400/70 rotate-180 shrink-0" />
                    </button>
                  ))
                )}
              </>
            ) : (
              <>
                <span className="text-[10px] uppercase font-bold text-gray-500 tracking-wider block">
                  {t('contacts.title', 'Contacts')} ({dmDirectory.length})
                </span>
                {dmDirectory.length === 0 ? (
                  <div className="text-center py-10 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
                    <MessageSquare size={24} className="mx-auto opacity-30 text-cyan-400 mb-1" />
                    <p className="text-xs">{t('contacts.no_contacts', 'No personal contacts unlocked yet.')}</p>
                    <p className="text-[10px] text-gray-500 mt-1">
                      {t(
                        'contacts.unlock_hint',
                        "Ask for someone's number in conversation, add them on PeerPulse, or reach Friend standing (100+)."
                      )}
                    </p>
                  </div>
                ) : (
                  dmDirectory.map((c) => (
                    <button
                      key={c.npc_id}
                      type="button"
                      onClick={() => onLoadChatMessages(c.npc_id)}
                      className={`w-full text-left bg-neutral-900/60 border rounded-xl p-2.5 flex items-center justify-between cursor-pointer transition-colors ${
                        c.is_blocked_contact
                          ? 'border-red-900/60 hover:border-red-700/70'
                          : 'border-neutral-800 hover:border-cyan-500/50'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div
                          className={`w-8 h-8 rounded-full border flex items-center justify-center font-bold text-xs shrink-0 ${
                            c.is_blocked_contact
                              ? 'bg-red-950/60 border-red-800/60 text-red-300'
                              : 'bg-cyan-950/60 border-cyan-800/60 text-cyan-300'
                          }`}
                        >
                          <User size={14} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span
                              className={`font-semibold text-xs truncate ${
                                c.deceased ? 'line-through text-gray-500' : 'text-gray-200'
                              }`}
                            >
                              {c.name}
                            </span>
                            {c.is_blocked_contact && (
                              <span className="text-[8.5px] px-1 py-0.5 rounded bg-red-950/80 text-red-300 border border-red-700/60 font-bold uppercase shrink-0">
                                🚫 {t('contacts.blocked_badge', 'Blocked')}
                              </span>
                            )}
                            {c.anomalous_npc_tag === 'special_agent' && (
                              <span className="text-[8.5px] px-1 py-0.5 rounded bg-cyan-950/70 text-cyan-300 border border-cyan-700/50 font-bold uppercase shrink-0">
                                ⚡ {t('codex.special_agent', 'Special Agent')}
                              </span>
                            )}
                            {c.anomalous_npc_tag === 'civilian' && (
                              <span className="text-[8.5px] px-1 py-0.5 rounded bg-slate-900/80 text-slate-300 border border-slate-700/60 font-semibold uppercase shrink-0">
                                {t('codex.civilian', 'Civilian')}
                              </span>
                            )}
                            {c.deceased && (
                              <span className="text-[8.5px] px-1 py-0.5 rounded bg-rose-950/80 text-rose-300 border border-rose-700/60 font-bold uppercase shrink-0">
                                💀 {t('codex.deceased', 'Deceased')}
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-gray-400 block truncate">{c.role}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {c.score !== null && (
                          <span
                            className={`text-[10px] font-mono tabular-nums flex items-center gap-0.5 ${
                              c.is_blocked_contact ? 'text-red-400' : 'text-pink-400'
                            }`}
                          >
                            <Heart size={10} /> {c.score}
                          </span>
                        )}
                        <ChevronLeft size={14} className="text-gray-500 rotate-180" />
                      </div>
                    </button>
                  ))
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PhoneDmsApp;
