import WorldPulseLoreSubTab from './WorldPulseLoreSubTab';
import EncyclopediaSubTab from './EncyclopediaSubTab';

const CodexLoreTab = ({
  subTab,
  worldPulse,
  filteredLore,
  searchQuery,
  busyRumorId,
  onTrackRumor,
  isStreaming = false,
  processingTurn = false,
  session,
  encyclopedia,
}) => {
  if (subTab === 'encyclopedia') {
    return (
      <EncyclopediaSubTab
        encyclopedia={encyclopedia}
        searchQuery={searchQuery}
      />
    );
  }

  return (
    <WorldPulseLoreSubTab
      worldPulse={worldPulse || session?.world_pulse}
      filteredLore={filteredLore}
      searchQuery={searchQuery}
      busyRumorId={busyRumorId}
      onTrackRumor={onTrackRumor}
      isStreaming={isStreaming}
      processingTurn={processingTurn}
      session={session}
    />
  );
};

export default CodexLoreTab;
