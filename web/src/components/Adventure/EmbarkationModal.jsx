import { useState, useEffect, useMemo, useId, useRef } from 'react';
import { copyToClipboard } from '../../utils/clipboard';
import { X, Sparkles, Shield, Compass, RefreshCw, Check, Link, Play, Building2, Briefcase, Landmark, Smartphone, Eye, KeyRound } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiCall } from '../../api/client';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import {
  REAR_SIZE_OPTIONS,
  classifyAssetSizeTierClient,
  classifyRearSizeTierClient,
  formatAssetTexture,
  formatRearSizeLabel,
  formatRearTexture,
  getAllowedRearTextureOptions,
  getAllowedTextureOptions,
  getSpeciesSurfaceClient,
  healRearTextureForSelection,
  healTextureForSelection,
  isFeralRearExcluded,
  isMaleGender,
  rollClientAssetTexture,
  rollClientRearTexture,
} from '../../utils/anatomyOptions';

const STAT_KEYS = [
  { key: 'str', code: 'STR', label: 'Strength' },
  { key: 'per', code: 'PER', label: 'Perception' },
  { key: 'end', code: 'END', label: 'Endurance' },
  { key: 'cha', code: 'CHA', label: 'Charisma' },
  { key: 'int', code: 'INT', label: 'Intelligence' },
  { key: 'agi', code: 'AGI', label: 'Agility' },
  { key: 'luk', code: 'LUK', label: 'Luck' },
];

function computeClassPreset(className = '', classDesc = '') {
  const text = `${className} ${classDesc}`.toLowerCase();
  if (/mage|wizard|sorcerer|warlock|arcan|scholar|psion|netrunner|alchemist|hacker|technolog|esper|scribe|investigator|ordnance specialist|countermeasure tech|tester|tinkerer/.test(text)) return { str: 1, per: 2, end: 2, cha: 1, int: 4, agi: 1, luk: 1 };
  if (/rogue|thief|assassin|ranger|scout|sniper|infiltrator|smuggler|delinquent|marksman|overwatch|telemetry specialist|licensed field specialist|wetwork|stalker|runner|trouble-shooter/.test(text)) return { str: 1, per: 3, end: 1, cha: 1, int: 1, agi: 3, luk: 2 };
  if (/paladin|knight|templar|guardian|vanguard|enforcer|juggernaut|breacher|entry specialist|recovery operator|engineer|warden|strike operator|perimeter guard/.test(text)) return { str: 3, per: 1, end: 3, cha: 2, int: 1, agi: 1, luk: 1 };
  if (/bard|diplomat|idol|president|noble|social|merchant|cleric|healer|priest|ritualist|broker|exorcist|escort|containment agent|containment specialist/.test(text)) return { str: 1, per: 1, end: 2, cha: 4, int: 2, agi: 1, luk: 1 };
  return { str: 3, per: 1, end: 3, cha: 1, int: 1, agi: 2, luk: 1 };
}

const BREAST_SIZE_LABELS = {
  flat: ['character.breast_flat', 'Flat (AA-Cup / Barely There)'],
  small: ['character.breast_petite', 'Petite / Modest (A-B Cup)'],
  average: ['character.breast_proportional', 'Proportional (C-Cup)'],
  large: ['character.breast_voluptuous', 'Voluptuous / Full (D-DD Cup)'],
  huge: ['character.breast_bountiful', 'Bountiful / Massive (E+ Cup)'],
};

const PENIS_SIZE_LABELS = {
  small: ['character.penis_compact', 'Petite / Modest (Compact)'],
  average: ['character.penis_average', 'Proportional (Average)'],
  large: ['character.penis_large', 'Well-Endowed / Formidable (Large)'],
  huge: ['character.penis_huge', 'Massive / Heavy (Huge)'],
};

const EmbarkationModal = ({ isOpen, onClose, character, onEmbark, scenarios = [], availableTags = [], targetSlot = 1 }) => {
  const { t, i18n } = useTranslation();
  const activeUiLang = (i18n.resolvedLanguage || i18n.language || 'en').slice(0, 2);
  const factionFieldId = useId();
  const [step, setStep] = useState(1);
  const [scenario, setScenario] = useState(() => {
    const cScen = character?.scenario;
    return (cScen && !['none', 'null', 'undefined'].includes(String(cScen).trim().toLowerCase())) ? cScen : 'fantasy';
  });
  const [customTags, setCustomTags] = useState(['fantasy']);
  const [charClass, setCharClass] = useState(character?.char_class || 'Warrior');
  const [startingWeapon, setStartingWeapon] = useState('Rusty Sword');
  const [startingFaction, setStartingFaction] = useState('public_agency');
  const [originMode, setOriginMode] = useState('student');
  const [studentGrade, setStudentGrade] = useState('Sophomore');
  const [attribute, setAttribute] = useState(character?.attribute || 'fire');
  const [combatArchetype, setCombatArchetype] = useState(character?.combat_archetype || 'vanguard');
  const [abilityMedium, setAbilityMedium] = useState(character?.ability_medium || 'direct_manifestation');
  const [previewStartingItems, setPreviewStartingItems] = useState(null);
  
  const [templates, setTemplates] = useState(null);
  const [_loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({ str: 1, per: 1, end: 1, cha: 1, int: 1, agi: 1, luk: 1 });
  const [regeneratedLoadout, setRegeneratedLoadout] = useState(null);
  const [regeneratingGear, setRegeneratingGear] = useState(false);
  
  const [breastSize, setBreastSize] = useState('average');
  const [penisSize, setPenisSize] = useState('average');
  const [assetTexture, setAssetTexture] = useState('');
  const [rearSize, setRearSize] = useState('average');
  const [rearTexture, setRearTexture] = useState('');
  // Collapsed to a summary when the character already has saved anatomy (set on a previous NSFW embark).
  const [anatomyExpanded, setAnatomyExpanded] = useState(false);

  // Step 2 variables
  const [mode, setMode] = useState('solo'); // solo, turn, sync
  const [shareLink, setShareLink] = useState('');
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef(null);
  const isMountedRef = useRef(true);
  const gearAbortRef = useRef(null);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      if (gearAbortRef.current) {
        try {
          gearAbortRef.current.abort();
        } catch {}
      }
    };
  }, []);

  const isNsfw = useMemo(() => {
    if (scenario === 'nsfw_high_school_drama' || String(scenario).toLowerCase().includes('nsfw')) return true;
    if (scenario === 'custom' && customTags.includes('nsfw')) return true;
    const scenObj = scenarios.find(s => s.key === scenario);
    if (scenObj?.tags?.includes('nsfw')) return true;
    return false;
  }, [scenario, customTags, scenarios]);

  const familyRootOf = (s) => s?.family_root || s?.key;
  const familyRoots = useMemo(() => scenarios.filter(s => familyRootOf(s) === s.key), [scenarios]);
  const activeFamily = useMemo(() => {
    if (scenario === 'custom') return 'custom';
    const scenObj = scenarios.find(s => s.key === scenario);
    return scenObj ? familyRootOf(scenObj) : scenario;
  }, [scenario, scenarios]);
  const familyVariants = useMemo(
    () => (activeFamily === 'custom' ? [] : scenarios.filter(s => familyRootOf(s) === activeFamily)),
    [activeFamily, scenarios]
  );

  const isMale = useMemo(() => isMaleGender(character?.gender), [character?.gender]);
  const feralRearExcluded = useMemo(() => isFeralRearExcluded(character?.race), [character?.race]);

  useEffect(() => {
    let cancelled = false;
    const publicUrlController = new AbortController();
    if (isOpen && character) {
      setStats({
        str: character.str_ ?? character.str ?? 1,
        per: character.per_ ?? character.per ?? 1,
        end: character.end_ ?? character.end ?? 1,
        cha: character.cha ?? 1,
        int: character.int_ ?? character.int ?? 1,
        agi: character.agi ?? 1,
        luk: character.luk ?? 1
      });
      const appObj = character.appearance || {};
      const rawBSize = appObj.breast_size || character.breast_size || 'average';
      const rawPSize = appObj.penis_size || character.penis_size || 'average';
      const bTier = classifyAssetSizeTierClient(rawBSize, false);
      const pTier = classifyAssetSizeTierClient(rawPSize, true);
      setBreastSize(bTier);
      setPenisSize(pTier);
      const rawTex = appObj.asset_texture || character.asset_texture || '';
      const activeTier = isMale ? pTier : bTier;
      const curTex = healTextureForSelection(rawTex, isMale, activeTier);
      setAssetTexture(curTex);
      const rawRSize = appObj.rear_size || character.rear_size || 'average';
      const rTier = classifyRearSizeTierClient(rawRSize);
      setRearSize(rTier);
      const rawRTex = appObj.rear_texture || character.rear_texture || '';
      setRearTexture(healRearTextureForSelection(rawRTex, rTier));
      setAnatomyExpanded(!(appObj.breast_size || appObj.penis_size || appObj.rear_size || character.breast_size || character.penis_size || character.rear_size));
      setAttribute(character.attribute || 'fire');
      setCombatArchetype(character.combat_archetype || 'vanguard');
      setAbilityMedium(character.ability_medium || 'direct_manifestation');
      if (character.scenario && !['none', 'null', 'undefined'].includes(String(character.scenario).trim().toLowerCase())) {
        setScenario(character.scenario);
      }
      setStep(1);
      
      // Fetch share link in background
      apiCall('/api/server/public-url', { signal: publicUrlController.signal }).then(res => {
        const publicUrl = res?.public_url || res?.url || '';
        if (!cancelled && publicUrl) setShareLink(publicUrl);
      }).catch((err) => {
        if (err?.name === 'AbortError' || err?.isUserAbort || cancelled) return;
      });
    }
    return () => {
      cancelled = true;
      publicUrlController.abort();
    };
  }, [isOpen, character, isMale]);

  const tagsParam = useMemo(() => (scenario === 'custom' ? customTags.join(',') : ''), [scenario, customTags]);
  const charClassRef = useRef(charClass);
  charClassRef.current = charClass;

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    const query = scenario === 'custom' 
      ? `/api/class-templates?scenario=custom&tags=${encodeURIComponent(tagsParam || 'fantasy')}&lang=${encodeURIComponent(activeUiLang)}`
      : `/api/class-templates?scenario=${encodeURIComponent(scenario || 'fantasy')}&lang=${encodeURIComponent(activeUiLang)}`;

    apiCall(query, { signal: controller.signal })
      .then((data) => {
        if (cancelled) return;
        setTemplates(data);
        const activeClassesObj = data?.classes || {};
        const classNames = Object.keys(activeClassesObj);
        if (classNames.length > 0 && !classNames.includes(charClassRef.current)) {
          setCharClass(classNames[0]);
        }
        setRegeneratedLoadout(null);
      })
      .catch((err) => {
        if (err?.name === 'AbortError' || err?.isUserAbort || cancelled) return;
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [isOpen, scenario, tagsParam, activeUiLang]);

  const isAnomalousHighSchool = useMemo(() => {
    if (templates?.is_anomalous_high_school) return true;
    const scenStr = String(scenario || '').toLowerCase();
    return [
      'anomalous_high_school',
      'nsfw_gore_anomalous_high_school',
      'furry_anomalous_high_school',
      'nsfw_furry_gore_anomalous_high_school',
    ].includes(scenStr);
  }, [templates, scenario]);

  const isAnomalousIncursions = useMemo(() => {
    if (templates?.is_anomalous_incursions) return true;
    const scenStr = String(scenario || '').toLowerCase();
    return [
      'anomalous_incursions',
      'nsfw_gore_anomalous_incursions',
      'furry_anomalous_incursions',
      'nsfw_furry_gore_anomalous_incursions',
      'urban_anomalies',
      'anomalous_high_school',
      'nsfw_gore_anomalous_high_school',
      'furry_anomalous_high_school',
      'nsfw_furry_gore_anomalous_high_school',
    ].includes(scenStr);
  }, [templates, scenario]);

  const isNonCombat = useMemo(() => {
    if (isAnomalousIncursions) return false;
    if (templates?.is_non_combat) return true;
    if (scenario === 'custom' && (customTags.includes('non_combat') || customTags.includes('non-combat'))) return true;
    const scenStr = String(scenario || '').toLowerCase();
    if (scenStr.includes('high_school') || scenStr.includes('school')) return true;
    const scenObj = scenarios.find(s => s.key === scenario);
    if (scenObj?.tags?.some(t => t === 'non_combat' || t === 'non-combat')) return true;
    return false;
  }, [isAnomalousIncursions, templates, scenario, customTags, scenarios]);

  const effectiveFaction = useMemo(() => {
    if (isAnomalousHighSchool && originMode === 'student') {
      return 'student_freelancer';
    }
    return startingFaction || 'public_agency';
  }, [isAnomalousHighSchool, originMode, startingFaction]);

  const anomalousFactionOptions = useMemo(() => [
    {
      id: 'public_agency',
      Icon: Landmark,
      isDefault: true,
      name: t('embark.faction_public_name', 'Public Containment Agency'),
      desc: t('embark.faction_public_desc', 'Daily Salary (₵50–₵300) • 50% HQ Shop Discount • Mandatory Daily Bounty • ₵0/0 Loot on Agency Bounties • Starts at Bureau HQ'),
    },
    {
      id: 'private_agency_1',
      Icon: Building2,
      isDefault: false,
      name: t('embark.faction_private_name', 'Corporate Containment Conglomerate'),
      desc: t('embark.faction_private_desc', 'Keep 100% Bounty Credits & Loot • Special Ordnance Vault (+35% Price) • Public Contracts Allowed • Mandatory Daily Bounty • Starts at Tower HQ'),
    },
    {
      id: 'private_agency_2',
      Icon: Briefcase,
      isDefault: false,
      name: t('embark.faction_private_2_name', 'Independent Private Agency'),
      desc: t('embark.faction_private_2_desc', 'Keep 100% Bounty Credits & Loot • Custom Gunsmith & Broker Armory (+35% Price) • Public Contracts Allowed • Mandatory Daily Bounty • Starts at Field Office HQ'),
    },
    {
      id: 'monastic_order',
      Icon: Sparkles,
      isDefault: false,
      name: t('embark.faction_monastic_name', 'Monastic Shrine Order'),
      desc: t('embark.faction_monastic_desc', '2–3 Free Sacred Items Daily • Keep Combat Loot (₵0 Order Fee) • Free Temple Healing • Mandatory Daily Bounty • Starts at Grand Temple'),
    },
    {
      id: 'cult_faction',
      Icon: Eye,
      isDefault: false,
      name: t('embark.faction_cult_name', 'Occult Cult Sanctum'),
      desc: t('embark.faction_cult_desc', '0.85x Reliquary Tithe • -50% Pact Offering Costs • +1 Daily Resonator Charge • Free Apotheca Extraction • Blacklisted from Licensed Agencies • Starts at Sanctum Threshold'),
    },
    {
      id: 'clandestine_faction',
      Icon: KeyRound,
      isDefault: false,
      name: t('embark.faction_clandestine_name', 'Clandestine Relic Syndicate'),
      desc: t('embark.faction_clandestine_desc', '+35% Syndicate Bounty Cash • +40% Fence Loot Resale • Auto-Revealed Anomaly Dossiers • +25% Harvest Credits • Blacklisted from Licensed Agencies • Starts at Vault Threshold'),
    },
    {
      id: 'freelancer',
      Icon: Smartphone,
      isDefault: false,
      name: t('embark.faction_freelancer_name', 'Independent Freelancer'),
      desc: t('embark.faction_freelancer_desc', 'No Mandatory Daily Quotas • Full Payouts on Public Contracts & Freelance App • Starts at Suburb Home'),
    },
  ], [t]);

  const activeClassesMap = useMemo(() => {
    if (isAnomalousIncursions && templates?.faction_classes?.[effectiveFaction]) {
      return templates.faction_classes[effectiveFaction];
    }
    return templates?.classes || {};
  }, [isAnomalousIncursions, templates, effectiveFaction]);

  const activeClassInfo = useMemo(
    () => activeClassesMap[charClass] || {},
    [activeClassesMap, charClass]
  );
  
  const weaponsList = useMemo(() => {
    if (isAnomalousIncursions && templates?.faction_starting_weapons?.[effectiveFaction]) {
      return templates.faction_starting_weapons[effectiveFaction];
    }
    const rawList = (templates?.starting_weapons || []).map(w => typeof w === 'object' ? w.name : w);
    return rawList.length > 0 ? rawList : ['Rusty Sword', 'Oak Staff', 'Hunting Bow', 'Iron Dagger'];
  }, [isAnomalousIncursions, templates, effectiveFaction]);

  useEffect(() => {
    const classNames = Object.keys(activeClassesMap);
    if (classNames.length > 0 && !classNames.includes(charClass)) {
      setCharClass(classNames[0]);
    }
  }, [activeClassesMap, charClass]);

  useEffect(() => {
    if (weaponsList.length > 0 && !weaponsList.includes(startingWeapon)) {
      setStartingWeapon(weaponsList[0]);
    }
  }, [weaponsList, startingWeapon]);

  const weaponsDisplayMap = useMemo(
    () => templates?.starting_weapons_localized || {},
    [templates?.starting_weapons_localized]
  );

  const displayedLoadout = useMemo(() => {
    const resolveGenderSlashLabel = (labelStr) => {
      if (!labelStr || !String(labelStr).includes(' / ')) return labelStr;
      const parts = String(labelStr).split(' / ').map((s) => s.trim());
      if (parts.length === 2) return isMale ? parts[1] : parts[0];
      return labelStr;
    };
    let loadout = {};
    const locGear = activeClassInfo?.starter_gear_localized || {};
    if (regeneratedLoadout) {
      loadout = { ...regeneratedLoadout };
    } else {
      const rawGear = activeClassInfo?.starter_gear || {};
      Object.entries(rawGear).forEach(([slot, entry]) => {
        if (slot === 'Weapon' || !entry) return;
        if (isNonCombat && (slot === 'Shield' || slot === 'Armor')) return;
        if (Array.isArray(entry) && entry.length >= 1) {
          const locSlot = locGear[slot];
          const dispName = Array.isArray(locSlot) && locSlot[0] ? resolveGenderSlashLabel(locSlot[0]) : resolveGenderSlashLabel(entry[0]);
          const dispDesc = Array.isArray(locSlot) && locSlot[1] ? String(locSlot[1]) : (entry[1] ? String(entry[1]) : 'Starter equipment');
          loadout[slot] = {
            name: entry[0],
            display_name: dispName,
            description: entry[1] ? String(entry[1]) : 'Starter equipment',
            display_description: dispDesc,
          };
        } else if (typeof entry === 'object' && entry.name) {
          loadout[slot] = entry;
        }
      });
    }

    if (isNonCombat) {
      delete loadout['Weapon'];
      delete loadout['Shield'];
      delete loadout['Armor'];
    } else if (startingWeapon && (!loadout['Weapon'] || !isAnomalousIncursions)) {
      loadout['Weapon'] = {
        name: startingWeapon,
        display_name: weaponsDisplayMap[startingWeapon] || startingWeapon,
        description: 'Starter weapon',
      };
    }
    return loadout;
  }, [regeneratedLoadout, activeClassInfo, isNonCombat, isAnomalousIncursions, startingWeapon, isMale, weaponsDisplayMap]);

  useEffect(() => {
    if (!isOpen || !isAnomalousIncursions || !charClass) {
      setPreviewStartingItems(null);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setRegeneratingGear(true);
    apiCall('/api/character/preview-gear', {
      method: 'POST',
      signal: controller.signal,
      body: JSON.stringify({
        char_class: charClass,
        scenario,
        tags: scenario === 'custom' ? customTags : undefined,
        gender: character?.gender || 'Male',
        race: character?.race || 'Human',
        starting_weapon: isNonCombat ? '' : startingWeapon,
        force_dynamic: true,
        starting_faction: effectiveFaction,
      }),
    })
      .then((res) => {
        if (cancelled) return;
        if (res?.loadout) setRegeneratedLoadout(res.loadout);
        if (res?.starting_items) setPreviewStartingItems(res.starting_items);
      })
      .catch((err) => {
        if (err?.name === 'AbortError' || err?.isUserAbort || cancelled) return;
        console.error(err);
      })
      .finally(() => {
        if (!cancelled) setRegeneratingGear(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [isOpen, isAnomalousIncursions, effectiveFaction, charClass, scenario, startingWeapon, character?.gender, character?.race, isNonCombat, customTags]);

  const maxTotalPoints = 12;
  const totalAllocated = Object.values(stats).reduce((acc, v) => acc + Number(v || 1), 0);
  const pointsRemaining = maxTotalPoints - totalAllocated;

  const handleApplyPreset = () => {
    setStats(computeClassPreset(charClass, activeClassInfo?.canonical_description || activeClassInfo?.description || ''));
  };

  const adjustStat = (key, delta) => {
    setStats((prev) => {
      const next = (prev[key] ?? 1) + delta;
      if (next < 1 || next > 10) return prev;
      if (delta > 0 && pointsRemaining <= 0) return prev;
      return { ...prev, [key]: next };
    });
  };

  const handleRegenerateEquipment = async () => {
    if (regeneratingGear) return;
    if (gearAbortRef.current) {
      try {
        gearAbortRef.current.abort();
      } catch {}
    }
    const controller = new AbortController();
    gearAbortRef.current = controller;
    setRegeneratingGear(true);
    try {
      const res = await apiCall('/api/character/preview-gear', {
        method: 'POST',
        signal: controller.signal,
        body: JSON.stringify({
          char_class: charClass,
          scenario,
          tags: scenario === 'custom' ? customTags : undefined,
          gender: character?.gender || 'Male',
          race: character?.race || 'Human',
          starting_weapon: isNonCombat ? '' : startingWeapon,
          force_dynamic: true,
          starting_faction: isAnomalousIncursions ? effectiveFaction : undefined,
        }),
      });
      if (!isMountedRef.current || gearAbortRef.current !== controller) return;
      if (res?.loadout) setRegeneratedLoadout(res.loadout);
      if (res?.starting_items) setPreviewStartingItems(res.starting_items);
    } catch (err) {
      if (err?.name === 'AbortError' || err?.isUserAbort) return;
      console.error(err);
    } finally {
      if (gearAbortRef.current === controller) {
        gearAbortRef.current = null;
      }
      if (isMountedRef.current) {
        setRegeneratingGear(false);
      }
    }
  };

  const toggleCustomTag = (tagKey) => {
    setCustomTags(prev => prev.includes(tagKey) ? prev.filter(t => t !== tagKey) : [...prev, tagKey]);
  };

  const copyLink = async () => {
    if (!shareLink) return;
    if (await copyToClipboard(shareLink)) {
      setCopied(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
    }
  };

  const submitEmbark = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      // Intimate anatomy only applies (and is only persisted) for NSFW scenarios.
      const finalBSize = isNsfw && !isMale ? breastSize : undefined;
      const finalPSize = isNsfw && isMale ? penisSize : undefined;
      const finalTexture = isNsfw ? assetTexture : undefined;
      const finalRSize = isNsfw && !feralRearExcluded ? rearSize : undefined;
      const finalRTexture = isNsfw && !feralRearExcluded ? rearTexture : undefined;

      if (isNsfw && character?.user_id) {
        try {
          await apiCall('/api/character/appearance', {
            method: 'POST',
            body: JSON.stringify({
              user_id: character.user_id,
              character_id: character.id,
              breast_size: finalBSize,
              penis_size: finalPSize,
              asset_texture: finalTexture,
              rear_size: finalRSize,
              rear_texture: finalRTexture,
            }),
          });
        } catch (syncErr) {
          console.warn('Character appearance background sync failed:', syncErr);
          setError(syncErr?.message || t('embark.anatomy_sync_warn', 'Failed to sync anatomy customization.'));
          return;
        }
      }

      const finalStarterLoadout = { ...(displayedLoadout || {}) };
      if (!isNonCombat && startingWeapon && !finalStarterLoadout['Weapon']?.effect) {
        finalStarterLoadout['Weapon'] = {
          name: startingWeapon,
          description: 'Starter weapon',
        };
      }


      await onEmbark({
        slot: targetSlot || 1,
        scenario,
        mode,
        tags: scenario === 'custom' ? customTags : undefined,
        char_class: charClass,
        weapon_name: isNonCombat ? '' : startingWeapon,
        starter_loadout: finalStarterLoadout,
        starting_items: isAnomalousIncursions && previewStartingItems ? previewStartingItems : undefined,
        starting_faction: isAnomalousIncursions ? effectiveFaction : undefined,
        origin_mode: isAnomalousHighSchool ? originMode : undefined,
        student_grade: isAnomalousHighSchool && originMode === 'student' ? studentGrade : undefined,
        attribute: isAnomalousIncursions ? attribute : undefined,
        combat_archetype: isAnomalousIncursions ? combatArchetype : undefined,
        ability_medium: isAnomalousIncursions ? abilityMedium : undefined,
        str_val: stats.str,
        per: stats.per,
        end: stats.end,
        cha: stats.cha,
        int_val: stats.int,
        agi: stats.agi,
        luk: stats.luk,
        breast_size: finalBSize,
        penis_size: finalPSize,
        asset_texture: finalTexture,
        rear_size: finalRSize,
        rear_texture: finalRTexture,
      });
      if (isMountedRef.current) onClose();
    } catch (err) {
      if (isMountedRef.current) setError(err.message || 'Embarkation failed');
    } finally {
      if (isMountedRef.current) setSubmitting(false);
    }
  };

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('embark.wizard_title', 'Embarkation Wizard')}
      maxWidthClass="max-w-4xl"
      zIndexClass="z-[60]"
    >
        <div className="px-4 py-3.5 border-b border-fantasy-border/35 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-2 rounded-xl bg-fantasy-accent/15 border border-fantasy-accent/40 text-fantasy-accent shrink-0">
              <Compass size={18} />
            </div>
            <div className="min-w-0">
              <h2 className="font-rpg font-bold text-lg text-fantasy-accent truncate">{t('embark.wizard_title', 'Embarkation Wizard')}</h2>
              <p className="text-xs text-gray-400">Step {step} of 2 • Configure Your Journey</p>
            </div>
          </div>
          <MotionButton onClick={onClose} aria-label={t('common.close', 'Close')} className="hk-icon-btn h-8 min-w-8 shrink-0">
            <X size={18} />
          </MotionButton>
        </div>

        {error && (
          <div className="mx-4 mt-3 p-2.5 bg-red-500/15 text-red-200 border border-red-500/40 text-xs rounded-xl shrink-0">{error}</div>
        )}

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain custom-scrollbar px-5 py-2">
          {step === 1 && (
            <div>
              {/* Realm Selection */}
              <section className="hk-flat-section space-y-3">
                <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100 mb-2">{t('embark.origin_realm', '1. Origin Realm')}</h3>
                <select
                  value={activeFamily}
                  onChange={(e) => setScenario(e.target.value)}
                  aria-label={t('embark.origin_realm', '1. Origin Realm')}
                  className="w-full bg-fantasy-dark border border-fantasy-border p-2.5 rounded text-sm text-gray-100"
                >
                  {familyRoots.map(s => {
                    const count = scenarios.filter(v => familyRootOf(v) === s.key).length;
                    return (
                      <option key={s.key} value={s.key}>
                        {s.emoji} {s.dropdown_label || s.display_name || s.name}
                        {count > 1 ? ` · ${t('embark.variant_count', '{{count}} variants', { count })}` : ''}
                      </option>
                    );
                  })}
                  <option value="custom">{t('embark.custom_scenario_builder', '✨ Custom Scenario (Multi-Tag Builder)')}</option>
                </select>
                {familyVariants.length > 1 && (
                  <div className="space-y-1.5">
                    <div className="text-[11px] uppercase tracking-wider font-bold text-gray-300">
                      {t('embark.scenario_variant', 'Variant')}
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" role="radiogroup" aria-label={t('embark.scenario_variant', 'Variant')}>
                      {familyVariants.map(v => {
                        const active = v.key === scenario;
                        const extraTags = (v.variant_tags || []).map(tag => availableTags.find(at => (at.key || at.id) === tag)?.name || tag.replace(/_/g, ' '));
                        return (
                          <button
                            key={v.key}
                            type="button"
                            role="radio"
                            aria-checked={active}
                            onClick={() => setScenario(v.key)}
                            className={`p-2.5 rounded-lg border text-left transition-all ${
                              active
                                ? 'bg-indigo-600/30 border-indigo-400 text-white shadow-sm ring-1 ring-indigo-400'
                                : 'bg-black/40 border-fantasy-border/70 text-gray-300 hover:border-gray-500'
                            }`}
                          >
                            <div className="text-xs font-bold flex items-center gap-1.5">
                              <span aria-hidden="true">{v.emoji}</span>
                              <span>{v.variant_label || v.display_name || v.name}</span>
                            </div>
                            <div className="text-[10px] text-gray-400 leading-tight mt-0.5">
                              {extraTags.length > 0 ? extraTags.join(' • ') : t('embark.variant_base_hint', 'Base experience')}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
                {scenario !== 'custom' && scenarios.find(s => s.key === scenario)?.description && (
                  <p className="text-[11px] text-gray-400 leading-relaxed pt-0.5">
                    {scenarios.find(s => s.key === scenario)?.description}
                  </p>
                )}

                {scenario === 'custom' && (
                  <div className="space-y-3 pt-2">
                    <div>
                      <div className="text-[11px] uppercase tracking-wider font-bold text-gray-300 mb-1.5 flex items-center gap-1.5">
                        <span>{t('embark.genres', 'Genres')}</span>
                        <span className="text-[10px] text-gray-400 font-normal">{t('embark.select_genres_sub', '(select one or more)')}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {availableTags
                          .filter(t => t.category === 'genre' || (!t.category && !['grimdark', 'furry', 'nsfw', 'gore', 'non_combat'].includes(t.key || t.id)))
                          .map(tag => {
                            const tKey = tag.key || tag.id;
                            const active = customTags.includes(tKey);
                            return (
                              <button
                                key={tKey}
                                type="button"
                                onClick={() => toggleCustomTag(tKey)}
                                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                                  active
                                    ? 'bg-fantasy-accent/25 border-fantasy-accent text-fantasy-accent shadow-sm'
                                    : 'bg-black/50 border-fantasy-border/60 text-gray-400 hover:text-gray-200'
                                }`}
                              >
                                {tag.name || tKey}
                              </button>
                            );
                          })}
                      </div>
                    </div>

                    <div>
                      <div className="text-[11px] uppercase tracking-wider font-bold text-gray-300 mb-1.5 flex items-center gap-1.5">
                        <span>{t('embark.tone_and_modifiers', 'Tone & Modifiers')}</span>
                        <span className="text-[10px] text-gray-400 font-normal">{t('embark.tone_modifiers_sub', '(optional tone & rule toggles)')}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {availableTags
                          .filter(t => t.category === 'modifier' || ['grimdark', 'furry', 'nsfw', 'gore', 'non_combat'].includes(t.key || t.id))
                          .map(tag => {
                            const tKey = tag.key || tag.id;
                            const active = customTags.includes(tKey);
                            const icon = tKey === 'nsfw' ? '🔞 ' : (tKey === 'gore' ? '🩸 ' : (tKey === 'furry' ? '🐾 ' : (tKey === 'non_combat' ? '🕊️ ' : (tKey === 'grimdark' ? '💀 ' : '✨ '))));
                            return (
                              <button
                                key={tKey}
                                type="button"
                                onClick={() => toggleCustomTag(tKey)}
                                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                                  active
                                    ? 'bg-amber-500/25 border-amber-500 text-amber-300 shadow-sm'
                                    : 'bg-black/50 border-fantasy-border/60 text-gray-400 hover:text-gray-200'
                                }`}
                              >
                                {icon}{tag.name || tKey}
                              </button>
                            );
                          })}
                      </div>
                    </div>
                  </div>
                )}

                {isAnomalousHighSchool && (
                  <div className="pt-3 mt-2 border-t border-indigo-800/40 bg-indigo-950/20 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] uppercase tracking-wider font-bold text-indigo-300 flex items-center gap-1.5">
                        <span aria-hidden="true">🎒</span>
                        <span>{t('embark.origin_mode_title', 'Operative Protocol & Background')}</span>
                      </span>
                      <span className="text-[10px] text-indigo-200/80">
                        {originMode === 'student' ? t('embark.origin_student_tag', 'Student Special Agent (Campus & Freelance)') : t('embark.origin_adult_tag', 'Adult Agency Agent (Full Agency Operative)')}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setOriginMode('student')}
                        className={`p-2.5 rounded-lg border text-left flex items-center gap-2 transition-all ${
                          originMode === 'student'
                            ? 'bg-indigo-600/30 border-indigo-400 text-white shadow-sm ring-1 ring-indigo-400'
                            : 'bg-black/40 border-fantasy-border/70 text-gray-300 hover:border-gray-500'
                        }`}
                      >
                        <span className="text-base" aria-hidden="true">🎒</span>
                        <div>
                          <div className="text-xs font-bold">{t('embark.origin_student_label', 'Student Operative')}</div>
                          <div className="text-[10px] text-gray-400 leading-tight">{t('embark.origin_student_hint', 'School classes & clubs by day, anomaly hunting by night')}</div>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => setOriginMode('adult')}
                        className={`p-2.5 rounded-lg border text-left flex items-center gap-2 transition-all ${
                          originMode === 'adult'
                            ? 'bg-amber-600/30 border-amber-400 text-white shadow-sm ring-1 ring-amber-400'
                            : 'bg-black/40 border-fantasy-border/70 text-gray-300 hover:border-gray-500'
                        }`}
                      >
                        <span className="text-base" aria-hidden="true">🪪</span>
                        <div>
                          <div className="text-xs font-bold">{t('embark.origin_adult_label', 'Adult Field Agent')}</div>
                          <div className="text-[10px] text-gray-400 leading-tight">{t('embark.origin_adult_hint', 'Full agency enlistment with adult protocols & clearance')}</div>
                        </div>
                      </button>
                    </div>

                    {originMode === 'student' && (
                      <div className="pt-2 border-t border-indigo-800/30">
                        <label className="block text-[10px] uppercase tracking-wider font-bold text-indigo-300 mb-1">
                          {t('embark.student_grade_label', 'Academic Grade Year')}
                        </label>
                        <div className="grid grid-cols-4 gap-1.5">
                          {['Freshman', 'Sophomore', 'Junior', 'Senior'].map((gr) => (
                            <button
                              key={gr}
                              type="button"
                              onClick={() => setStudentGrade(gr)}
                              className={`py-1.5 px-2 rounded text-xs font-bold text-center border transition-all ${
                                studentGrade === gr
                                  ? 'bg-indigo-500/40 border-indigo-300 text-indigo-100 ring-1 ring-indigo-400'
                                  : 'bg-black/30 border-fantasy-border/60 text-gray-300 hover:border-gray-400'
                              }`}
                            >
                              {gr}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {isAnomalousIncursions && (
                  <fieldset className="pt-3 mt-2 border-t border-fantasy-border/60 space-y-2">
                    {(!isAnomalousHighSchool || originMode === 'adult') && (
                      <>
                        <legend className="text-[11px] uppercase tracking-wider font-bold text-fantasy-accent mb-0.5 flex items-center gap-1.5">
                          <Shield size={13} aria-hidden="true" />
                          <span>{t('embark.starting_faction_legend', 'Starting Faction Affiliation')}</span>
                        </legend>
                        <p className="text-[11px] text-gray-400 leading-snug">
                          {t('embark.starting_faction_hint', 'Shapes your starting HQ, uniform loadout, daily mandates, merchant perks, and agent clearance.')}
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                          {anomalousFactionOptions.map((fac) => {
                        const optId = `${factionFieldId}-${fac.id}`;
                        const descId = `${factionFieldId}-${fac.id}-desc`;
                        const isSelected = startingFaction === fac.id;
                        const FacIcon = fac.Icon;
                        return (
                          <label
                            key={fac.id}
                            htmlFor={optId}
                            className={`min-h-[52px] p-3 rounded-lg border cursor-pointer flex items-start gap-2.5 transition-all has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-fantasy-accent ${
                              isSelected
                                ? 'bg-fantasy-accent/15 border-fantasy-accent shadow-sm'
                                : 'bg-black/40 border-fantasy-border/70 hover:border-gray-500'
                            }`}
                          >
                            <input
                              type="radio"
                              id={optId}
                              name="starting_faction"
                              value={fac.id}
                              checked={isSelected}
                              onChange={() => setStartingFaction(fac.id)}
                              aria-describedby={descId}
                              className="mt-1 accent-amber-500 shrink-0"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <FacIcon size={13} aria-hidden="true" className={isSelected ? 'text-fantasy-accent shrink-0' : 'text-gray-400 shrink-0'} />
                                <span className={`text-xs font-bold ${isSelected ? 'text-amber-200' : 'text-gray-200'}`}>
                                  {fac.name}
                                </span>
                                {fac.isDefault && (
                                  <span className="px-1.5 py-0.5 rounded bg-fantasy-accent/20 border border-fantasy-accent/40 text-fantasy-accent text-[9px] uppercase font-mono">
                                    {t('embark.default_badge', 'Default')}
                                  </span>
                                )}
                              </div>
                              <p id={descId} className="text-[10px] text-gray-400 leading-relaxed mt-1">
                                {fac.desc}
                              </p>
                            </div>
                          </label>
                        );
                      })}
                        </div>
                      </>
                    )}

                    {/* Awakened 3-Axis Resonance Attunement */}
                    <div className="pt-3 mt-2 border-t border-cyan-800/40 bg-cyan-950/15 rounded-lg p-3 space-y-2.5">
                      <div className="flex items-center justify-between flex-wrap gap-1">
                        <span className="text-[11px] uppercase tracking-wider font-bold text-cyan-300 flex items-center gap-1.5">
                          <span aria-hidden="true">🧬</span>
                          <span>{t('awakened.section_title', 'Awakened Resonance Attunement')}</span>
                        </span>
                        <span id={`${factionFieldId}-res-sub`} className="text-[10px] text-cyan-200/80">
                          {t('awakened.section_subtitle', 'Lock your innate Attribute, Combat Archetype, and Ability Medium (5-Skill Kit)')}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                        <div>
                          <label htmlFor={`${factionFieldId}-attr`} className="block text-[10px] uppercase tracking-wider font-bold text-gray-300 mb-1">
                            {t('awakened.attribute_label', 'Resonance Attribute (9)')}
                          </label>
                          <select
                            id={`${factionFieldId}-attr`}
                            aria-describedby={`${factionFieldId}-res-sub`}
                            value={attribute}
                            onChange={(e) => setAttribute(e.target.value)}
                            className="w-full bg-fantasy-dark border border-cyan-800/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-cyan-400"
                          >
                            {(templates?.anomalous_attributes?.length ? templates.anomalous_attributes : ['fire', 'water', 'wind', 'earth', 'ice', 'electric', 'bio', 'physical', 'aether']).map((attrKey) => (
                              <option key={attrKey} value={attrKey}>
                                {t(`awakened.attrs.${attrKey}`, attrKey.toUpperCase())}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label htmlFor={`${factionFieldId}-arch`} className="block text-[10px] uppercase tracking-wider font-bold text-gray-300 mb-1">
                            {t('awakened.archetype_label', 'Combat Archetype (4)')}
                          </label>
                          <select
                            id={`${factionFieldId}-arch`}
                            aria-describedby={`${factionFieldId}-res-sub`}
                            value={combatArchetype}
                            onChange={(e) => setCombatArchetype(e.target.value)}
                            className="w-full bg-fantasy-dark border border-cyan-800/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-cyan-400"
                          >
                            {(templates?.combat_archetypes?.length ? templates.combat_archetypes : ['vanguard', 'catalyst', 'breaker', 'warden']).map((archKey) => (
                              <option key={archKey} value={archKey}>
                                {t(`awakened.archetypes.${archKey}`, archKey.toUpperCase())}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label htmlFor={`${factionFieldId}-med`} className="block text-[10px] uppercase tracking-wider font-bold text-gray-300 mb-1">
                            {t('awakened.medium_label', 'Ability Medium (4)')}
                          </label>
                          <select
                            id={`${factionFieldId}-med`}
                            aria-describedby={`${factionFieldId}-res-sub`}
                            value={abilityMedium}
                            onChange={(e) => setAbilityMedium(e.target.value)}
                            className="w-full bg-fantasy-dark border border-cyan-800/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-cyan-400"
                          >
                            {(templates?.ability_mediums?.length ? templates.ability_mediums : ['direct_manifestation', 'ordnance_imbuement', 'somatic_overdrive', 'autonomous_construct']).map((medKey) => (
                              <option key={medKey} value={medKey}>
                                {t(`awakened.mediums.${medKey}`, medKey)}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>
                  </fieldset>
                )}
              </section>

              {/* Class & Stats Reallocation */}
              <section className="hk-flat-section grid grid-cols-1 md:grid-cols-2 gap-5">
                <div className="space-y-3 min-w-0">
                   <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100 mb-2">{t('embark.class_and_loadout', '2. Class & Loadout')}</h3>
                   <select value={charClass} onChange={(e) => setCharClass(e.target.value)} className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-sm text-gray-100">
                     {Object.keys(activeClassesMap).map(cls => <option key={cls} value={cls}>{activeClassesMap[cls]?.display_name || cls}</option>)}
                   </select>
                   {activeClassInfo?.description && (
                     <p className="text-[11px] text-gray-400 leading-relaxed">
                       {activeClassInfo.description}
                     </p>
                   )}

                   {!isNonCombat && (
                     <>
                       <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-400 mt-2">{t('embark.starting_weapon', 'Starting Weapon')}</label>
                       <select value={startingWeapon} onChange={(e) => setStartingWeapon(e.target.value)} className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100">
                         {weaponsList.map(w => <option key={w} value={w}>{weaponsDisplayMap[w] || w}</option>)}
                       </select>
                     </>
                   )}

                   <div className="mt-3 pt-3 border-t border-fantasy-border/50 space-y-2">
                     <div className="flex items-center justify-between">
                       <span className="text-[11px] uppercase tracking-wider font-bold text-gray-400">
                         Starting Equipment
                       </span>
                       <button
                         type="button"
                         onClick={handleRegenerateEquipment}
                         disabled={regeneratingGear}
                         className="px-2 py-0.5 rounded bg-fantasy-accent/15 hover:bg-fantasy-accent/25 border border-fantasy-accent/50 text-fantasy-accent text-[11px] font-semibold flex items-center gap-1 transition-colors disabled:opacity-50"
                       >
                         <RefreshCw size={11} className={regeneratingGear ? 'animate-spin' : ''} />
                         <span>{regeneratingGear ? 'Rolling...' : 'Regenerate'}</span>
                       </button>
                     </div>

                     <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto custom-scrollbar pr-1">
                       {Object.entries(displayedLoadout).map(([slot, item]) => {
                         const isAnomItem = String(item?.name || '').includes('[Anomalous]');
                         const grantMatch = String(item?.description || '').match(/✨ Grants Ability[^•]*/);
                         return (
                           <div
                             key={slot}
                             className={`p-2 rounded border flex flex-col justify-center ${
                               isAnomItem
                                 ? 'bg-purple-950/30 border-purple-500/60'
                                 : 'bg-black/40 border-fantasy-border/60'
                             }`}
                           >
                             <span className="text-[9px] uppercase tracking-wider text-gray-400 font-semibold">{slot}</span>
                             <span
                               className={`text-xs font-bold leading-snug break-words ${isAnomItem ? 'text-purple-200' : 'text-gray-200'}`}
                               title={item.display_description || item.description || item.display_name || item.name}
                             >
                               {item.display_name || item.name}
                             </span>
                             {grantMatch && (
                               <span className="text-[10px] text-amber-300 font-medium leading-tight mt-0.5">
                                 {grantMatch[0].trim()}
                               </span>
                             )}
                           </div>
                         );
                       })}
                       {Object.keys(displayedLoadout).length === 0 && (
                         <div className="col-span-1 sm:col-span-2 text-center text-[10px] text-gray-500 py-2 italic">
                           Default gear will be forged upon embarkation.
                         </div>
                       )}
                     </div>
                   </div>
                </div>

                {/* Stats Reallocation */}
                <div className="min-w-0 md:border-l md:border-fantasy-border/35 md:pl-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs uppercase tracking-wider font-bold text-gray-100">{t('embark.free_stats', '3. Free Stats Allocation')}</h3>
                    <span className="px-2 py-0.5 bg-gray-500/15 text-fantasy-accent border border-fantasy-border/40 text-[10px] font-mono rounded-lg">{pointsRemaining} pts left</span>
                  </div>
                  
                  <button onClick={handleApplyPreset} className="w-full mb-3 py-1.5 rounded border border-fantasy-accent/50 text-fantasy-accent text-[11px] bg-fantasy-accent/10 hover:bg-fantasy-accent/20 transition-colors">
                    {t('embark.switch_to_class_rec', { className: activeClassInfo?.display_name || charClass, defaultValue: `Switch to ${activeClassInfo?.display_name || charClass} Rec` })}
                  </button>

                  <div className="space-y-1.5">
                    {STAT_KEYS.map(s => {
                      const medMap = templates?.medium_stat_synergy || {
                        direct_manifestation: ['INT', 'CHA'],
                        ordnance_imbuement: ['PER', 'STR', 'AGI'],
                        somatic_overdrive: ['STR', 'AGI', 'END'],
                        autonomous_construct: ['INT', 'PER', 'END'],
                      };
                      const isSynergyStat = isAnomalousIncursions && (medMap[abilityMedium] || []).includes(s.code);
                      return (
                      <div key={s.key} className={`flex items-center justify-between bg-black/40 border p-1.5 rounded ${isSynergyStat ? 'border-cyan-500/60 bg-cyan-950/20' : 'border-fantasy-border/50'}`}>
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-bold text-gray-300 w-10">{s.code}</span>
                          {isSynergyStat && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono uppercase">
                              ⚡ {t('awakened.synergy_badge', 'Medium Synergy')}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                           <button onClick={() => adjustStat(s.key, -1)} disabled={stats[s.key] <= 1} className="w-6 h-6 bg-black border border-fantasy-border rounded text-gray-300">-</button>
                           <span className="w-4 text-center font-mono text-sm text-fantasy-accent">{stats[s.key]}</span>
                           <button onClick={() => adjustStat(s.key, 1)} disabled={pointsRemaining <= 0 || stats[s.key] >= 10} className="w-6 h-6 bg-black border border-fantasy-border rounded text-gray-300">+</button>
                        </div>
                      </div>
                      );
                    })}
                  </div>
                </div>
              </section>

              {/* Optional / NSFW Intimate Physical Anatomy Customizer */}
              {isNsfw && (
                <section className="hk-flat-section space-y-3">
                  <div className="flex items-center justify-between border-b border-pink-900/50 pb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-base">🔞</span>
                      <h3 className="text-xs uppercase tracking-wider font-bold text-pink-300">
                        4. Intimate Anatomy &amp; Dynamic Flavor
                      </h3>
                    </div>
                    <span className="text-[10px] text-pink-400 font-medium">
                      Shapes Narrative Voice &amp; Reactions
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-300 leading-relaxed">
                    Assets influence psychological vulnerability or confidence, tactile sensations, lingerie fit, and partner reactions across romantic encounters.
                  </p>

                  {(() => {
                    const embarkSizeTier = isMale
                      ? classifyAssetSizeTierClient(penisSize, true)
                      : classifyAssetSizeTierClient(breastSize, false);
                    const allowedEmbarkTextures = getAllowedTextureOptions(isMale, embarkSizeTier);
                    const embarkRearTier = classifyRearSizeTierClient(rearSize);
                    const allowedEmbarkRearTextures = getAllowedRearTextureOptions(embarkRearTier);
                    const embarkSpeciesSurface = getSpeciesSurfaceClient(character?.race, character?.appearance?.skin_type);
                    return !anatomyExpanded ? (
                    <div className="flex items-center justify-between gap-3 p-3 rounded-lg bg-black/40 border border-pink-900/50">
                      <div className="text-xs text-gray-200 min-w-0">
                        <div className="text-[10px] uppercase tracking-wider font-bold text-pink-300 mb-0.5">
                          {t('embark.anatomy_saved_title', 'Using your saved anatomy')}
                        </div>
                        <div className="truncate">
                          {isMale
                            ? t(PENIS_SIZE_LABELS[penisSize]?.[0] || 'character.penis_average', PENIS_SIZE_LABELS[penisSize]?.[1] || penisSize)
                            : t(BREAST_SIZE_LABELS[breastSize]?.[0] || 'character.breast_proportional', BREAST_SIZE_LABELS[breastSize]?.[1] || breastSize)}
                          {' • '}
                          {assetTexture ? formatAssetTexture(assetTexture, isMale, t) : t('embark.anatomy_texture_auto', 'Texture auto-assigned')}
                        </div>
                        {!feralRearExcluded && (
                          <div className="truncate text-amber-200/90 mt-0.5">
                            {t('anatomy.rear_size', 'Rear')}:{' '}
                            {formatRearSizeLabel(rearSize, t) || rearSize}
                            {' • '}
                            {rearTexture ? formatRearTexture(rearTexture, t) : t('embark.anatomy_texture_auto', 'Texture auto-assigned')}
                          </div>
                        )}
                        {embarkSpeciesSurface && (
                          <div className="mt-1 text-[10px] text-amber-300/90 truncate">
                            ✨ {t('anatomy.species_surface.label', 'Auto species surface')}: {t(embarkSpeciesSurface.i18nKey, embarkSpeciesSurface.fallback)}
                          </div>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => setAnatomyExpanded(true)}
                        className="shrink-0 px-3 py-1.5 rounded border border-pink-700/70 text-[11px] font-semibold text-pink-200 hover:bg-pink-900/30"
                      >
                        {t('embark.anatomy_customize', 'Customize')}
                      </button>
                    </div>
                  ) : (
                  <>
                  <div>
                    {isMale ? (
                      <div>
                        <label className="block text-[11px] uppercase tracking-wider font-bold text-purple-300 mb-1">
                          Penis Size Tier
                        </label>
                        <select
                          value={penisSize}
                          onChange={(e) => {
                            const nextSz = e.target.value;
                            setPenisSize(nextSz);
                            if (assetTexture) {
                              setAssetTexture(healTextureForSelection(assetTexture, true, classifyAssetSizeTierClient(nextSz, true)));
                            }
                          }}
                          className="w-full bg-fantasy-dark border border-purple-900/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-purple-500"
                        >
                          <option value="small">{t('character.penis_compact', 'Petite / Modest (Compact)')}</option>
                          <option value="average">{t('character.penis_average', 'Proportional (Average)')}</option>
                          <option value="large">{t('character.penis_large', 'Well-Endowed / Formidable (Large)')}</option>
                          <option value="huge">{t('character.penis_huge', 'Massive / Heavy (Huge)')}</option>
                        </select>
                      </div>
                    ) : (
                      <div>
                        <label className="block text-[11px] uppercase tracking-wider font-bold text-pink-300 mb-1">
                          Breast Size Tier
                        </label>
                        <select
                          value={breastSize}
                          onChange={(e) => {
                            const nextSz = e.target.value;
                            setBreastSize(nextSz);
                            if (assetTexture) {
                              setAssetTexture(healTextureForSelection(assetTexture, false, classifyAssetSizeTierClient(nextSz, false)));
                            }
                          }}
                          className="w-full bg-fantasy-dark border border-pink-900/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-pink-500"
                        >
                          <option value="flat">{t('character.breast_flat', 'Flat (AA-Cup / Barely There)')}</option>
                          <option value="small">{t('character.breast_petite', 'Petite / Modest (A-B Cup)')}</option>
                          <option value="average">{t('character.breast_proportional', 'Proportional (C-Cup)')}</option>
                          <option value="large">{t('character.breast_voluptuous', 'Voluptuous / Full (D-DD Cup)')}</option>
                          <option value="huge">{t('character.breast_bountiful', 'Bountiful / Massive (E+ Cup)')}</option>
                        </select>
                      </div>
                    )}
                  </div>

                  {/* Tactile Texture / Shape Feature */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-300">
                        Tactile Feature &amp; Texture ({isMale ? 'Phallus' : 'Breasts'})
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setAssetTexture(rollClientAssetTexture(isMale, embarkSizeTier, character?.race, character?.appearance?.physique));
                        }}
                        className="text-[10px] text-pink-400 hover:text-pink-300 flex items-center gap-1 font-semibold"
                      >
                        <Sparkles size={11} /> Roll Feature
                      </button>
                    </div>
                    <select
                      value={assetTexture}
                      onChange={(e) => setAssetTexture(e.target.value)}
                      className="w-full bg-fantasy-dark border border-fantasy-border/80 p-2 rounded text-xs text-gray-100"
                    >
                      <option value="">{t('character.auto_assign_anatomy', 'Auto-Assign from Race & Build (Dynamic Roll)')}</option>
                      {allowedEmbarkTextures.map(opt => (
                        <option key={opt.value} value={opt.value}>{t(opt.i18nKey, opt.fallback)}</option>
                      ))}
                    </select>
                  </div>

                  {/* Rear / Ass Anatomy (All Genders, NSFW only, non-feral) */}
                  {!feralRearExcluded && (
                    <div className="pt-2.5 border-t border-pink-900/35 space-y-3">
                      <div>
                        <label className="block text-[11px] uppercase tracking-wider font-bold text-rose-300 mb-1">
                          {t('character.rear_size_tier', 'Rear / Ass Size Tier')}
                        </label>
                        <select
                          value={rearSize}
                          onChange={(e) => {
                            const nextSz = e.target.value;
                            setRearSize(nextSz);
                            if (rearTexture) {
                              setRearTexture(healRearTextureForSelection(rearTexture, classifyRearSizeTierClient(nextSz)));
                            }
                          }}
                          className="w-full bg-fantasy-dark border border-rose-900/60 p-2 rounded text-xs text-gray-100 focus:outline-none focus:border-rose-500"
                        >
                          {REAR_SIZE_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>{t(opt.selectKey, opt.selectFallback)}</option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <label className="block text-[11px] uppercase tracking-wider font-bold text-gray-300">
                            {t('character.rear_texture', 'Rear Tactile Texture')}
                          </label>
                          <button
                            type="button"
                            onClick={() => {
                              setRearTexture(rollClientRearTexture(embarkRearTier, character?.race, character?.appearance?.physique));
                            }}
                            className="text-[10px] text-rose-300 hover:text-rose-200 flex items-center gap-1 font-semibold"
                          >
                            <Sparkles size={11} /> {t('character.roll_rear_feature', 'Roll Rear Feature')}
                          </button>
                        </div>
                        <select
                          value={rearTexture}
                          onChange={(e) => setRearTexture(e.target.value)}
                          className="w-full bg-fantasy-dark border border-fantasy-border/80 p-2 rounded text-xs text-gray-100"
                        >
                          <option value="">{t('character.auto_assign_anatomy', 'Auto-Assign from Race & Build (Dynamic Roll)')}</option>
                          {allowedEmbarkRearTextures.map((opt) => (
                            <option key={opt.value} value={opt.value}>{t(opt.i18nKey, opt.label)}</option>
                          ))}
                        </select>
                      </div>

                      {embarkSpeciesSurface && (
                        <p className="mt-1.5 text-[10px] text-amber-300/90 flex items-center gap-1">
                          ✨ {t('anatomy.species_surface.label', 'Auto species surface')}:{' '}
                          <strong className="font-semibold">{t(embarkSpeciesSurface.i18nKey, embarkSpeciesSurface.fallback)}</strong>
                        </p>
                      )}
                    </div>
                  )}
                  {feralRearExcluded && embarkSpeciesSurface && (
                    <p className="mt-1.5 text-[10px] text-amber-300/90 flex items-center gap-1">
                      ✨ {t('anatomy.species_surface.label', 'Auto species surface')}:{' '}
                      <strong className="font-semibold">{t(embarkSpeciesSurface.i18nKey, embarkSpeciesSurface.fallback)}</strong>
                    </p>
                  )}
                  </>
                  );
                  })()}
                </section>
              )}
            </div>
          )}

          {step === 2 && (
            <div>
              <section className="hk-flat-section">
                 <h3 className="text-sm uppercase tracking-wider font-bold text-fantasy-accent mb-4 text-center">{t('embark.select_adventure_mode', 'Select Adventure Mode')}</h3>
                 <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                   {[
                     { id: 'solo', name: 'Solo Adventure', desc: 'Play alone, offline or online.' },
                     { id: 'turn', name: 'Multiplayer (Turn-Based)', desc: 'Take turns with friends.' },
                     { id: 'sync', name: 'Multiplayer (Sync)', desc: 'Real-time chaotic actions.' }
                   ].map(m => (
                     <MotionButton key={m.id} onClick={() => setMode(m.id)} className={`p-4 rounded-xl border text-left transition-all ${mode === m.id ? 'bg-fantasy-accent/20 border-fantasy-accent' : 'bg-gray-500/10 border-fantasy-border/40 hover:border-fantasy-border'}`}>
                       <div className="font-bold text-gray-100">{m.name}</div>
                       <div className="text-[11px] text-gray-400 mt-1">{m.desc}</div>
                     </MotionButton>
                   ))}
                 </div>
              </section>

              {mode !== 'solo' && shareLink && (
                <section className="hk-flat-section text-center">
                  <h4 className="text-xs font-bold text-gray-300 mb-2">{t('embark.invite_friends', 'Invite Friends (Cross-Device Link)')}</h4>
                  <p className="text-[11px] text-gray-400 mb-3">{t('embark.invite_friends_desc', 'Share this public link so anyone can join your adventure!')}</p>
                  <div className="flex items-center justify-center gap-2">
                    <code className="px-3 py-1.5 bg-gray-500/15 border border-fantasy-border/50 text-fantasy-accent rounded-lg text-sm select-all break-all">
                      {shareLink}
                    </code>
                    <MotionButton onClick={copyLink} className="p-1.5 rounded-lg bg-gray-500/15 border border-fantasy-border/50 hover:text-white transition-colors">
                      {copied ? <Check size={16} className="text-green-400" /> : <Link size={16} />}
                    </MotionButton>
                  </div>
                </section>
              )}
            </div>
          )}
        </div>

        <div className="px-4 py-3 border-t border-fantasy-border/35 flex justify-between shrink-0">
          {step === 2 ? (
            <MotionButton onClick={() => setStep(1)} className="px-4 py-2 border border-fantasy-border/60 text-xs rounded-lg text-gray-300 hover:bg-gray-500/10">{t('common.back', 'Back')}</MotionButton>
          ) : (
            <MotionButton onClick={onClose} className="px-4 py-2 border border-fantasy-border/60 text-xs rounded-lg text-gray-300 hover:bg-gray-500/10">{t('common.cancel', 'Cancel')}</MotionButton>
          )}

          {step === 1 ? (
             <MotionButton onClick={() => setStep(2)} className="px-5 py-2 bg-fantasy-accent text-black font-bold text-xs uppercase rounded-lg hover:bg-amber-400 transition-colors">{t('embark.next_step', 'Next Step')}</MotionButton>
          ) : (
             <MotionButton onClick={submitEmbark} disabled={submitting} className="px-5 py-2 bg-fantasy-accent text-black font-bold text-xs uppercase rounded-lg flex items-center gap-2 hover:bg-amber-400 transition-colors">
               <Play size={14} />
               {submitting ? 'Embarking...' : 'Start Adventure'}
             </MotionButton>
          )}
        </div>
    </AcrylicModal>
  );
};

export default EmbarkationModal;
