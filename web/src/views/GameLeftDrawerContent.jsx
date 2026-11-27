import { Suspense, lazy } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import CharacterSheet from '../components/Sidebar/CharacterSheet';
import InventoryPanel from '../components/Sidebar/InventoryPanel';
import PartyWidget from '../components/Sidebar/PartyWidget';
import ContactsPanel from '../components/Sidebar/ContactsPanel';
import QuestLogPanel from '../components/Sidebar/QuestLogPanel';
import CodexPanel from '../components/Sidebar/CodexPanel';
import { MotionButton } from '../components/Common/MotionPrimitives';

const WorldMapModal = lazy(() => import('../components/Modals/WorldMapModal'));
const EntityContractsModal = lazy(() => import('../components/Modals/EntityContractsModal'));

const GameLeftDrawerContent = ({
  leftPanel,
  utilityTabs,
  activeUtilityTab,
  setActiveUtilityTab,
  setHudField,
  worldMapTargetLocation,
  setWorldMapTargetLocation,
  setWorldMapExpandedOpen,
  setContractsModalOpen,
  setMerchantModalOpen,
  session,
  user,
  character,
  inventory,
  codex,
  inCombat,
  isStreaming,
  processingTurn,
  onlineUserIds,
  partyChatMessages,
  sendPartyChat,
  allocateStatPoint,
  refreshCharacter,
  handleAction,
  handleFastTravel,
  handleCastSpell,
  handleSessionLoaded,
  handleMessageContact,
  openWorldMap,
  targetContactName,
  setTargetContactName,
  targetContactPulse,
  setTargetContactPulse,
  handleConsumeTargetContact,
}) => {
  const { t } = useTranslation();

  if (leftPanel === 'map') {
    return (
      <Suspense fallback={<div className="p-4 text-xs text-gray-400">{t('common.loading', 'Loading...')}</div>}>
        <WorldMapModal
          mode="drawer"
          isOpen={true}
          onClose={() => {
            setWorldMapTargetLocation(null);
            setHudField('leftPanel', null);
          }}
          onExpandModal={() => {
            setHudField('leftPanel', null);
            setWorldMapExpandedOpen(true);
          }}
          session={session}
          user={user}
          onTravel={handleFastTravel}
          initialTargetLocation={worldMapTargetLocation}
          processingTurn={processingTurn}
        />
      </Suspense>
    );
  }

  const activeTabMeta =
    utilityTabs.find((tb) => tb.id === activeUtilityTab) || utilityTabs[0];

  const renderUtilityContent = () => {
    switch (activeUtilityTab) {
      case 'contracts':
        return (
          <Suspense fallback={<div className="p-4 text-xs text-gray-400">{t('common.loading', 'Loading...')}</div>}>
            <EntityContractsModal
              mode="drawer"
              isOpen={true}
              onClose={() => setHudField('leftPanel', null)}
              onExpandModal={() => {
                setHudField('leftPanel', null);
                setContractsModalOpen(true);
              }}
              session={session}
              user={user}
              onSessionUpdated={handleSessionLoaded}
              onContractMutated={() => {
                refreshCharacter();
                inventory.refreshInventory();
                codex.refreshCodex();
              }}
            />
          </Suspense>
        );
      case 'inventory':
        return (
          <InventoryPanel
            inventoryHook={inventory}
            onRefreshCharacter={refreshCharacter}
            onRefreshCodex={codex.refreshCodex}
            sessionId={session?.id}
            session={session}
            onAction={handleAction}
            inCombat={inCombat}
            currentUserId={user?.user_id}
          />
        );
      case 'party':
        return (
          <PartyWidget
            session={session}
            currentUserId={user?.user_id}
            characterName={character?.name || user?.display_name}
            onlineUserIds={onlineUserIds}
            partyChatMessages={partyChatMessages}
            onSendPartyChat={sendPartyChat}
            onSessionUpdated={handleSessionLoaded}
            onTriggerAction={handleAction}
          />
        );
      case 'contacts':
        return (
          <ContactsPanel
            codexHook={codex}
            session={session}
            user={user}
            onSessionUpdated={handleSessionLoaded}
            onMessageContact={handleMessageContact}
            onJumpToCharacterInCodex={(npcName) => {
              setTargetContactName(npcName);
              setTargetContactPulse((prev) => prev + 1);
              setActiveUtilityTab('codex');
            }}
            targetContactName={targetContactName}
            targetContactPulse={targetContactPulse}
            onConsumeTargetContact={handleConsumeTargetContact}
          />
        );
      case 'quests':
        return (
          <QuestLogPanel
            codexHook={codex}
            onRefreshCharacter={refreshCharacter}
            character={character}
            session={session}
            playerProfile={session?.player_profile || null}
            scenario={session?.scenario || character?.scenario}
            onOpenWorldMap={(targetLoc) => openWorldMap(targetLoc)}
          />
        );
      case 'codex':
        return (
          <CodexPanel
            codexHook={codex}
            session={session}
            user={user}
            onSessionUpdated={handleSessionLoaded}
            onRefreshCharacter={refreshCharacter}
            onOpenMerchant={() => setMerchantModalOpen(true)}
            onTriggerAction={handleAction}
            targetContactName={targetContactName}
            targetContactPulse={targetContactPulse}
            onConsumeTargetContact={handleConsumeTargetContact}
            isStreaming={isStreaming}
            processingTurn={processingTurn}
            onJumpToSavedContact={(npcName) => {
              setTargetContactName(npcName);
              setTargetContactPulse((prev) => prev + 1);
              setActiveUtilityTab('contacts');
            }}
          />
        );
      case 'hero':
      default:
        return (
          <CharacterSheet
            character={
              session?.player_clothing_status && character
                ? {
                    ...character,
                    clothing_status: session.player_clothing_status,
                  }
                : character
            }
            scenario={session?.scenario || character?.scenario}
            playerProfile={session?.player_profile || null}
            onAllocateStat={allocateStatPoint}
            onCastSpell={handleCastSpell}
            onRefreshCharacter={refreshCharacter}
            processingTurn={processingTurn}
          />
        );
    }
  };

  return (
    <div className="flex flex-1 min-h-0 min-w-0 overflow-hidden">
      {/* Vertical Icon Rail */}
      <nav
        aria-label={t('nav.utility', 'Utilities')}
        className="w-[3.25rem] shrink-0 border-r border-fantasy-border/30 py-2.5 flex flex-col items-center gap-1.5"
      >
        {utilityTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeUtilityTab === tab.id;
          return (
            <MotionButton
              key={tab.id}
              onClick={() => setActiveUtilityTab(tab.id)}
              title={tab.label}
              aria-label={tab.label}
              aria-current={isActive ? 'page' : undefined}
              className={`relative w-10 h-10 rounded-xl grid place-items-center transition-colors ${
                isActive
                  ? 'bg-fantasy-accent text-black shadow-sm'
                  : 'text-gray-300 hover:text-gray-50 hover:bg-gray-500/15'
              }`}
            >
              <Icon size={18} />
              {tab.badge != null && (
                <span
                  className={`absolute -top-1 -right-1 min-w-[0.95rem] h-[0.95rem] px-1 rounded-full text-[9px] font-bold leading-[0.95rem] text-center ${
                    tab.badge === '!' || tab.alert
                      ? 'bg-emerald-400 text-black animate-pulse'
                      : isActive
                        ? 'bg-black/80 text-white'
                        : 'bg-gray-600 text-gray-100'
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </MotionButton>
          );
        })}
      </nav>

      {/* Borderless Utility Content Pane */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-fantasy-border/25 flex items-center justify-between gap-2 shrink-0">
          <span className="text-xs font-semibold uppercase tracking-wider text-fantasy-accent truncate">
            {activeTabMeta.label}
          </span>
          <MotionButton
            onClick={() => setHudField('leftPanel', null)}
            className="hk-icon-btn h-7 min-w-7"
            aria-label={t('common.close', 'Close')}
            title={t('common.close', 'Close')}
          >
            <X size={15} />
          </MotionButton>
        </div>
        <div
          className={
            activeUtilityTab === 'contracts'
              ? 'hk-utility-pane flex-1 min-h-0 flex flex-col overflow-hidden'
              : 'hk-utility-pane flex-1 min-h-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable] custom-scrollbar p-3.5 flex flex-col'
          }
        >
          {renderUtilityContent()}
        </div>
      </div>
    </div>
  );
};

export default GameLeftDrawerContent;
