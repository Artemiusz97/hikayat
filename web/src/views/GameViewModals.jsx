import { lazy } from 'react';
import { useTranslation } from 'react-i18next';
import ConfirmDialog from '../components/Common/ConfirmDialog';
import { LazyMount } from '../components/Common/MotionPrimitives';
import { isAnomalousScenarioKey } from '../utils/session';

const PhoneModal = lazy(() => import('../components/Phone/PhoneModal'));
const MerchantModal = lazy(() => import('../components/Merchant/MerchantModal'));
const SavesModal = lazy(() => import('../components/Saves/SavesModal'));
const SettingsModal = lazy(() => import('../components/Settings/SettingsModal'));
const WorldMapModal = lazy(() => import('../components/Modals/WorldMapModal'));
const TurnHistoryModal = lazy(() => import('../components/Modals/TurnHistoryModal'));
const TimeSkipModal = lazy(() => import('../components/Modals/TimeSkipModal'));
const QuickBeltPopover = lazy(() => import('../components/Modals/QuickBeltPopover'));
const GiveGiftModal = lazy(() => import('../components/Modals/GiveGiftModal'));
const ExamineModal = lazy(() => import('../components/Modals/ExamineModal'));
const EntityContractsModal = lazy(() => import('../components/Modals/EntityContractsModal'));

const GameViewModals = ({
  session,
  setSession,
  user,
  character,
  inventory,
  codex,
  phone,
  settings,
  inCombat,
  isStealthActive,
  processingTurn,
  rerollImage,
  rerollingImage,
  handleFastTravel,
  handleAction,
  handleSessionLoaded,
  refreshCharacter,
  historyModalOpen,
  setHistoryModalOpen,
  worldMapExpandedOpen,
  setWorldMapExpandedOpen,
  worldMapTargetLocation,
  setWorldMapTargetLocation,
  merchantModalOpen,
  setMerchantModalOpen,
  phoneModalOpen,
  setPhoneModalOpen,
  phoneInitialNpc,
  setPhoneInitialNpc,
  savesModalOpen,
  setSavesModalOpen,
  settingsModalOpen,
  setSettingsModalOpen,
  examineModalOpen,
  setExamineModalOpen,
  quickBeltModalOpen,
  setQuickBeltModalOpen,
  useItemInitialTarget,
  setUseItemInitialTarget,
  giveGiftModalOpen,
  setGiveGiftModalOpen,
  giveGiftInitialTarget,
  setGiveGiftInitialTarget,
  contractsModalOpen,
  setContractsModalOpen,
  timeSkipModalOpen,
  setTimeSkipModalOpen,
  endSessionConfirmOpen,
  setEndSessionConfirmOpen,
  endingSessionBusy,
  onConfirmEndSession,
}) => {
  const { t } = useTranslation();

  return (
    <>
      {/* Full Turn History Chronicle Modal */}
      <LazyMount open={historyModalOpen}>
        <TurnHistoryModal
          isOpen={historyModalOpen}
          onClose={() => setHistoryModalOpen(false)}
          session={session}
          scenario={session?.scenario || character?.scenario}
          onRerollImage={rerollImage}
          rerollingImage={rerollingImage}
        />
      </LazyMount>

      {/* Expanded Full-Screen World Atlas Modal */}
      <LazyMount open={worldMapExpandedOpen}>
        <WorldMapModal
          mode="modal"
          isOpen={worldMapExpandedOpen}
          onClose={() => {
            setWorldMapExpandedOpen(false);
            setWorldMapTargetLocation(null);
          }}
          session={session}
          user={user}
          onTravel={handleFastTravel}
          initialTargetLocation={worldMapTargetLocation}
          processingTurn={processingTurn}
        />
      </LazyMount>

      {/* Merchant Emporium Modal */}
      <LazyMount open={merchantModalOpen}>
        <MerchantModal
          isOpen={merchantModalOpen}
          onClose={() => setMerchantModalOpen(false)}
          session={session}
          user={user}
          onRefreshCodex={codex.refreshCodex}
          onTransactionComplete={() => {
            refreshCharacter();
            inventory.refreshInventory();
          }}
        />
      </LazyMount>

      {/* Smartphone OS Modal */}
      <LazyMount open={phoneModalOpen}>
        <PhoneModal
          isOpen={phoneModalOpen}
          onClose={() => setPhoneModalOpen(false)}
          phoneHook={phone}
          codexHook={codex}
          session={session}
          user={user}
          inCombat={inCombat}
          imageGenMode={settings.settings?.image_gen_enabled}
          initialChatNpc={phoneInitialNpc}
          onClearInitialChatNpc={() => setPhoneInitialNpc(null)}
          onRefreshInventory={inventory.refreshInventory}
          onRefreshCodex={codex.refreshCodex}
          onRefreshCharacter={refreshCharacter}
        />
      </LazyMount>

      {/* Save / Load Checkpoints Modal */}
      <LazyMount open={savesModalOpen}>
        <SavesModal
          isOpen={savesModalOpen}
          onClose={() => setSavesModalOpen(false)}
          user={user}
          onSessionLoaded={handleSessionLoaded}
        />
      </LazyMount>

      {/* Chronicle Preferences & Streaming Settings Modal */}
      <LazyMount open={settingsModalOpen}>
        <SettingsModal
          isOpen={settingsModalOpen}
          onClose={() => setSettingsModalOpen(false)}
          settingsHook={settings}
          user={user}
          session={session}
          onSessionUpdated={handleSessionLoaded}
          onRefreshCharacter={refreshCharacter}
          onRefreshCodex={codex.refreshCodex}
          onImageModeSaved={(nextMode) => {
            if (
              session &&
              (Number(session.capacity || 1) <= 1 ||
                String(session.host_user_id) === String(user?.user_id))
            ) {
              setSession((prev) => (prev ? { ...prev, image_gen_enabled: nextMode } : prev));
              phone.refreshPhone?.();
            }
          }}
        />
      </LazyMount>

      {/* Zero-Turn Async Examine / Intel Modal */}
      <LazyMount open={examineModalOpen}>
        <ExamineModal
          isOpen={examineModalOpen}
          onClose={() => setExamineModalOpen(false)}
          session={session}
          user={user}
          inCombat={inCombat}
          processing={processingTurn}
          onTargetUseItem={(target) => {
            setExamineModalOpen(false);
            setUseItemInitialTarget(target);
            setQuickBeltModalOpen(true);
          }}
          onTargetGiveGift={(target) => {
            setExamineModalOpen(false);
            setGiveGiftInitialTarget(target);
            setGiveGiftModalOpen(true);
          }}
          onPickupItem={(rawName, displayName) => {
            setExamineModalOpen(false);
            handleAction({
              choice_index: null,
              direct_choice: {
                label: `Pick up ${displayName || rawName}`,
                pickup_item_name: rawName,
                stat: 'FREE',
                requirement: 0,
              },
            });
          }}
          onOpenWorldMap={(locName) => {
            setWorldMapTargetLocation(locName);
            setWorldMapExpandedOpen(true);
          }}
        />
      </LazyMount>

      {/* Contextual Use Item Modal */}
      <LazyMount open={quickBeltModalOpen}>
        <QuickBeltPopover
          isOpen={quickBeltModalOpen}
          onClose={() => setQuickBeltModalOpen(false)}
          items={inventory?.items}
          inventoryHook={inventory}
          session={session}
          character={character}
          currentUserId={user?.user_id}
          presentNpcs={session?.current_npcs || []}
          inCombat={inCombat}
          isStealthActive={isStealthActive}
          initialTarget={useItemInitialTarget}
          onClearInitialTarget={() => setUseItemInitialTarget(null)}
          onAction={handleAction}
          onRefreshCharacter={refreshCharacter}
          processing={processingTurn}
        />
      </LazyMount>

      {/* Give Gift / Transfer Item Modal */}
      <LazyMount open={giveGiftModalOpen}>
        <GiveGiftModal
          isOpen={giveGiftModalOpen}
          onClose={() => setGiveGiftModalOpen(false)}
          items={inventory?.items}
          inventoryHook={inventory}
          session={session}
          presentNpcs={session?.current_npcs || []}
          currentUserId={user?.user_id}
          initialTarget={giveGiftInitialTarget}
          onClearInitialTarget={() => setGiveGiftInitialTarget(null)}
          onAction={handleAction}
          processing={processingTurn}
        />
      </LazyMount>

      {/* Entity Contracts & Devil Pacts Modal */}
      {isAnomalousScenarioKey(session?.scenario) && (
        <LazyMount open={contractsModalOpen}>
          <EntityContractsModal
            isOpen={contractsModalOpen}
            onClose={() => setContractsModalOpen(false)}
            session={session}
            user={user}
            onSessionUpdated={handleSessionLoaded}
            onContractMutated={() => {
              refreshCharacter();
              inventory.refreshInventory();
              codex.refreshCodex();
            }}
          />
        </LazyMount>
      )}

      {/* Chronos Dial Time Skip Modal */}
      <LazyMount open={timeSkipModalOpen}>
        <TimeSkipModal
          isOpen={timeSkipModalOpen}
          onClose={() => setTimeSkipModalOpen(false)}
          session={session}
          phoneHook={phone}
          onAction={handleAction}
          processing={processingTurn}
        />
      </LazyMount>

      <ConfirmDialog
        isOpen={endSessionConfirmOpen}
        onClose={() => setEndSessionConfirmOpen(false)}
        onConfirm={onConfirmEndSession}
        busy={endingSessionBusy}
        tone="danger"
        title={t('dashboard.confirm_end_session_title', 'End Adventure Session?')}
        message={t('dashboard.confirm_end_session', 'End this adventure session?')}
        confirmLabel={t('dashboard.end', 'End')}
      />
    </>
  );
};

export default GameViewModals;
