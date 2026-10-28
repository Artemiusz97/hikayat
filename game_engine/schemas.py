"""
LLM JSON response schemas and custom starter gear generation prompts/schemas for Hikayat.
"""

CHARACTER_OUTCOME_FIELD = """{"name": "string, exact character name", "hp_change": integer, "temp_hp_change": integer, "mp_change": integer, "gold_change": integer, "items_gained": ["string"], "items_lost": ["string"], "status_effects": ["short condition tag"]}"""

TRACKER_ENTITY_FIELD = """{"name": "string", "descriptor": "string (optional: short physical descriptor if the prose introduces them by description rather than name)", "level": "integer (only if friendly companion)", "hp": "integer (only if friendly companion)", "max_hp": "integer (only if friendly companion)", "mp": "integer (only if friendly companion)", "max_mp": "integer (only if friendly companion)", "status_effects": ["short condition tag"]}"""

MERCHANT_ENCOUNTER_FIELD = """{"present": boolean, "name": "string (token if new)", "description": "short flavor sentence"}"""

RELATIONSHIP_UPDATE_FIELD = """{"npc_name": "string", "delta_score": integer (-10 to +10, scale: +1..+3 minor chat, +4..+6 helpful/check success, +7..+10 major bond moment), "interaction_tone": "warm|neutral|hostile|flirtatious|prying", "trait_alignment": "resonated|clashed|none", "memory_summary": "string (1 short evocative sentence describing notable bond moment, or empty)", "revealed_attributes": ["sensitive_spots", "turn_ons", "fetishes", "demeanor", "dynamic"], "new_sensitive_spots": "string or empty", "new_turn_ons": "string or empty", "new_fetishes": "string or empty", "new_demeanor": "string or empty", "new_dynamic": "string or empty", "new_traits": ["short 1-2 word personality trait"], "new_preferences": ["short 1-3 word preference tag"]}"""

FACTION_UPDATE_FIELD = """{"faction_name": "string", "delta_score": integer, "notes": "string"}"""

PHYSICAL_UPDATE_FIELD = """{"actors": {"Character Name": {"posture": "standing|seated|kneeling|prone", "holding": "item name or empty", "stance": "Guarded|Melee|Cover|Ready"}}, "props": [{"name": "string", "state": "string"}], "combat_focus": "string or null"}"""

ENTITY_AUDIT_FIELD = """{"present_named_characters": ["string, list of EVERY named individual physically present in the immediate room right now"]}"""

CAST_EVENT_FIELD = """{"type": "arrive|depart|engage", "npc": "string, exact NPC personal name (invent one for a new unnamed person)", "reason": "short 1-phrase rationale", "gender": "male|female (arrive only)", "descriptor": "short physical descriptor matching the prose (arrive only)"}"""

SCENE_SCHEMA = f"""{{
  "scene_title": "string, 2-5 word atmospheric narrative chapter heading (e.g. 'Echoes in the Stacks')",
  "entity_audit": {ENTITY_AUDIT_FIELD},
  "narrative": "string, paragraphs establishing scene setting, environment, and upcoming choice context. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone.",
  "choices": [
    {{"label": "string (concise, max 6-8 words)", "stat": "STR|PER|END|CHA|INT|AGI|LUK|ITEM|NONE", "requirement": 0-12, "mp_cost": 0, "intent": "general_action|dialogue_init|dialogue_exit|movement|social_invite|phone_contact_exchange|romantic_confession|affection_touch|intimate_act|disclosure_inquiry|investigate_clue|area_scout|stealth_covert|rest_sleep|party_recruit|gift_offer|merchant_trade|inspect_board|media_capture|phone_comm", "sub_intent": "string (optional: kiss|foreplay|manual_give|manual_receive|manual_mutual|oral_give|oral_receive|oral_mutual|intercourse|anal_give|anal_receive|anal_mutual|aftercare|redress|date|confession|lockpick|pickpocket|gamble|use_item|deduce_clues|explore|combat_flee or empty)", "target_npc": "string (exact NPC name if targeting an NPC, else empty)", "ends_dialogue": false, "dismisses_npc": false, "gold_spent": 0, "triggers_loot_roll": false}}
  ],
  "campaign_end_goals": [
    {{"id": "G1", "title": "string, 1st long-term campaign victory condition relevant to scenario", "description": "string, 1-sentence goal description"}},
    {{"id": "G2", "title": "string, 2nd long-term campaign victory condition relevant to scenario", "description": "string, 1-sentence goal description"}},
    {{"id": "G3", "title": "string, 3rd long-term campaign victory condition relevant to scenario", "description": "string, 1-sentence goal description"}}
  ],
  "new_entities": [{{"type": "person|place|faction", "name": "string (token if new)", "race": "string if person", "species": "cat|fox|wolf|rabbit|tiger|lion|cheetah|fennec|mouse|bear|bird|reptile|snake|dragon|human", "social_role_type": "student_peer|faculty_staff|adult_service|general", "gender": "male|female|other (if person)", "appearance": {{"eye_color": "string (e.g. sapphire blue, emerald green, glowing purple, ruby red, amethyst, heterochromatic blue-green)", "hair_color": "string", "hair_length": "string", "hair_style": "string", "stature": "string", "skin_color": "string (humanoids)", "skin_type": "furry|feathered|scaly|synthetic|skin", "coat_color": "string (beastfolk/monsters e.g. snow white fur, midnight black, pastel pink, cerulean blue, golden-cream, lavender, calico)", "distinctive_features": "string (tails, ears, scars, tattoos)", "outfit_style": "string (clothing style)", "breast_size": "string (NSFW female only: tactile-fused cup e.g. 'Bouncy & Sensitive DD-Cup', 'Soft & Downy Chest Fur B-Cup', 'Tender & Delicate Petite A-Cup')", "penis_size": "string (NSFW male only: tactile-fused size e.g. 'Veined & Firm 7.5\"', 'Sleek Scaled Base & Firm 8\"', 'Warm & Pulsing Average')", "intercourse_experience": "virgin|non_virgin|unknown (NSFW only)", "oral_experience": "virgin|has_given|has_received|has_given_and_received|unknown (NSFW only)", "intimate_demeanor": "string (NSFW only: private demeanor)", "intimate_dynamic": "string (NSFW only: power dynamic, proactivity, & drive)", "sensitive_spots": "string (NSFW only: 1-3 spots or None)", "turn_ons": "string (NSFW only: 1-3 triggers or None)", "fetishes": "string (NSFW only: 1-3 kinks or None/Vanilla)"}}, "description": "short sentence", "disposition": "friendly|neutral|hostile", "traits": ["2-3 traits"], "motivation": "string", "mannerisms": "string", "descriptor": "string (persons only: short physical descriptor matching how the prose first describes them, e.g. 'man in a disheveled investigator coat')"}}],
  "npcs_present": [{TRACKER_ENTITY_FIELD}],
  "nearby_enemies": [{TRACKER_ENTITY_FIELD}],
  "merchant_encounter": {MERCHANT_ENCOUNTER_FIELD},
  "props": [{{"name": "string, 1-3 prominent interactive objects or furniture in the room", "state": "string (e.g. 'Present')"}}],
  "physical_updates": {PHYSICAL_UPDATE_FIELD},
  "focal_point": "string, immediate local micro focal point or stance within the room (e.g. 'Player\\'s Desk', 'By the glass window', 'Sitting on the bench')",
  "location": "string, 3-tiered physical location: Zone ➔ Primary Place ➔ Sub-Area (e.g. 'Oakhaven Private Academy ➔ Class 2-1 (Homeroom) ➔ Player\\'s Desk')",
  "image_prompt": "string, a short (1-2 sentence) visual description of the opening scene"
}}"""

ACTOR_POSE_FIELD = """{"Character Name": {"posture": "standing|seated|kneeling|leaning|...", "holding": "item name or Empty hands"}}"""

OUTCOME_SCHEMA = f"""{{
  "scene_title": "string, 2-5 word atmospheric narrative chapter heading (e.g. 'Echoes in the Stacks')",
  "outcome_narrative": "string, paragraphs narrating exclusively the execution and immediate consequence of the NEW action: (1) how the player carries out their immediate choice with class/race flavor, (2) the immediate outcome and instant NPC reaction based on the check tier. Focus strictly on executing the player's immediate decision. NEVER repeat, recap, or re-quote past dialogue/events from RECENT HISTORY; start immediately from the new action and move forward. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone. For 'Failure' or 'Critical Failure', enforce FAIL-FORWARD: narrate complications, escalations, or success-at-a-cost rather than static roadblocks. Do NOT contradict the check tier.",
  "next_narrative": "string, paragraphs establishing exclusively the subsequent scene aftermath: environmental shifts, physical atmosphere, what NPCs do or say next, and new tension leading into the upcoming choices. Do NOT re-narrate or re-hash the action execution from `outcome_narrative`. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone. FOLLOW THE ACTIVE DIALOGUE DIRECTIVE for how much spoken dialogue to include.",
  "next_choices": [
    {{"label": "string (concise contextual roleplay or exploration action, max 6-8 words)", "stat": "STR|PER|END|CHA|INT|AGI|LUK|ITEM|NONE", "requirement": 0-12, "mp_cost": 0, "intent": "general_action|dialogue_init|dialogue_exit|movement|social_invite|phone_contact_exchange|romantic_confession|affection_touch|intimate_act|disclosure_inquiry|investigate_clue|area_scout|stealth_covert|rest_sleep|party_recruit|gift_offer|merchant_trade|inspect_board|media_capture|phone_comm", "sub_intent": "string (optional: kiss|foreplay|manual_give|manual_receive|manual_mutual|oral_give|oral_receive|oral_mutual|intercourse|anal_give|anal_receive|anal_mutual|aftercare|redress|date|confession|lockpick|pickpocket|gamble|use_item|deduce_clues|explore|combat_flee or empty)", "target_npc": "string (exact NPC name if targeting an NPC, else empty)", "ends_dialogue": false, "dismisses_npc": false, "gold_spent": 0, "triggers_loot_roll": false}}
  ],
  "cast_events": [{CAST_EVENT_FIELD}],
  "actor_poses": {ACTOR_POSE_FIELD},
  "episodic_memory": "string or null, 1 concise sentence summarizing any notable personal fact, promise, or emotional moment the active NPC will remember from this turn, or null if routine",
  "image_prompt": "string, a short (1-2 sentence) visual description of NEW scene"
}}"""

COMBAT_OUTCOME_SCHEMA = f"""{{
  "scene_title": "string, 2-5 word atmospheric combat chapter heading",
  "outcome_narrative": "string, vivid combat paragraphs narrating the player's action and the enemy counter-attack according to the pre-computed combat directive. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone.",
  "next_narrative": "string, paragraphs describing the immediate battlefield aftermath, enemy stances, and tension. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone.",
  "cast_events": [{CAST_EVENT_FIELD}],
  "actor_poses": {ACTOR_POSE_FIELD},
  "episodic_memory": "string or null, 1 concise sentence if a memorable combat turning point occurred, else null",
  "image_prompt": "string, a short (1-2 sentence) visual description of the combat scene"
}}"""

SOCIAL_ARBITER_SCHEMA = f"""{{
  "relationship_updates": [{RELATIONSHIP_UPDATE_FIELD}],
  "new_entities": [{{"type": "person|place|faction", "name": "string (token if new)", "race": "string if person", "species": "cat|fox|wolf|rabbit|tiger|lion|cheetah|fennec|mouse|bear|bird|reptile|snake|dragon|human", "social_role_type": "student_peer|faculty_staff|adult_service|general", "gender": "male|female|other (if person)", "appearance": {{"eye_color": "string (e.g. sapphire blue, emerald green, glowing purple, ruby red, amethyst, heterochromatic blue-green)", "hair_color": "string", "hair_length": "string", "hair_style": "string", "stature": "string", "skin_color": "string (humanoids)", "skin_type": "furry|feathered|scaly|synthetic|skin", "coat_color": "string (beastfolk/monsters e.g. snow white fur, midnight black, pastel pink, cerulean blue, golden-cream, lavender, calico)", "distinctive_features": "string (tails, ears, scars, tattoos)", "outfit_style": "string (clothing style)", "breast_size": "string (NSFW female only: tactile-fused cup e.g. 'Bouncy & Sensitive DD-Cup', 'Soft & Downy Chest Fur B-Cup', 'Tender & Delicate Petite A-Cup')", "penis_size": "string (NSFW male only: tactile-fused size e.g. 'Veined & Firm 7.5\"', 'Sleek Scaled Base & Firm 8\"', 'Warm & Pulsing Average')", "intercourse_experience": "virgin|non_virgin|unknown (NSFW only)", "oral_experience": "virgin|has_given|has_received|has_given_and_received|unknown (NSFW only)", "intimate_demeanor": "string (NSFW only: private demeanor)", "intimate_dynamic": "string (NSFW only: power dynamic, proactivity, & drive)", "sensitive_spots": "string (NSFW only: 1-3 spots or None)", "turn_ons": "string (NSFW only: 1-3 triggers or None)", "fetishes": "string (NSFW only: 1-3 kinks or None/Vanilla)"}}, "description": "short sentence", "disposition": "friendly|neutral|hostile", "traits": ["2-3 traits"], "motivation": "string", "mannerisms": "string", "descriptor": "string (persons only: short physical descriptor matching how the prose first describes them, e.g. 'man in a disheveled investigator coat')"}}],
  "npc_memories": [
    {{"npc_name": "string", "memory_fact": "string, what they specifically remember about the player's action this turn", "sentiment_delta": 1, "importance": 1, "emotional_tone": "grateful|flustered|suspicious|resentful|curious|warm|amused|guarded", "open_thread": "unresolved question, promise, or tension to follow up later, or empty"}}
  ]
}}"""

CLASSIFY_SCHEMA = """{
  "stat": "STR|PER|END|CHA|INT|AGI|LUK|ITEM",
  "requirement": 2-12,
  "mp_cost": 0,
  "intent": "general_action|dialogue_init|dialogue_exit|movement|social_invite|phone_contact_exchange|romantic_confession|affection_touch|intimate_act|disclosure_inquiry|investigate_clue|area_scout|stealth_covert|rest_sleep|party_recruit|gift_offer|merchant_trade|inspect_board|media_capture|phone_comm",
  "sub_intent": "string (optional: kiss|foreplay|manual_give|manual_receive|manual_mutual|oral_give|oral_receive|oral_mutual|intercourse|anal_give|anal_receive|anal_mutual|aftercare|redress|date|confession|lockpick|pickpocket|gamble|use_item|deduce_clues|explore|combat_flee or empty)",
  "target_npc": "string (exact NPC name if targeting an NPC, else empty)",
  "target_location": "string (destination place name if intent is movement, else empty)",
  "ends_dialogue": false,
  "dismisses_npc": false,
  "gold_spent": 0,
  "triggers_loot_roll": false,
  "breakthrough_leveraged": false,
  "is_memory_recall": false,
  "recall_query": "string (if is_memory_recall is true, output the core subject/entity the player is trying to remember, otherwise empty)",
  "reasoning": "string, one sentence"
}"""

NEXT_STORY_QUEST_SCHEMA = """{
  "title": "string, unique evocative Story Quest title (NOT 'Unfolding Crisis' or generic phrases)",
  "archetype": "string, creative scenario-appropriate main quest archetype",
  "objective": "string, rich 2-3 sentence objective with specific story goal, stakes, and motivation",
  "sub_quests": [
    {
      "id": 1,
      "archetype": "string, creative sub-quest archetype 1 (e.g. Forensics / Infiltration / Escort)",
      "text": "string, specific concrete sub-quest goal 1",
      "waypoints": [
        {"stage_index": 1, "stage_label": "string, arrival/lead task", "target_location": "Zone -> Primary Place A", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "string, investigation/obstacle task", "target_location": "Zone -> Primary Place B", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "string, resolution/extraction/delivery task", "target_location": "Zone -> Primary Place C", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "skill_check"}
      ]
    },
    {
      "id": 2,
      "archetype": "string, creative sub-quest archetype 2 (e.g. Investigation / Alchemy / Heist)",
      "text": "string, specific concrete sub-quest goal 2",
      "waypoints": [
        {"stage_index": 1, "stage_label": "string, arrival/lead task", "target_location": "Zone -> Primary Place D", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "string, investigation/obstacle task", "target_location": "Zone -> Primary Place D", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "string, resolution/extraction/delivery task", "target_location": "Zone -> Primary Place E", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "skill_check"}
      ]
    },
    {
      "id": 3,
      "archetype": "string, creative sub-quest archetype 3 (e.g. Diplomacy / Monster Hunting / Interception)",
      "text": "string, specific concrete sub-quest goal 3",
      "waypoints": [
        {"stage_index": 1, "stage_label": "string, arrival/lead task", "target_location": "Zone -> Primary Place F", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "string, investigation/obstacle task", "target_location": "Zone -> Primary Place F", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "string, resolution/extraction/delivery task", "target_location": "Zone -> Primary Place F", "target_node_id": "string, exact node ID if known or empty", "target_npc": "string or empty", "completion_trigger": "skill_check"}
      ]
    }
  ]
}"""

CUSTOM_STARTER_GEAR_SYSTEM_PROMPT = """Design a starting equipment loadout for a novice character. All gear must be Level 1 starter-appropriate: humble, grounded, and plausible for a complete beginner. No legendary, divine, ancient, glowing, masterwork, or high-tech prototype items.

Provide gear for these slots: Head, Armor, Top, Bottom, Gloves, Shoes, Shield, Accessory 1, Accessory 2.

=== THEMATIC MATCHING ===
The gear MUST match the character's profession both functionally and aesthetically. Read the profession carefully and design gear that makes narrative sense for that role.

Examples of good matching:
• Paladin → Full greathelm, plate cuirass, linen vestment, plate legguards, blessed gauntlets, armored sabatons, tower shield, holy amulet
• Archmage → Arcane circlet, (no combat armor), silk robes, enchanted robe skirt/trousers, (bare hands or arcane gloves), rune-stitched boots, (no shield), mana-focus ring
• Rogue → Shadow cowl, leather jerkin, dark jacket, dark trousers, fingerless cutpurse mitts, silent-step boots, (no shield), lockpick ring

=== WACKY, JOKE, AND OUT-OF-PLACE PROFESSIONS ===
If the profession is unusual, comedic, satirical, surreal, or otherwise "out of place" — FULLY COMMIT to the theme. Do not give them generic gear. Invent creative, humorous, and narratively fitting novice items that match the absurdity of the concept.

Wacky examples:
• "Rubber Duck Inquisitor" → Head: "Squeaky Duckling Mitre", Top: "Bright Yellow Waterproof Smock", Bottom: "Rubber Waders", Gloves: "Yellow Dishwashing Gauntlets", Shoes: "Non-slip Rubber Deck Boots", Shield: "Porcelain Tub Lid Buckler", Accessory 1: "Soap-on-a-Rope Rosary"
• "Professional Couch Potato" → Head: "Faded Baseball Cap", Top: "Oversized Grey Hoodie", Bottom: "Fleece Sweatpants", Shoes: "Memory Foam House Slippers", Accessory 1: "Universal TV Remote", Accessory 2: "Half-eaten Bag of Chips"
• "Taco Truck Luchador" → Head: "Luchador Wrestling Mask with Taco Horns", Top: "Grease-Stained Wrestling Cape", Bottom: "Spandex Lucha Trunks", Gloves: "Salsa-Stained Fingerless Mitts", Shoes: "Steel-Toed Wrestling Boots", Accessory 1: "Lucky Jalapeño Pendant"
• "Banana Samurai" → Head: "Banana-Yellow Kabuto Helm", Armor: "Peel-Plate Cuirass", Top: "Musa Silk Haori", Bottom: "Yellow Hakama", Gloves: "Fruit-Leather Tekko", Shoes: "Straw Waraji", Accessory 1: "Bunch-of-Bananas Mon Badge"

=== SLOT RULES ===
- Head: Any headwear appropriate to the role (helm, cap, hood, hat, crown, mask, circlet, goggles, mitre, etc.)
- Armor: Combat body armor ONLY (plate cuirass, leather jerkin, kevlar vest, etc.). Set to null for mages, civilians, support classes, and non-combat professions.
- Top: Civilian garment worn over or instead of armor (shirt, tunic, robe, jacket, smock, blouse, etc.)
- Bottom: Lower garment (trousers, breeches, skirt, hakama, shorts, slacks, etc.)
- Gloves: Hand protection or working gloves. Set to null if the class works bare-handed (e.g. brawlers, hand-gesturing mages).
- Shoes: Footwear (boots, sandals, sneakers, greaves, slippers, etc.)
- Shield: Defensive off-hand item. Set to null for mages, two-handed weapons users, ranged classes, and most civilians. Can be creative (a tub lid, a trash can lid, a binder folder) for wacky professions.
- Accessory 1 & 2: Jewelry, trinkets, tools, badges, gadgets, wearable items. Be creative and thematic. Set to null if nothing fits.

=== GENDER & SPECIES RULES ===
- MALE characters: Strictly male/masculine or unisex garments only. NEVER assign skirts, dresses, corsets, or female-coded items.
- FEMALE characters: Female/feminine or unisex garments (skirts, blouses, dresses, tailored slacks, leggings are all fine).
- Human/tailless species: NEVER assign tail-slotted, ear-slotted, or horn-slotted garments.

- slot_cost: 1 (light/wearable) to 3 (heavy/bulky).

Respond with ONLY a single valid JSON object matching the schema exactly. No prose, no markdown code fences."""

CUSTOM_STARTER_GEAR_SCHEMA = """{
  "Head": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-2} or null,
  "Armor": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-3} or null,
  "Top": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-3} or null,
  "Bottom": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-3} or null,
  "Gloves": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-3} or null,
  "Shoes": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-3} or null,
  "Shield": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-3} or null,
  "Accessory 1": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-2} or null,
  "Accessory 2": {"name": "string", "description": "short flavor sentence, no numbers or stats", "slot_cost": 1-2} or null
}"""
