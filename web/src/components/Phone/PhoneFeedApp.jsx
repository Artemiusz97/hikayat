import {
  ChevronLeft,
  Heart,
  MessageSquare,
  RefreshCw,
  Rss,
  Search,
  Sparkles,
  UserPlus,
  Users,
} from 'lucide-react';
import { formatCleanLocation } from '../../utils/locationFormat';
import { getAvatarInitial } from './phoneHelpers';

const PhoneFeedApp = ({
  branding,
  socialState,
  feedSubTab,
  onChangeFeedSubTab,
  feedBusy,
  feedBanner,
  onClearFeedBanner,
  onScourRumor,
  onRefreshFeed,
  gossipFeed = [],
  peerQuery,
  onChangePeerQuery,
  peerBusy,
  peerFeedback,
  onClearPeerFeedback,
  peerProfile,
  onSelectPeerProfile,
  onDiscoverPeer,
  onSendFriendRequest,
  suggestedPeers = [],
  contacts = [],
  onOpenChatWithContact,
  t,
}) => {
  return (
    <div className="space-y-2.5">
      {/* Header + Rumor Charges */}
      <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80">
        <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
          <Rss size={15} className="text-purple-400" />
          <span>{branding.feed_app_name || 'NetWire Feed'}</span>
        </h4>
        <span className="text-[10px] font-mono tabular-nums px-2 py-0.5 rounded-full bg-purple-950/50 text-purple-300 border border-purple-700/50 font-semibold">
          ⚡ {socialState?.charges ?? 3}/3 Rumors
        </span>
      </div>

      {/* Sub-view Switcher: Timeline vs PeerPulse People Discovery */}
      <div className="flex bg-neutral-900 p-1 rounded-xl border border-neutral-800 gap-1">
        <button
          type="button"
          onClick={() => onChangeFeedSubTab('timeline')}
          className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
            feedSubTab === 'timeline'
              ? 'bg-purple-600/30 text-purple-200 border border-purple-500/50'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Rss size={12} />
          <span>{t('phone.feed.timeline_and_rumors', 'Timeline & Rumors')}</span>
        </button>
        <button
          type="button"
          onClick={() => onChangeFeedSubTab('peerpulse')}
          className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
            feedSubTab === 'peerpulse'
              ? 'bg-cyan-600/30 text-cyan-200 border border-cyan-500/50'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          <Users size={12} />
          <span>{t('phone.feed.peerpulse_graph', 'PeerPulse Graph')}</span>
        </button>
      </div>

      {/* SUB-VIEW A: TIMELINE & SCOUR RUMORS */}
      {feedSubTab === 'timeline' && (
        <div className="space-y-2.5">
          {/* Action Bar */}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={feedBusy || (socialState?.charges ?? 3) <= 0}
              onClick={onScourRumor}
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
              type="button"
              disabled={feedBusy}
              onClick={onRefreshFeed}
              className="p-1.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 text-gray-300 border border-neutral-800 transition-colors"
              title={t('phone.feed.refresh_timeline', 'Refresh Timeline')}
            >
              <RefreshCw size={13} className={feedBusy ? 'animate-spin text-purple-400' : ''} />
            </button>
          </div>

          {/* Rumor Scour Result Banner */}
          {feedBanner && (
            <div
              className={`p-2.5 rounded-xl text-xs border space-y-1 ${
                feedBanner.type === 'ok'
                  ? 'bg-emerald-950/50 border-emerald-700/60 text-emerald-200'
                  : feedBanner.type === 'error'
                    ? 'bg-red-950/50 border-red-800/60 text-red-200'
                    : 'bg-amber-950/40 border-amber-700/50 text-amber-200'
              }`}
            >
              {feedBanner.title && (
                <div className="font-bold text-[11px] flex justify-between items-center">
                  <span>{feedBanner.title}</span>
                  <button type="button" onClick={onClearFeedBanner} className="text-[10px] opacity-70">
                    ✕
                  </button>
                </div>
              )}
              <p className="text-[11px] leading-snug">{feedBanner.text}</p>
            </div>
          )}

          {gossipFeed.length === 0 ? (
            <div className="text-center py-12 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl">
              <Rss size={28} className="mx-auto opacity-30 text-purple-400 mb-1" />
              <p className="text-xs">{t('phone.feed.quiet_title', 'Feed is quiet right now.')}</p>
              <p className="text-[10px] text-gray-500 mt-1">
                {t('phone.feed.quiet_desc', 'Click Refresh or Scour Rumors to pull live whispers.')}
              </p>
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
                        <div
                          className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs ${
                            isLead
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : 'bg-purple-900/30 text-purple-300 border border-purple-700/40'
                          }`}
                        >
                          {isLead ? '⚡' : getAvatarInitial(post.author_name)}
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className={`font-bold text-xs ${isLead ? 'text-emerald-300' : 'text-gray-200'}`}>
                              {post.author_name}
                            </span>
                            {isLead && (
                              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold">
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
                          <span
                            className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                              isLead
                                ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 font-semibold'
                                : 'bg-purple-950/60 text-purple-300 border border-purple-800/40'
                            }`}
                          >
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
                      ) : (
                        <span />
                      )}
                      {post.likes !== undefined && (
                        <span className="text-[10px] font-mono tabular-nums text-pink-400 flex items-center gap-1">
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
                onChange={(e) => onChangePeerQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && onDiscoverPeer(peerQuery)}
                placeholder={t('phone.peers.search_placeholder', 'Search name or @handle...')}
                className="w-full bg-neutral-900 border border-neutral-800 pl-7 pr-2.5 py-1.5 rounded-xl text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-cyan-500"
              />
            </div>
            <button
              type="button"
              disabled={peerBusy}
              onClick={() => onDiscoverPeer(peerQuery)}
              className="px-2.5 py-1.5 rounded-xl bg-cyan-600/30 hover:bg-cyan-600/40 text-cyan-200 border border-cyan-500/50 text-[11px] font-bold transition-colors shrink-0"
            >
              Lookup
            </button>
          </div>

          <button
            type="button"
            disabled={peerBusy}
            onClick={() => onDiscoverPeer('')}
            className="w-full py-1.5 px-3 rounded-xl bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-xs font-semibold text-cyan-300 flex items-center justify-center gap-1.5 transition-colors"
          >
            <Sparkles size={12} />
            <span>{peerBusy ? 'Scanning Directory...' : 'Discover Suggested Peer'}</span>
          </button>

          {peerFeedback && (
            <div
              className={`p-2.5 rounded-xl text-xs border ${
                peerFeedback.type === 'ok'
                  ? 'bg-emerald-950/50 border-emerald-700/60 text-emerald-200'
                  : peerFeedback.type === 'error'
                    ? 'bg-red-950/50 border-red-800/60 text-red-200'
                    : 'bg-amber-950/50 border-amber-700/60 text-amber-200'
              }`}
            >
              <p className="text-[11px] leading-snug">{peerFeedback.text}</p>
            </div>
          )}

          {/* Discovered Profile Card */}
          {peerProfile ? (
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => {
                  onSelectPeerProfile(null);
                  onClearPeerFeedback();
                }}
                className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-semibold cursor-pointer transition-colors"
              >
                <ChevronLeft size={14} />
                <span>{t('phone.peers.back_to_suggestions', 'Back to Suggestions')}</span>
              </button>

              <div className="bg-neutral-900/90 border border-neutral-800 rounded-2xl p-3.5 space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <h5 className="font-bold text-xs text-gray-100">{peerProfile.name}</h5>
                      {peerProfile.anomalous_npc_tag === 'special_agent' && (
                        <span className="text-[8.5px] px-1 py-0.5 rounded bg-cyan-950/70 text-cyan-300 border border-cyan-700/50 font-bold uppercase">
                          ⚡ {t('codex.special_agent', 'Special Agent')}
                        </span>
                      )}
                      {peerProfile.anomalous_npc_tag === 'civilian' && (
                        <span className="text-[8.5px] px-1 py-0.5 rounded bg-slate-900/80 text-slate-300 border border-slate-700/60 font-semibold uppercase">
                          {t('codex.civilian', 'Civilian')}
                        </span>
                      )}
                    </div>
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
                      📍 {formatCleanLocation(peerProfile.facility, { includeZone: false })}
                    </span>
                  )}
                </div>

                {/* Social Graph Ties & Mutual Friends */}
                {(peerProfile.is_sibling_friend ||
                  peerProfile.shared_club ||
                  (peerProfile.mutual_friends && peerProfile.mutual_friends.length > 0)) && (
                  <div className="pt-1.5 border-t border-neutral-800 space-y-1 text-[10px]">
                    <span className="font-bold uppercase tracking-wider text-cyan-400 block">
                      Social Graph Synergies (CHA Bonus)
                    </span>
                    {peerProfile.is_sibling_friend && (
                      <p className="text-emerald-300">
                        • +4 CHA: Sibling of your contact {peerProfile.sibling_name}
                      </p>
                    )}
                    {peerProfile.shared_club && (
                      <p className="text-purple-300">
                        • +2 CHA: Shared affiliation ({peerProfile.shared_club})
                      </p>
                    )}
                    {peerProfile.mutual_friends?.length > 0 && (
                      <p className="text-cyan-300">• Mutual Friends: {peerProfile.mutual_friends.join(', ')}</p>
                    )}
                  </div>
                )}

                {/* Friend Request Action */}
                <div className="pt-1">
                  {peerProfile.is_already_contact ? (
                    <button
                      type="button"
                      onClick={() => onOpenChatWithContact(peerProfile.npc_id || peerProfile.name)}
                      className="w-full py-2 rounded-xl bg-emerald-950/60 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-700/60 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <MessageSquare size={13} />
                      <span>{t('phone.peers.connected_open_dm', 'Connected — Open Direct Message')}</span>
                    </button>
                  ) : peerProfile.is_faculty ? (
                    <div className="text-center py-1.5 px-2 rounded-xl bg-neutral-950 border border-neutral-800 text-[10px] text-gray-500">
                      🔒 Faculty/Staff accounts cannot be added to student friend circles
                    </div>
                  ) : (
                    <button
                      type="button"
                      disabled={peerBusy || (peerProfile.cooldown_turns_left || 0) > 0}
                      onClick={() => onSendFriendRequest(peerProfile)}
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
                    <span>{t('phone.peers.suggested_peers', 'Suggested Peers & Classmates')}</span>
                  </h5>
                  <p className="text-[10px] text-gray-500">
                    Classmates and mutual peers eligible for friend requests.
                  </p>
                </div>
                {suggestedPeers.length > 0 && (
                  <span className="text-[10px] font-mono tabular-nums px-2 py-0.5 rounded-full bg-cyan-950/60 text-cyan-300 border border-cyan-800/50">
                    {suggestedPeers.length} eligible
                  </span>
                )}
              </div>

              {suggestedPeers.length === 0 ? (
                <div className="text-center py-10 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-1">
                  <Users size={26} className="mx-auto opacity-30 text-cyan-400" />
                  <p className="text-xs text-gray-400">
                    {t('phone.peers.discover_peers', 'Discover Peers & Mutual Connections')}
                  </p>
                  <p className="text-[10px] text-gray-500">
                    Search by name or click "Discover Suggested Peer" to view social profiles and send Friend Requests.
                  </p>
                </div>
              ) : (
                <div className="space-y-2 max-h-[360px] overflow-y-auto pr-0.5 custom-scrollbar">
                  {suggestedPeers.map((peer, idx) => {
                    const isConnected =
                      peer.is_already_contact ||
                      contacts.some((c) => c.name === peer.name || c.id === peer.npc_id);
                    const cooldownLeft = peer.cooldown_turns_left || 0;
                    return (
                      <div
                        key={peer.handle || peer.name || idx}
                        className="bg-neutral-900/90 hover:bg-neutral-900 border border-neutral-800 hover:border-neutral-700/80 rounded-2xl p-3 transition-colors space-y-2"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-900/50 to-blue-900/50 border border-cyan-700/40 flex items-center justify-center font-bold text-xs text-cyan-200 shrink-0">
                              {getAvatarInitial(peer.name)}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <h6 className="font-bold text-xs text-gray-100 truncate">{peer.name}</h6>
                                {peer.anomalous_npc_tag === 'special_agent' && (
                                  <span className="text-[8.5px] px-1 py-0.5 rounded bg-cyan-950/70 text-cyan-300 border border-cyan-700/50 font-bold uppercase shrink-0">
                                    ⚡ {t('codex.special_agent', 'Special Agent')}
                                  </span>
                                )}
                                {peer.anomalous_npc_tag === 'civilian' && (
                                  <span className="text-[8.5px] px-1 py-0.5 rounded bg-slate-900/80 text-slate-300 border border-slate-700/60 font-semibold uppercase shrink-0">
                                    {t('codex.civilian', 'Civilian')}
                                  </span>
                                )}
                              </div>
                              <span className="text-[10px] font-mono text-cyan-400/90 block truncate">
                                {peer.handle}
                              </span>
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
                            type="button"
                            onClick={() => {
                              onSelectPeerProfile(peer);
                              onClearPeerFeedback();
                            }}
                            className="flex-1 py-1.5 rounded-xl bg-neutral-800 hover:bg-neutral-700/80 text-gray-300 border border-neutral-700 text-[11px] font-medium transition-colors"
                          >
                            View Bio
                          </button>
                          {isConnected ? (
                            <button
                              type="button"
                              onClick={() => onOpenChatWithContact(peer.npc_id || peer.name)}
                              className="flex-1 py-1.5 rounded-xl bg-emerald-950/60 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-700/60 text-[11px] font-bold flex items-center justify-center gap-1 transition-colors"
                            >
                              <MessageSquare size={12} />
                              <span>{t('phone.peers.message', 'Message')}</span>
                            </button>
                          ) : (
                            <button
                              type="button"
                              disabled={peerBusy || cooldownLeft > 0}
                              onClick={() => onSendFriendRequest(peer)}
                              className={`flex-1 py-1.5 rounded-xl text-[11px] font-bold flex items-center justify-center gap-1 border transition-all ${
                                cooldownLeft > 0
                                  ? 'bg-neutral-950 text-gray-600 border-neutral-800 cursor-not-allowed'
                                  : 'bg-cyan-600/30 hover:bg-cyan-600/50 text-cyan-200 border-cyan-500/60'
                              }`}
                              title={
                                cooldownLeft > 0
                                  ? `Wait ${cooldownLeft} turns before re-attempting`
                                  : 'Send a friend request (CHA check)'
                              }
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
  );
};

export default PhoneFeedApp;
