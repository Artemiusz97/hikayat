import {
  Bookmark,
  Check,
  Clock,
  Compass,
  Globe,
  LogIn,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import { formatSaveDate } from '../../utils/timeFormat';
import { formatStature, formatPhysique } from '../../utils/npcDemographics';

export const AdventuresSubModal = ({
  isOpen,
  onClose,
  character,
  activeSlots = [],
  emptySlots = [],
  saves = [],
  loadingSaves = false,
  loadingSessions = false,
  onResume,
  onEnd,
  onStartSlot,
  onLoadSave,
  onDeleteSave,
}) => {
  const { t } = useTranslation();

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('dashboard.adventures_and_saves', 'Adventures & Saves')}
      maxWidthClass="max-w-2xl"
    >
      <div className="px-5 py-4 border-b border-fantasy-border/35 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <Compass size={18} className="text-fantasy-accent shrink-0" />
          <h2 className="hk-display font-bold text-base sm:text-lg text-gray-50 truncate">
            {t('dashboard.adventures_and_saves', 'Adventures & Saves')}
          </h2>
          {character && (
            <span className="hk-chip tabular-nums shrink-0">
              {activeSlots.length} / 6
            </span>
          )}
        </div>
        <MotionButton
          onClick={onClose}
          className="hk-icon-btn shrink-0"
          aria-label={t('common.close', 'Close')}
          title={t('common.close', 'Close')}
        >
          <X size={18} />
        </MotionButton>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-5 py-2">
        {!character ? (
          <div className="py-10 text-center text-sm text-gray-400">
            {t('dashboard.no_character_selected', 'Select or create a character to view adventures.')}
          </div>
        ) : (
          <>
            {/* Active Sessions */}
            <section className="hk-flat-section">
              <div className="flex items-center justify-between gap-2 mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                  {t('dashboard.active_sessions', 'Active Adventures')}
                </h3>
                <span className="text-xs text-gray-500 tabular-nums">
                  {activeSlots.length} / 6
                </span>
              </div>

              {loadingSessions && activeSlots.length === 0 ? (
                <p className="py-4 text-xs text-gray-400 italic">
                  {t('common.loading', 'Loading...')}
                </p>
              ) : activeSlots.length === 0 ? (
                <p className="py-3 text-xs text-gray-400">
                  {t('dashboard.adventures_subtitle', 'Manage active sessions and checkpoints, or embark on a new journey.')}
                </p>
              ) : (
                <ul className="divide-y divide-fantasy-border/25">
                  {activeSlots.map((slot) => {
                    const title =
                      slot.data.scene_title ||
                      slot.data.scenario_display_name ||
                      slot.data.scenario;
                    const snippet =
                      slot.data.narrative_snippet ||
                      t('dashboard.journey_continues', 'Journey continues...');
                    return (
                      <li
                        key={`active-${slot.slotNum}`}
                        className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 min-w-0"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="w-2 h-2 rounded-full bg-fantasy-accent animate-pulse shrink-0" />
                            <span className="text-[11px] font-mono text-fantasy-accent shrink-0">
                              #{slot.slotNum}
                            </span>
                            <span className="font-semibold text-sm text-gray-100 truncate">
                              {title}
                            </span>
                          </div>
                          <p className="text-xs text-gray-400 line-clamp-1 mt-0.5 pl-4">
                            {snippet}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 pl-4 sm:pl-0">
                          <MotionButton
                            onClick={() => {
                              onClose();
                              onResume(slot.data);
                            }}
                            className="hk-btn hk-btn-primary h-8 px-3 text-xs"
                          >
                            <Play size={12} className="fill-current" />
                            <span>{t('dashboard.resume', 'Resume')}</span>
                          </MotionButton>
                          <MotionButton
                            onClick={(e) => onEnd(slot.data.id, e)}
                            className="hk-btn hk-btn-ghost h-8 px-3 text-xs"
                          >
                            {t('dashboard.end', 'End')}
                          </MotionButton>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            {/* Open Slots / Start New Adventure */}
            <section className="hk-flat-section">
              <div className="flex items-center justify-between gap-2 mb-2.5">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                  {t('dashboard.new_adventure', 'New Adventure')}
                </h3>
                <span className="text-xs text-gray-500 tabular-nums">
                  {emptySlots.length} / 6
                </span>
              </div>

              {emptySlots.length > 0 ? (
                <div className="space-y-2.5">
                  <MotionButton
                    onClick={() => {
                      onClose();
                      onStartSlot(emptySlots[0].slotNum);
                    }}
                    className="hk-btn hk-btn-primary w-full sm:w-auto"
                  >
                    <Plus size={15} />
                    <span>{t('dashboard.start_adventure', 'Embark on Adventure')}</span>
                  </MotionButton>

                  <div className="flex flex-wrap items-center gap-1.5">
                    {emptySlots.map((slot) => (
                      <MotionButton
                        key={`empty-${slot.slotNum}`}
                        onClick={() => {
                          onClose();
                          onStartSlot(slot.slotNum);
                        }}
                        className="hk-chip hover:bg-fantasy-accent/20 hover:text-fantasy-accent cursor-pointer h-7 px-2.5 text-xs transition-colors"
                      >
                        #{slot.slotNum}
                      </MotionButton>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-xs text-gray-400">
                  {t(
                    'dashboard.slots_full_hint',
                    'All 6 slots are active — open Adventures & Saves to resume or free a slot.'
                  )}
                </p>
              )}
            </section>

            {/* Saved Checkpoints */}
            <section className="hk-flat-section">
              <div className="flex items-center justify-between gap-2 mb-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
                  <Bookmark size={13} className="text-fantasy-accent" />
                  <span>{t('saves.title', 'Chronicle Checkpoints')}</span>
                </h3>
                {saves.length > 0 && (
                  <span className="text-xs text-gray-500 tabular-nums">
                    {saves.length}
                  </span>
                )}
              </div>

              {loadingSaves && saves.length === 0 ? (
                <p className="py-4 text-xs text-gray-400 italic">
                  {t('saves.loading', 'Loading checkpoints...')}
                </p>
              ) : saves.length === 0 ? (
                <p className="py-3 text-xs text-gray-400">
                  {t('saves.no_saves', 'No saved checkpoints yet.')}
                </p>
              ) : (
                <ul className="divide-y divide-fantasy-border/25">
                  {saves.map((save) => {
                    const slotName =
                      typeof save === 'string' ? save : save.slot_name;
                    const sceneTitle =
                      typeof save === 'object' ? save.scene_title : null;
                    const savedAt =
                      typeof save === 'object' ? save.saved_at : null;
                    return (
                      <li
                        key={save.id || slotName}
                        className="group py-2.5 flex items-center justify-between gap-3 min-w-0"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="font-semibold text-sm text-gray-100 truncate">
                              {slotName}
                            </span>
                            {savedAt && (
                              <span className="hidden sm:inline-flex items-center gap-1 text-[11px] font-mono text-gray-400 shrink-0">
                                <Clock size={10} />
                                {formatSaveDate(savedAt)}
                              </span>
                            )}
                          </div>
                          {sceneTitle && (
                            <p className="text-xs text-gray-400 truncate mt-0.5">
                              {sceneTitle}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <MotionButton
                            onClick={async () => {
                              await onLoadSave(slotName);
                              onClose();
                            }}
                            className="hk-btn hk-btn-ghost h-8 px-3 text-xs text-fantasy-accent"
                          >
                            {t('saves.restore', 'Restore')}
                          </MotionButton>
                          <MotionButton
                            onClick={(e) => onDeleteSave(slotName, e)}
                            className="hk-icon-btn is-danger h-8 min-w-8 hk-hover-reveal"
                            title={t('common.delete', 'Delete')}
                            aria-label={t('common.delete', 'Delete')}
                          >
                            <Trash2 size={14} />
                          </MotionButton>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </AcrylicModal>
  );
};

export const CharactersSubModal = ({
  isOpen,
  onClose,
  character,
  characters = [],
  statPreview = [],
  onSelectCharacter,
  onDeleteCharacter,
  onResumeSession,
  onOpenCreator,
}) => {
  const { t } = useTranslation();

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('dashboard.characters', 'Your Characters')}
      maxWidthClass="max-w-xl"
    >
      <div className="px-5 py-4 border-b border-fantasy-border/35 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <Users size={18} className="text-fantasy-accent shrink-0" />
          <h2 className="hk-display font-bold text-base sm:text-lg text-gray-50 truncate">
            {t('dashboard.characters', 'Your Characters')}
          </h2>
          <span className="hk-chip tabular-nums shrink-0">
            {characters.length} / 6
          </span>
        </div>
        <MotionButton
          onClick={onClose}
          className="hk-icon-btn shrink-0"
          aria-label={t('common.close', 'Close')}
          title={t('common.close', 'Close')}
        >
          <X size={18} />
        </MotionButton>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-5 py-2">
        {character && (
          <section className="hk-flat-section">
            <p className="text-[11px] uppercase tracking-wider text-gray-400 font-semibold">
              {t('dashboard.select_hero', 'Active Character')}
            </p>
            <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="hk-display text-xl sm:text-2xl font-bold text-gray-50 truncate">
                {character.name}
              </h3>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="hk-chip hk-chip-accent">
                  {t('dashboard.level_short', 'Lv')} {character.level}
                </span>
                {character.char_class && (
                  <span className="hk-chip">{character.char_class}</span>
                )}
                {character.race && (
                  <span className="hk-chip">{character.race}</span>
                )}
                {character.gender && (
                  <span className="hk-chip">{character.gender}</span>
                )}
                {(() => {
                  const activeBuild = [
                    formatStature(character.appearance?.stature || character.stature, t),
                    formatPhysique(character.appearance?.physique || character.physique, t),
                  ].filter(Boolean).join(' • ');
                  return activeBuild ? <span className="hk-chip">📐 {activeBuild}</span> : null;
                })()}
              </div>
            </div>

            {statPreview.length > 0 && (
              <div className="mt-3 pt-3 border-t border-fantasy-border/25 grid grid-cols-7 gap-1 text-center">
                {statPreview.map((st) => (
                  <div key={st.label} title={`${st.label}: ${st.val}`}>
                    <div className="text-[10px] font-medium text-gray-400">
                      {st.label}
                    </div>
                    <div className="text-sm sm:text-base font-bold text-gray-100 tabular-nums">
                      {st.val}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="hk-flat-section">
          {characters.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              {t(
                'dashboard.no_character_selected',
                'Select or create a character to view adventures.'
              )}
            </p>
          ) : (
            <ul className="space-y-1">
              {characters.map((c) => {
                const isActive = character?.id === c.id;
                const hasActiveSession = Boolean(c.active_session_id);
                return (
                  <li key={c.id}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => onSelectCharacter(c)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          onSelectCharacter(c);
                        }
                      }}
                      className={`hk-flat-row group cursor-pointer ${
                        isActive ? 'bg-fantasy-accent/15' : ''
                      }`}
                    >
                      <span
                        className={`grid place-items-center w-9 h-9 rounded-full text-sm font-bold shrink-0 ${
                          isActive
                            ? 'bg-fantasy-accent text-black'
                            : 'bg-gray-500/20 text-gray-200'
                        }`}
                      >
                        {(c.name || '?').charAt(0).toUpperCase()}
                      </span>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="font-semibold text-sm text-gray-100 truncate">
                            {c.name}
                          </span>
                          {hasActiveSession && (
                            <span
                              className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0"
                              title={t('dashboard.in_adventure', 'In Adventure')}
                            />
                          )}
                          {isActive && (
                            <Check
                              size={14}
                              className="text-fantasy-accent shrink-0"
                            />
                          )}
                        </div>
                        <div className="text-xs text-gray-400 truncate">
                          {t('dashboard.level_short', 'Lv')} {c.level} ·{' '}
                          {c.char_class}
                          {c.race ? ` · ${c.race}` : ''}
                        </div>
                      </div>

                      {hasActiveSession && (
                        <MotionButton
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (!isActive) await onSelectCharacter(c);
                            onClose();
                            onResumeSession?.();
                          }}
                          className="hk-btn hk-btn-primary h-8 px-3 text-xs shrink-0"
                          title={t('dashboard.resume', 'Resume')}
                        >
                          <Play size={11} className="fill-current" />
                          <span>{t('dashboard.resume', 'Resume')}</span>
                        </MotionButton>
                      )}

                      <MotionButton
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteCharacter(c);
                        }}
                        className="hk-icon-btn is-danger h-8 min-w-8 hk-hover-reveal shrink-0"
                        title={t('common.delete', 'Delete')}
                        aria-label={t('common.delete', 'Delete')}
                      >
                        <Trash2 size={14} />
                      </MotionButton>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>

      {characters.length < 6 && (
        <div className="px-5 py-3.5 border-t border-fantasy-border/35 shrink-0">
          <MotionButton
            onClick={() => {
              onClose();
              onOpenCreator();
            }}
            className="hk-btn hk-btn-primary w-full"
          >
            <Plus size={15} />
            <span>{t('dashboard.create_character', 'Create Character')}</span>
          </MotionButton>
        </div>
      )}
    </AcrylicModal>
  );
};

export const MultiplayerSubModal = ({
  isOpen,
  onClose,
  lobbies = [],
  loadingLobbies = false,
  joinCode,
  setJoinCode,
  onRefreshLobbies,
  onJoinSession,
}) => {
  const { t } = useTranslation();

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('dashboard.multiplayer', 'Multiplayer')}
      maxWidthClass="max-w-lg"
    >
      <div className="px-5 py-4 border-b border-fantasy-border/35 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <Globe size={18} className="text-fantasy-accent shrink-0" />
          <h2 className="hk-display font-bold text-base sm:text-lg text-gray-50 truncate">
            {t('dashboard.multiplayer', 'Multiplayer')}
          </h2>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <MotionButton
            onClick={onRefreshLobbies}
            className="hk-icon-btn"
            title={t('common.refresh', 'Refresh')}
            aria-label={t('common.refresh', 'Refresh')}
          >
            <RefreshCw
              size={15}
              className={loadingLobbies ? 'animate-spin' : ''}
            />
          </MotionButton>
          <MotionButton
            onClick={onClose}
            className="hk-icon-btn"
            aria-label={t('common.close', 'Close')}
            title={t('common.close', 'Close')}
          >
            <X size={18} />
          </MotionButton>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-5 py-3">
        <section className="hk-flat-section !pt-1">
          <form
            className="flex flex-wrap sm:flex-nowrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (joinCode.trim()) {
                onClose();
                onJoinSession(joinCode.trim());
              }
            }}
          >
            <input
              type="text"
              placeholder={t('dashboard.invite_code_placeholder', 'Invite Code...')}
              aria-label={t('dashboard.invite_code_placeholder', 'Invite Code...')}
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
              className="hk-input h-10 flex-1 min-w-0"
            />
            <MotionButton
              type="submit"
              disabled={!joinCode.trim()}
              className="hk-btn hk-btn-primary h-10 px-4 shrink-0"
            >
              <LogIn size={15} />
              <span>{t('dashboard.join', 'Join')}</span>
            </MotionButton>
          </form>
        </section>

        <section className="hk-flat-section">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">
            {t('dashboard.lobbies', 'Public Lobbies')}
          </h3>

          {lobbies.length === 0 ? (
            <p className="py-8 text-center text-xs text-gray-400">
              {t('dashboard.no_lobbies', 'No active lobbies')}
            </p>
          ) : (
            <ul className="divide-y divide-fantasy-border/25">
              {lobbies.map((lobby) => (
                <li
                  key={lobby.id}
                  className="hk-flat-row justify-between min-w-0"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-gray-100 truncate">
                      {lobby.scene_title}
                    </div>
                    <div className="text-xs text-gray-400 truncate">
                      {lobby.host_name}
                    </div>
                  </div>
                  <MotionButton
                    onClick={() => {
                      onClose();
                      onJoinSession(lobby.id);
                    }}
                    className="hk-btn hk-btn-ghost h-8 px-3 text-xs shrink-0"
                  >
                    {t('dashboard.join', 'Join')}
                  </MotionButton>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </AcrylicModal>
  );
};
