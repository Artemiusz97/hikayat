import React, { useState } from 'react';
import { Users, Heart, Zap, UserCheck, Shield, Sparkles, UserMinus, MessageSquare, Send, Share2, Check } from 'lucide-react';
import { apiCall } from '../../api/client';

const MiniBar = ({ label, current, max, color, icon: Icon }) => {
  const safeCurrent = Math.max(0, current || 0);
  const safeMax = Math.max(1, max || 1);
  const pct = Math.min(100, Math.round((safeCurrent / safeMax) * 100));

  return (
    <div className="flex items-center gap-1.5 text-[10px]">
      <div className="flex items-center gap-0.5 text-gray-400 font-bold w-6">
        <Icon size={10} className={color.text} />
        <span>{label}</span>
      </div>
      <div className="flex-1 h-1.5 bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
        <div 
          className={`h-full ${color.bg} transition-all duration-300`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[9px] text-gray-400 min-w-8 text-right font-medium">{safeCurrent}/{safeMax}</span>
    </div>
  );
};

const PartyMemberCard = ({ member, isNpc = false, isSelf = false, isOnline = true, onDismiss, dismissing, onTriggerAction }) => {
  const name = member.name || (isNpc ? 'Companion' : 'Player');
  const role = member.char_class || member.role || (isNpc ? 'Allied Companion' : 'Adventurer');
  const level = member.level || 1;
  const hp = member.hp !== undefined ? member.hp : (member.max_hp || 20);
  const maxHp = member.max_hp || 20;
  const mp = member.mp !== undefined ? member.mp : (member.max_mp || 10);
  const maxMp = member.max_mp || 10;

  // Status effects
  let statusList = [];
  if (Array.isArray(member.status_effects)) {
    statusList = member.status_effects;
  } else if (typeof member.status_effects === 'string' && member.status_effects.trim()) {
    try {
      statusList = JSON.parse(member.status_effects);
    } catch {
      statusList = member.status_effects.split(',').map(s => s.trim()).filter(Boolean);
    }
  }

  return (
    <div className={`p-3 rounded-lg border transition-all ${
      isSelf 
        ? 'bg-fantasy-accent/5 border-fantasy-accent/40 shadow-sm' 
        : 'bg-black/40 border-fantasy-border/60 hover:border-fantasy-border'
    }`}>
      {/* Member Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="relative">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center border text-xs font-bold ${
              isNpc 
                ? 'bg-purple-950/40 border-purple-700/50 text-purple-300' 
                : isSelf 
                  ? 'bg-fantasy-accent/20 border-fantasy-accent text-fantasy-accent' 
                  : 'bg-blue-950/40 border-blue-700/50 text-blue-300'
            }`}>
              {isNpc ? <Sparkles size={13} /> : <UserCheck size={13} />}
            </div>
            {!isNpc && (
              <span
                title={isOnline ? 'Online' : 'Offline'}
                className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border border-black ${
                  isOnline ? 'bg-emerald-400' : 'bg-gray-600'
                }`}
              />
            )}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-xs text-gray-200">{name}</span>
              {isSelf && (
                <span className="text-[9px] px-1 py-0.2 bg-fantasy-accent/20 text-fantasy-accent rounded font-bold uppercase">
                  You
                </span>
              )}
              {isNpc && (
                <span className="text-[9px] px-1 py-0.2 bg-purple-950/60 text-purple-300 rounded font-bold uppercase border border-purple-800/40">
                  NPC
                </span>
              )}
            </div>
            <span className="text-[10px] text-gray-400 font-medium block">
              Lv.{level} {role}
            </span>
          </div>
        </div>

        {isNpc && onDismiss && (
          <button
            disabled={dismissing}
            onClick={() => onDismiss(name)}
            title={`Dismiss ${name} from party`}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-red-950/40 hover:bg-red-900/50 text-red-300 border border-red-800/50 transition-colors"
          >
            <UserMinus size={11} />
            <span>{dismissing ? '...' : 'Dismiss'}</span>
          </button>
        )}
      </div>

      {/* Mini HP & MP Bars */}
      <div className="space-y-1 bg-black/50 p-2 rounded border border-fantasy-border/30">
        <MiniBar 
          label="HP" current={hp} max={maxHp} 
          icon={Heart} color={{ text: 'text-health', bg: 'bg-health' }} 
        />
        <MiniBar 
          label="MP" current={mp} max={maxMp} 
          icon={Zap} color={{ text: 'text-mana', bg: 'bg-mana' }} 
        />
      </div>

      {/* Status Badges */}
      {statusList && statusList.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {statusList.map((eff, i) => {
            const effStr = typeof eff === 'string' ? eff : (eff.name || 'Condition');
            return (
              <span key={i} className="text-[9px] px-1.5 py-0.5 rounded bg-red-950/60 text-red-300 border border-red-800/50 font-medium">
                {effStr}
              </span>
            );
          })}
        </div>
      )}

      {/* Companion Quick-Interaction Buttons */}
      {isNpc && onTriggerAction && (
        <div className="grid grid-cols-3 gap-1.5 mt-2 pt-2 border-t border-fantasy-border/30">
          <button
            type="button"
            onClick={() => onTriggerAction({ custom_action_text: `I chat with ${name} about our current situation and tactics.` })}
            className="px-1.5 py-1 rounded bg-black/60 hover:bg-purple-950/50 text-gray-300 hover:text-purple-200 border border-fantasy-border/60 hover:border-purple-700/60 text-[10px] font-semibold transition-colors truncate"
          >
            💬 Chat & Tactics
          </button>
          <button
            type="button"
            onClick={() => onTriggerAction({ custom_action_text: `I ask ${name} about their personal backstory and past memories.` })}
            className="px-1.5 py-1 rounded bg-black/60 hover:bg-cyan-950/50 text-gray-300 hover:text-cyan-200 border border-fantasy-border/60 hover:border-cyan-700/60 text-[10px] font-semibold transition-colors truncate"
          >
            📖 Backstory
          </button>
          <button
            type="button"
            onClick={() => onTriggerAction({ custom_action_text: `I warmly compliment and flirt with ${name}.` })}
            className="px-1.5 py-1 rounded bg-black/60 hover:bg-pink-950/50 text-gray-300 hover:text-pink-200 border border-fantasy-border/60 hover:border-pink-700/60 text-[10px] font-semibold transition-colors truncate"
          >
            💕 Flirt
          </button>
        </div>
      )}
    </div>
  );
};

const PartyWidget = ({
  session,
  currentUserId,
  characterName,
  onlineUserIds = [],
  partyChatMessages = [],
  onSendPartyChat,
  onSessionUpdated,
  onTriggerAction
}) => {
  const [dismissingNpc, setDismissingNpc] = useState(null);
  const [chatText, setChatText] = useState('');
  const [copiedLink, setCopiedLink] = useState(false);

  if (!session) return null;

  const partyMembers = session.party_members || [];
  const partyNpcs = session.party_npcs || [];

  const totalMembers = partyMembers.length + partyNpcs.length;

  const handleCopyShareLink = async () => {
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
      const inviteMsg = `${shareUrl} (Invite Code: ${session.id})`;
      await navigator.clipboard.writeText(inviteMsg);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2500);
    } catch (e) {
      console.error('Failed to copy share link:', e);
    }
  };

  const handleDismissNpc = async (npcName) => {
    if (!session?.id || !currentUserId) return;
    setDismissingNpc(npcName);
    try {
      const res = await fetch('/api/party/companion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUserId,
          session_id: session.id,
          npc_name: npcName,
          action: 'dismiss',
        }),
      });
      const data = await res.json();
      if (res.ok && onSessionUpdated && Array.isArray(data.party_npcs)) {
        onSessionUpdated({ ...session, party_npcs: data.party_npcs });
      }
    } catch {
      // ignore
    } finally {
      setDismissingNpc(null);
    }
  };

  const handleSendChat = (e) => {
    e.preventDefault();
    if (!chatText.trim() || !onSendPartyChat) return;
    onSendPartyChat(chatText, characterName);
    setChatText('');
  };

  return (
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-fantasy-border pb-3">
        <div>
          <div className="flex items-center gap-2">
            <Users size={16} className="text-fantasy-accent" />
            <h3 className="font-rpg font-bold text-sm text-gray-100 uppercase tracking-wider">Party Roster</h3>
          </div>
          {session.id && (
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] text-gray-500 font-mono">
                Code: <strong className="text-gray-300">{session.id}</strong>
              </span>
              <button
                type="button"
                onClick={handleCopyShareLink}
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-fantasy-accent/15 hover:bg-fantasy-accent/25 border border-fantasy-accent/40 text-fantasy-accent font-medium transition-colors"
                title="Copy shareable link and invite code for friends"
              >
                {copiedLink ? <Check size={10} className="text-green-400" /> : <Share2 size={10} />}
                <span>{copiedLink ? 'Copied Link!' : 'Share Link'}</span>
              </button>
            </div>
          )}
        </div>
        <span className="text-[11px] font-mono font-bold text-fantasy-accent bg-black/60 px-2 py-0.5 rounded border border-fantasy-border">
          {totalMembers} / 4 Members
        </span>
      </div>

      {/* Members List */}
      <div className="space-y-2 max-h-80 overflow-y-auto custom-scrollbar pr-1">
        {/* Human Players */}
        {partyMembers.map(member => {
          const isSelf = member.user_id === currentUserId;
          const isOnline = isSelf || onlineUserIds.length === 0 || onlineUserIds.includes(member.user_id);
          return (
            <PartyMemberCard 
              key={`human-${member.user_id}`} 
              member={member} 
              isSelf={isSelf}
              isOnline={isOnline}
            />
          );
        })}

        {/* Companion NPCs */}
        {partyNpcs.map((npc, idx) => (
          <PartyMemberCard 
            key={`npc-${npc.id || npc.name || idx}`} 
            member={npc} 
            isNpc={true}
            onDismiss={handleDismissNpc}
            dismissing={dismissingNpc === npc.name}
            onTriggerAction={onTriggerAction}
          />
        ))}

        {/* Empty companion slots */}
        {totalMembers < 4 && Array.from({ length: 4 - totalMembers }).map((_, i) => (
          <div 
            key={`empty-${i}`} 
            className="p-3 rounded-lg border border-dashed border-fantasy-border/40 bg-black/20 text-center text-gray-600"
          >
            <span className="text-[11px] italic flex items-center justify-center gap-1">
              <Shield size={12} className="opacity-40" />
              Empty Companion Slot
            </span>
          </div>
        ))}
      </div>

      {/* Real-Time WebSocket Party Chat */}
      <div className="pt-3 border-t border-fantasy-border/60 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider font-bold text-fantasy-accent flex items-center gap-1.5">
            <MessageSquare size={13} />
            <span>Party Chat</span>
          </span>
          <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Live WS
          </span>
        </div>

        <div className="bg-black/50 border border-fantasy-border/60 rounded p-2.5 h-36 overflow-y-auto custom-scrollbar space-y-1.5">
          {partyChatMessages.length === 0 ? (
            <p className="text-[11px] text-gray-500 italic text-center py-10">
              Coordinate tactics or chat with your party in real time...
            </p>
          ) : (
            partyChatMessages.map((msg) => {
              const isMine = msg.user_id === currentUserId;
              return (
                <div key={msg.id} className="text-xs leading-snug">
                  <span className={`font-bold ${isMine ? 'text-fantasy-accent' : 'text-blue-300'}`}>
                    {msg.sender}:
                  </span>{' '}
                  <span className="text-gray-200 break-words">{msg.message}</span>
                </div>
              );
            })
          )}
        </div>

        <form onSubmit={handleSendChat} className="flex gap-1.5">
          <input
            type="text"
            placeholder="Message party..."
            value={chatText}
            onChange={(e) => setChatText(e.target.value)}
            maxLength={240}
            className="flex-1 bg-fantasy-dark border border-fantasy-border px-2.5 py-1.5 rounded text-xs text-gray-100 focus:outline-none focus:border-fantasy-accent"
          />
          <button
            type="submit"
            disabled={!chatText.trim()}
            className="px-2.5 py-1.5 rounded bg-fantasy-accent/20 hover:bg-fantasy-accent/30 text-fantasy-accent border border-fantasy-accent/50 disabled:opacity-40 transition-colors flex items-center justify-center"
            title="Send Party Chat"
          >
            <Send size={13} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default PartyWidget;
