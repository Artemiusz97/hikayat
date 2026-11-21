import { lazy, useState, useEffect, useCallback } from 'react';
import {
  Bookmark,
  ChevronRight,
  Compass,
  Globe,
  LogOut,
  Play,
  Plus,
  Sliders,
  Sparkles,
  Users,
  X,
} from 'lucide-react';
import { apiCall } from '../api/client';
import { useTranslation } from 'react-i18next';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';
import ThemeSwitcher from '../components/Common/ThemeSwitcher';
import AcrylicModeSwitcher from '../components/Common/AcrylicModeSwitcher';
import HikayatLogoIcon from '../components/Common/HikayatLogoIcon';
import ConfirmDialog from '../components/Common/ConfirmDialog';
import { AcrylicPanel, LazyMount, MotionButton } from '../components/Common/MotionPrimitives';
import {
  AdventuresSubModal,
  CharactersSubModal,
  MultiplayerSubModal,
} from '../components/Menu/MainMenuSubModals';
import { useSettings } from '../hooks/useSettings';

const SettingsModal = lazy(() => import('../components/Settings/SettingsModal'));
const CharacterCreatorModal = lazy(() => import('../components/Character/CharacterCreatorModal'));
const EmbarkationModal = lazy(() => import('../components/Adventure/EmbarkationModal'));

const DashboardView = ({
  user,
  character,
  characters,
  logout,
  createCharacter,
  switchCharacter,
  deleteCharacter,
  startSession,
  joinSession,
  activeSession,
  onResumeSession,
  onResumeSlot,
  onEndSession,
  onEndSlot,
  refreshCharacter,
  refreshSession,
  actionError,
  clearActionError,
  onSessionLoaded,
}) => {
  const { t, i18n } = useTranslation();
  const activeUiLang = (i18n.resolvedLanguage || i18n.language || 'en').slice(0, 2);
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [embarkOpen, setEmbarkOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [activeSubModal, setActiveSubModal] = useState(null); // null | 'adventures' | 'characters' | 'multiplayer'

  const [scenarios, setScenarios] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);

  const [saves, setSaves] = useState([]);
  const [loadingSaves, setLoadingSaves] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState(1);
  const [characterSessions, setCharacterSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const [lobbies, setLobbies] = useState([]);
  const [loadingLobbies, setLoadingLobbies] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const [confirmState, setConfirmState] = useState(null); // { mode: 'delete_save' | 'end_session', target }
  const [confirmBusy, setConfirmBusy] = useState(false);

  const settings = useSettings(user?.user_id);

  const fetchLobbies = useCallback(() => {
    setLoadingLobbies(true);
    apiCall('/api/adventure/lobbies')
      .then((data) => setLobbies(data.lobbies || []))
      .catch(() => {})
      .finally(() => setLoadingLobbies(false));
  }, []);

  const fetchSaves = useCallback(() => {
    if (!user?.user_id || !character?.id) return;
    setLoadingSaves(true);
    apiCall(`/api/saves/${user.user_id}`)
      .then((data) => setSaves(data.saves || []))
      .catch(() => {})
      .finally(() => setLoadingSaves(false));
  }, [user?.user_id, character?.id]);

  const fetchCharacterSessions = useCallback(() => {
    if (!character?.id) {
      setCharacterSessions([]);
      return;
    }
    setLoadingSessions(true);
    apiCall(`/api/adventure/character-sessions/${character.id}`)
      .then((data) => {
        setCharacterSessions(data.sessions || []);
      })
      .catch((err) => {
        console.error('Failed to fetch character sessions:', err);
      })
      .finally(() => {
        setLoadingSessions(false);
      });
  }, [character?.id]);

  useEffect(() => {
    apiCall(`/api/scenarios?lang=${encodeURIComponent(activeUiLang)}`)
      .then((data) => {
        const list =
          data.scenario_list ||
          (Array.isArray(data.scenarios) ? data.scenarios : []);
        if (list.length > 0) setScenarios(list);
      })
      .catch(() => {});

    apiCall(`/api/genres?lang=${encodeURIComponent(activeUiLang)}`)
      .then((data) => {
        const list =
          data.genre_list ||
          data.tag_list ||
          (Array.isArray(data.genres)
            ? data.genres
            : Object.entries(data.genres || {}).map(([key, val]) => ({
                key,
                ...val,
              })));
        if (list.length > 0) setAvailableTags(list);
      })
      .catch(() => {});

    fetchLobbies();
  }, [fetchLobbies, activeUiLang]);

  useEffect(() => {
    fetchSaves();
    fetchCharacterSessions();
  }, [fetchSaves, fetchCharacterSessions, character?.id]);

  const handleEmbark = async (config) => {
    const rawScen = config?.scenario;
    const safeScen =
      rawScen &&
      !['none', 'null', 'undefined'].includes(
        String(rawScen).trim().toLowerCase()
      )
        ? rawScen
        : 'fantasy';
    try {
      await startSession(safeScen, config.mode, {
        ...config,
        scenario: safeScen,
        tags: config.tags,
        capacity: 4,
        slot: config.slot || selectedSlot || 1,
        character_id: character?.id,
      });
      if (refreshCharacter) {
        await refreshCharacter();
      }
      fetchCharacterSessions();
    } catch (err) {
      console.error('Failed to embark from dashboard:', err);
    }
  };

  const handleLoadSave = async (slotName) => {
    try {
      const res = await apiCall('/api/saves/load', {
        method: 'POST',
        body: JSON.stringify({ user_id: user.user_id, slot_name: slotName }),
      });
      if (res.session || res.loaded) {
        if (onSessionLoaded) onSessionLoaded(res.session || res.loaded);
      }
    } catch (e) {
      console.error('Failed to load save', e);
    }
  };

  const handleDeleteSave = (slotName, e) => {
    if (e?.stopPropagation) e.stopPropagation();
    setConfirmState({ mode: 'delete_save', target: slotName });
  };

  const handleDeleteCharacter = (charOrId) => {
    const target =
      typeof charOrId === 'object' && charOrId !== null
        ? charOrId
        : (characters || []).find((ch) => String(ch.id) === String(charOrId)) || {
            id: charOrId,
            name: '',
          };
    setConfirmState({ mode: 'delete_character', target });
  };

  const handleResume = (sess) => {
    if (onResumeSlot) {
      onResumeSlot(sess);
    } else if (onResumeSession) {
      onResumeSession();
    }
  };

  const handleEnd = (sessId, e) => {
    if (e?.stopPropagation) e.stopPropagation();
    setConfirmState({ mode: 'end_session', target: sessId });
  };

  const handleConfirmDialog = async () => {
    if (!confirmState || confirmBusy) return;
    setConfirmBusy(true);
    try {
      if (confirmState.mode === 'delete_save') {
        await apiCall(
          `/api/saves/${user.user_id}/${encodeURIComponent(confirmState.target)}`,
          { method: 'DELETE' }
        );
        fetchSaves();
      } else if (confirmState.mode === 'delete_character') {
        await deleteCharacter(confirmState.target?.id ?? confirmState.target);
        fetchCharacterSessions();
      } else if (confirmState.mode === 'end_session') {
        if (onEndSlot) {
          await onEndSlot(confirmState.target);
        } else if (onEndSession) {
          await onEndSession();
        }
        fetchCharacterSessions();
      }
      setConfirmState(null);
    } catch (err) {
      console.error('Failed to perform confirmed action:', err);
    } finally {
      setConfirmBusy(false);
    }
  };

  const slots = Array.from({ length: 6 }, (_, idx) => {
    const slotNum = idx + 1;
    let found = (characterSessions || []).find(
      (s) => Number(s.slot) === slotNum
    );
    if (
      !found &&
      activeSession &&
      (Number(activeSession.slot) === slotNum ||
        (slotNum === 1 &&
          !characterSessions.some((s) => s.id === activeSession.id)))
    ) {
      found = activeSession;
    }
    if (found) {
      return { type: 'active', data: found, slotNum };
    }
    return { type: 'empty', slotNum };
  });

  const unassigned = (characterSessions || []).filter(
    (s) => !s.slot || s.slot < 1 || s.slot > 6
  );
  if (unassigned.length > 0) {
    let uIdx = 0;
    for (let i = 0; i < slots.length && uIdx < unassigned.length; i++) {
      if (slots[i].type === 'empty') {
        slots[i] = { type: 'active', data: unassigned[uIdx], slotNum: i + 1 };
        uIdx++;
      }
    }
  }

  const activeSlots = slots.filter((s) => s.type === 'active');
  const emptySlots = slots.filter((s) => s.type === 'empty');
  const primaryResumeSlot =
    activeSlots.find((s) => activeSession && s.data?.id === activeSession.id)
      ?.data ||
    activeSlots[0]?.data ||
    null;
  const firstEmptySlotNum = emptySlots[0]?.slotNum || null;

  const statPreview = character
    ? [
        { label: 'STR', val: character.str_ ?? character.str ?? 1 },
        { label: 'PER', val: character.per_ ?? character.per ?? 1 },
        { label: 'END', val: character.end_ ?? character.end ?? 1 },
        { label: 'CHA', val: character.cha ?? 1 },
        { label: 'INT', val: character.int_ ?? character.int ?? 1 },
        { label: 'AGI', val: character.agi ?? 1 },
        { label: 'LUK', val: character.luk ?? 1 },
      ]
    : [];

  const selectCharacter = async (c) => {
    await switchCharacter(c.id);
    if (refreshSession) refreshSession();
  };

  const handleStartNewAdventure = () => {
    if (!character) {
      setCreatorOpen(true);
      return;
    }
    if (firstEmptySlotNum) {
      setSelectedSlot(firstEmptySlotNum);
      setEmbarkOpen(true);
      return;
    }
    setActiveSubModal('adventures');
  };

  const primaryResumeLabel =
    primaryResumeSlot?.scene_title ||
    primaryResumeSlot?.scenario_display_name ||
    primaryResumeSlot?.scenario ||
    '';

  return (
    <div className="h-full w-full overflow-y-auto overflow-x-clip custom-scrollbar text-gray-100 font-sans relative flex flex-col items-center px-4 py-16">
      {/* Top-right floating acrylic utility pill */}
      <div className="fixed top-3 right-3 z-20 hk-acrylic-pill px-2 py-1 flex items-center gap-0.5 max-w-[calc(100dvw-1.5rem)]">
        <span className="hidden sm:inline-flex hk-chip mr-1 max-w-[140px] truncate">
          {user?.display_name ||
            user?.username ||
            t('dashboard.guest', 'Guest')}
        </span>
        <ThemeSwitcher compact />
        <AcrylicModeSwitcher />
        <LanguageSwitcher settingsHook={settings} />
      </div>

      {/* Centered Title + Vertical Main Menu Stack */}
      <main className="my-auto w-full max-w-[26rem] flex flex-col items-center min-w-0">
        {actionError && (
          <div
            role="alert"
            className="w-full mb-3 hk-acrylic-pill border-red-500/50 bg-red-950/75 px-3.5 py-2.5 flex items-center justify-between gap-2 text-xs text-red-200"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-red-400 font-bold shrink-0">
                {t('common.error', 'Error')}:
              </span>
              <span className="break-words min-w-0">{actionError}</span>
            </div>
            {clearActionError && (
              <MotionButton
                onClick={clearActionError}
                aria-label={t('common.close', 'Close')}
                className="hk-icon-btn h-7 min-w-7 text-gray-300 hover:text-white shrink-0"
              >
                <X size={14} />
              </MotionButton>
            )}
          </div>
        )}

        {/* 1. Floating Acrylic Title Card */}
        <AcrylicPanel
          variant="panel"
          origin="top"
          className="w-full px-6 py-5 text-center"
        >
          <div className="grid place-items-center w-12 h-12 rounded-full bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/35 mx-auto mb-3">
            <HikayatLogoIcon size={24} />
          </div>
          <h1 className="hk-display text-3xl sm:text-4xl font-bold text-gray-50 truncate">
            {t('nav.title', 'Hikayat')}
          </h1>
          <p className="text-xs sm:text-sm text-gray-300 mt-1 text-balance">
            {t('dashboard.chronicles_console', 'Living Chronicles · Interactive RPG')}
          </p>

          <div className="hk-divider my-3.5" />

          {character ? (
            <MotionButton
              onClick={() => setActiveSubModal('characters')}
              className="hk-flat-row w-full justify-between text-left"
              title={t('dashboard.characters', 'Your Characters')}
            >
              <div className="flex items-center gap-2.5 min-w-0 flex-1">
                <span className="grid place-items-center w-8 h-8 rounded-full bg-fantasy-accent text-black text-xs font-bold shrink-0">
                  {(character.name || '?').charAt(0).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-gray-100 truncate">
                    {character.name}
                  </div>
                  <div className="text-[11px] text-gray-400 truncate">
                    {t('dashboard.level_short', 'Lv')} {character.level} ·{' '}
                    {character.char_class}
                  </div>
                </div>
              </div>
              <ChevronRight size={15} className="text-gray-400 shrink-0" />
            </MotionButton>
          ) : (
            <MotionButton
              onClick={() => setCreatorOpen(true)}
              className="hk-flat-row w-full justify-between text-left text-fantasy-accent"
            >
              <div className="flex items-center gap-2.5 min-w-0 flex-1">
                <span className="grid place-items-center w-8 h-8 rounded-full bg-fantasy-accent/15 text-fantasy-accent shrink-0">
                  <Sparkles size={15} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold truncate">
                    {t('dashboard.no_active_character', 'No character selected')}
                  </div>
                  <div className="text-[11px] text-gray-400 truncate">
                    {t('dashboard.create_character', 'New Character')}
                  </div>
                </div>
              </div>
              <Plus size={15} className="shrink-0" />
            </MotionButton>
          )}
        </AcrylicPanel>

        {/* 2. Floating Acrylic Vertical Menu Card */}
        <AcrylicPanel
          variant="panel"
          origin="bottom"
          className="w-full mt-4 p-2.5 sm:p-3 space-y-0.5"
        >
          {character && primaryResumeSlot && (
            <MotionButton
              onClick={() => handleResume(primaryResumeSlot)}
              className="hk-flat-row w-full justify-between text-left bg-fantasy-accent/15 hover:bg-fantasy-accent/25 text-fantasy-accent"
            >
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <span className="grid place-items-center w-8 h-8 rounded-lg bg-fantasy-accent text-black shrink-0">
                  <Play size={14} className="fill-current" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-sm font-semibold">
                    <span className="truncate">
                      {t('dashboard.continue_adventure', 'Resume Adventure')}
                    </span>
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                  </div>
                  {primaryResumeLabel && (
                    <div className="text-[11px] text-gray-300 truncate">
                      {primaryResumeLabel}
                    </div>
                  )}
                </div>
              </div>
              <ChevronRight size={16} className="shrink-0 opacity-80" />
            </MotionButton>
          )}

          <MotionButton
            onClick={handleStartNewAdventure}
            className="hk-flat-row w-full justify-between text-left text-gray-100"
          >
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Compass size={17} className="text-fantasy-accent shrink-0" />
              <span className="text-sm font-medium truncate">
                {t('dashboard.new_adventure', 'New Adventure')}
              </span>
            </div>
            <Plus size={15} className="text-gray-400 shrink-0" />
          </MotionButton>

          <MotionButton
            onClick={() => setActiveSubModal('adventures')}
            className="hk-flat-row w-full justify-between text-left text-gray-100"
          >
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Bookmark size={17} className="text-fantasy-accent shrink-0" />
              <span className="text-sm font-medium truncate">
                {t('dashboard.adventures_and_saves', 'Adventures & Saves')}
              </span>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="hk-chip tabular-nums">
                {activeSlots.length}/6
              </span>
              {saves.length > 0 && (
                <span className="hk-chip hk-chip-accent tabular-nums">
                  {saves.length}
                </span>
              )}
            </div>
          </MotionButton>

          <MotionButton
            onClick={() => setActiveSubModal('characters')}
            className="hk-flat-row w-full justify-between text-left text-gray-100"
          >
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Users size={17} className="text-fantasy-accent shrink-0" />
              <span className="text-sm font-medium truncate">
                {t('dashboard.characters', 'Your Characters')}
              </span>
            </div>
            <span className="hk-chip tabular-nums shrink-0">
              {characters.length}/6
            </span>
          </MotionButton>

          <MotionButton
            onClick={() => setActiveSubModal('multiplayer')}
            className="hk-flat-row w-full justify-between text-left text-gray-100"
          >
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Globe size={17} className="text-fantasy-accent shrink-0" />
              <span className="text-sm font-medium truncate">
                {t('dashboard.multiplayer', 'Multiplayer')}
              </span>
            </div>
            {lobbies.length > 0 && (
              <span className="hk-chip hk-chip-accent tabular-nums shrink-0">
                {lobbies.length}
              </span>
            )}
          </MotionButton>

          <div className="hk-divider my-1.5" />

          <MotionButton
            onClick={() => setSettingsModalOpen(true)}
            className="hk-flat-row w-full justify-between text-left text-gray-200"
          >
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Sliders size={17} className="text-gray-400 shrink-0" />
              <span className="text-sm font-medium truncate">
                {t('nav.settings', 'Settings')}
              </span>
            </div>
          </MotionButton>

          <MotionButton
            onClick={logout}
            className="hk-flat-row w-full justify-between text-left text-red-400 hover:bg-red-500/10"
          >
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <LogOut size={17} className="shrink-0" />
              <span className="text-sm font-medium truncate">
                {t('dashboard.logout', 'Log Out')}
              </span>
            </div>
          </MotionButton>
        </AcrylicPanel>
      </main>

      {/* Main Menu Sub-Modals */}
      <AdventuresSubModal
        isOpen={activeSubModal === 'adventures'}
        onClose={() => setActiveSubModal(null)}
        character={character}
        activeSlots={activeSlots}
        emptySlots={emptySlots}
        saves={saves}
        loadingSaves={loadingSaves}
        loadingSessions={loadingSessions}
        onResume={handleResume}
        onEnd={handleEnd}
        onStartSlot={(slotNum) => {
          setSelectedSlot(slotNum);
          setEmbarkOpen(true);
        }}
        onLoadSave={handleLoadSave}
        onDeleteSave={handleDeleteSave}
      />

      <CharactersSubModal
        isOpen={activeSubModal === 'characters'}
        onClose={() => setActiveSubModal(null)}
        character={character}
        characters={characters}
        statPreview={statPreview}
        onSelectCharacter={selectCharacter}
        onDeleteCharacter={handleDeleteCharacter}
        onResumeSession={onResumeSession}
        onOpenCreator={() => setCreatorOpen(true)}
      />

      <MultiplayerSubModal
        isOpen={activeSubModal === 'multiplayer'}
        onClose={() => setActiveSubModal(null)}
        lobbies={lobbies}
        loadingLobbies={loadingLobbies}
        joinCode={joinCode}
        setJoinCode={setJoinCode}
        onRefreshLobbies={fetchLobbies}
        onJoinSession={joinSession}
      />

      <LazyMount open={creatorOpen}>
        <CharacterCreatorModal
          isOpen={creatorOpen}
          onClose={() => setCreatorOpen(false)}
          onCreateCharacter={createCharacter}
        />
      </LazyMount>

      <LazyMount open={embarkOpen}>
        <EmbarkationModal
          isOpen={embarkOpen}
          onClose={() => setEmbarkOpen(false)}
          character={character}
          scenarios={scenarios}
          availableTags={availableTags}
          targetSlot={selectedSlot}
          onEmbark={handleEmbark}
        />
      </LazyMount>

      <LazyMount open={settingsModalOpen}>
        <SettingsModal
          isOpen={settingsModalOpen}
          onClose={() => setSettingsModalOpen(false)}
          settingsHook={settings}
          user={user}
        />
      </LazyMount>

      <ConfirmDialog
        isOpen={Boolean(confirmState)}
        onClose={() => setConfirmState(null)}
        onConfirm={handleConfirmDialog}
        busy={confirmBusy}
        tone="danger"
        title={
          confirmState?.mode === 'delete_save'
            ? t('dashboard.confirm_delete_save_title', 'Delete Checkpoint?')
            : confirmState?.mode === 'delete_character'
              ? t('dashboard.confirm_delete_char_title', 'Delete Character?')
              : t('dashboard.confirm_end_session_title', 'End Adventure Session?')
        }
        message={
          confirmState?.mode === 'delete_save'
            ? t('dashboard.confirm_delete_save_msg', {
                slot: confirmState?.target || '',
                defaultValue: `Delete checkpoint "${confirmState?.target || ''}"?`,
              })
            : confirmState?.mode === 'delete_character'
              ? t('dashboard.confirm_delete_char_msg', {
                  name: confirmState?.target?.name || '',
                  defaultValue: `Permanently delete "${confirmState?.target?.name || ''}" and all associated adventure progress?`,
                })
              : t('dashboard.confirm_end_session', 'End this adventure session?')
        }
        confirmLabel={
          confirmState?.mode === 'delete_save' || confirmState?.mode === 'delete_character'
            ? t('saves.delete', 'Delete')
            : t('dashboard.end', 'End')
        }
      />
    </div>
  );
};

export default DashboardView;
