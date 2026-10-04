"""
LLM JSON response schemas and custom starter gear generation prompts/schemas for Hikayat.
"""

CHARACTER_OUTCOME_FIELD = """{"name": "string, exact character name", "hp_change": integer, "temp_hp_change": integer, "mp_change": integer, "gold_change": integer, "items_gained": ["string"], "items_lost": ["string"], "status_effects": ["short condition tag"]}"""

TRACKER_ENTITY_FIELD = """{"name": "string", "level": "integer (only if friendly companion)", "hp": "integer (only if friendly companion)", "max_hp": "integer (only if friendly companion)", "mp": "integer (only if friendly companion)", "max_mp": "integer (only if friendly companion)", "status_effects": ["short condition tag"]}"""

MERCHANT_ENCOUNTER_FIELD = """{"present": boolean, "name": "string (token if new)", "description": "short flavor sentence"}"""

RELATIONSHIP_UPDATE_FIELD = """{"npc_name": "string", "delta_score": integer (-10 to +10, scale: +1..+3 minor chat, +4..+6 helpful/check success, +7..+10 major milestone), "track": "platonic|romantic", "milestone_event": "first_kiss|kiss|date|confession|oral_give|oral_receive|intercourse|none", "memory_summary": "string (1 short evocative sentence describing milestone, or empty)", "revealed_attributes": ["sensitive_spots", "turn_ons", "fetishes", "demeanor", "dynamic", "intercourse_experience", "oral_experience", "all_intimate"], "intercourse_experience": "virgin|non_virgin|unknown", "oral_experience": "virgin|has_given|has_received|has_given_and_received|unknown", "intimate_revealed": boolean, "sensitive_spots_revealed": boolean, "turn_ons_revealed": boolean, "fetishes_revealed": boolean, "demeanor_revealed": boolean, "dynamic_revealed": boolean, "intercourse_revealed": boolean, "oral_revealed": boolean, "new_sensitive_spots": "string or empty", "new_turn_ons": "string or empty", "new_fetishes": "string or empty", "new_demeanor": "string or empty", "new_dynamic": "string or empty", "new_traits": ["short 1-2 word personality trait"], "new_preferences": ["short 1-3 word preference tag"]}"""

FACTION_UPDATE_FIELD = """{"faction_name": "string", "delta_score": integer, "notes": "string"}"""

PHYSICAL_UPDATE_FIELD = """{"actors": {"Character Name": {"posture": "standing|seated|kneeling|prone", "holding": "item name or empty", "clothing": {"top": "clothed|off|disheveled", "bottom": "clothed|off", "under_top": "worn|off", "under_bottom": "worn|off"}, "stance": "Guarded|Melee|Cover|Ready"}}, "props": [{"name": "string", "state": "string"}], "intimate_contact": "string or null", "combat_focus": "string or null"}"""

ENTITY_AUDIT_FIELD = """{"present_named_characters": ["string, list of EVERY named individual physically present in the immediate room right now"], "speaking_characters": ["string, list of NPCs who speak aloud in this scene"], "departed_characters": ["string, list of NPCs who departed, exited, said goodbye, or left during this turn"]}"""

SCENE_SCHEMA = f"""{{
  "scene_title": "string, 2-5 word atmospheric narrative chapter heading (e.g. 'Echoes in the Stacks')",
  "entity_audit": {ENTITY_AUDIT_FIELD},
  "narrative": "string, paragraphs establishing scene setting, environment, and upcoming choice context. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone.",
  "choices": [
    {{"label": "string (concise, max 6-8 words)", "stat": "STR|PER|END|CHA|INT|AGI|LUK|ITEM|NONE", "requirement": 0-12, "mp_cost": 0}}
  ],
  "campaign_end_goals": [
    {{"id": "G1", "title": "string, 1st long-term campaign victory condition relevant to scenario", "description": "string, 1-sentence goal description"}},
    {{"id": "G2", "title": "string, 2nd long-term campaign victory condition relevant to scenario", "description": "string, 1-sentence goal description"}},
    {{"id": "G3", "title": "string, 3rd long-term campaign victory condition relevant to scenario", "description": "string, 1-sentence goal description"}}
  ],
  "new_entities": [{{"type": "person|place|faction", "name": "string (token if new)", "race": "string if person", "gender": "male|female|other (if person)", "appearance": {{"eye_color": "string (e.g. sapphire blue, emerald green, glowing purple, ruby red, amethyst, heterochromatic blue-green)", "hair_color": "string", "hair_length": "string", "hair_style": "string", "stature": "string", "skin_color": "string (humanoids)", "skin_type": "furry|feathered|scaly|synthetic|skin", "coat_color": "string (beastfolk/monsters e.g. snow white fur, midnight black, pastel pink, cerulean blue, golden-cream, lavender, calico)", "distinctive_features": "string (tails, ears, scars, tattoos)", "outfit_style": "string (clothing style)", "breast_size": "string (NSFW female only)", "penis_size": "string (NSFW male only)", "intercourse_experience": "virgin|non_virgin|unknown (NSFW only)", "oral_experience": "virgin|has_given|has_received|has_given_and_received|unknown (NSFW only)", "intimate_demeanor": "string (NSFW only: private demeanor)", "intimate_dynamic": "string (NSFW only: power dynamic, proactivity, & drive)", "sensitive_spots": "string (NSFW only: 1-3 spots or None)", "turn_ons": "string (NSFW only: 1-3 triggers or None)", "fetishes": "string (NSFW only: 1-3 kinks or None/Vanilla)"}}, "description": "short sentence", "disposition": "friendly|neutral|hostile", "traits": ["2-3 traits"], "motivation": "string", "mannerisms": "string"}}],
  "npcs_present": [{TRACKER_ENTITY_FIELD}],
  "npc_departures": ["string, exact names of NPCs who departed, exited, or left"],
  "nearby_enemies": [{TRACKER_ENTITY_FIELD}],
  "merchant_encounter": {MERCHANT_ENCOUNTER_FIELD},
  "props": [{{"name": "string, 1-3 prominent interactive objects or furniture in the room", "state": "string (e.g. 'Present')"}}],
  "physical_updates": {PHYSICAL_UPDATE_FIELD},
  "location": "string, 3-tiered physical location: Zone ➔ Primary Place ➔ Sub-Area (e.g. 'Oakhaven Private Academy ➔ Class 2-1 (Homeroom) ➔ Player\'s Desk')",
  "image_prompt": "string, a short (1-2 sentence) visual description of the opening scene"
}}"""

STATE_ARBITER_SCHEMA = """{
  "director_reasoning": "string, 1 concise sentence explaining the mechanical and dramatic consequence of the action and check tier",
  "departed_characters": ["string, exact names of NPCs who departed, exited, or left the room during this turn"],
  "present_characters": ["string, exact names of NPCs who remain physically present in the room right now"],
  "speaking_characters": ["string, exact names of NPCs who speak aloud in this scene"],
  "deceased_characters": ["string, exact names of NPCs or enemies who are definitively killed or slain this turn"],
  "character_outcomes": [
    {"name": "string, exact character name", "hp_change": integer, "mp_change": integer, "gold_change": integer, "items_gained": ["string"], "items_lost": ["string"], "status_effects": ["short condition tag"]}
  ],
  "quest_progress": {
    "completed_sub_quest_id": 0,
    "clue_discovered": "string or empty"
  },
  "fail_forward_complication": "string or empty (if Failure/Crit Fail, the irreversible complication, ambush, or twist)",
  "fulfilled_commitments": [0], 
  "broken_commitments": [0]
}"""

OUTCOME_SCHEMA = f"""{{
  "scene_title": "string, 2-5 word atmospheric narrative chapter heading (e.g. 'Echoes in the Stacks')",
  "entity_audit": {ENTITY_AUDIT_FIELD},
  "outcome_narrative": "string, paragraphs narrating: (1) how the action is executed with class/race flavor, (2) the immediate outcome and NPC reaction based on the check tier. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone. For 'Failure' or 'Critical Failure', enforce FAIL-FORWARD: narrate complications, escalations, or success-at-a-cost rather than static roadblocks. Do NOT contradict the check tier.",
  "next_narrative": "string, paragraphs establishing scene aftermath, environmental shifts, NPC dialogue/reactions, and new tension leading into the upcoming choices. FOLLOW THE ACTIVE STYLE DIRECTIVE for paragraph count and vocabulary tone. FOLLOW THE ACTIVE DIALOGUE DIRECTIVE for how much spoken dialogue to include.",
  "next_choices": [
    {{"label": "string (concise, max 6-8 words)", "stat": "STR|PER|END|CHA|INT|AGI|LUK|ITEM|NONE", "requirement": 0-12, "mp_cost": 0}}
  ],
  "character_outcomes": [{CHARACTER_OUTCOME_FIELD}],
  "physical_updates": {PHYSICAL_UPDATE_FIELD},
  "location": "string, 3-tiered physical location: Zone ➔ Primary Place ➔ Sub-Area (e.g. 'Oakhaven Private Academy ➔ School Library ➔ Study Tables')",
  "npcs_present": [{TRACKER_ENTITY_FIELD}],
  "npc_departures": ["string, exact names of NPCs who departed, exited, or left"],
  "nearby_enemies": [{TRACKER_ENTITY_FIELD}],
  "merchant_encounter": {MERCHANT_ENCOUNTER_FIELD},
  "faction_updates": [{FACTION_UPDATE_FIELD}],
  "faction_promotion_result": "string, 'success' or 'failure' ONLY IF a promotion trial directive explicitly asked for it",
  "image_prompt": "string, a short (1-2 sentence) visual description of NEW scene"
}}"""

SOCIAL_ARBITER_SCHEMA = f"""{{
  "relationship_updates": [{RELATIONSHIP_UPDATE_FIELD}],
  "new_entities": [{{"type": "person|place|faction", "name": "string (token if new)", "race": "string if person", "gender": "male|female|other (if person)", "appearance": {{"eye_color": "string (e.g. sapphire blue, emerald green, glowing purple, ruby red, amethyst, heterochromatic blue-green)", "hair_color": "string", "hair_length": "string", "hair_style": "string", "stature": "string", "skin_color": "string (humanoids)", "skin_type": "furry|feathered|scaly|synthetic|skin", "coat_color": "string (beastfolk/monsters e.g. snow white fur, midnight black, pastel pink, cerulean blue, golden-cream, lavender, calico)", "distinctive_features": "string (tails, ears, scars, tattoos)", "outfit_style": "string (clothing style)", "breast_size": "string (NSFW female only)", "penis_size": "string (NSFW male only)", "intercourse_experience": "virgin|non_virgin|unknown (NSFW only)", "oral_experience": "virgin|has_given|has_received|has_given_and_received|unknown (NSFW only)", "intimate_demeanor": "string (NSFW only: private demeanor)", "intimate_dynamic": "string (NSFW only: power dynamic, proactivity, & drive)", "sensitive_spots": "string (NSFW only: 1-3 spots or None)", "turn_ons": "string (NSFW only: 1-3 triggers or None)", "fetishes": "string (NSFW only: 1-3 kinks or None/Vanilla)"}}, "description": "short sentence", "disposition": "friendly|neutral|hostile", "traits": ["2-3 traits"], "motivation": "string", "mannerisms": "string"}}],
  "quest_updates": [
    {{
      "quest_id": "string, exact ID from context",
      "title": "string",
      "quest_type": "Story Quest|Side Bounty|...",
      "archetype": "string, creative main quest archetype",
      "objective": "string, rich main objective explaining story goals (can be multi-sentence)",
      "completed_sub_quest_ids": [1],
      "goal_progress_updates": {{"G1": 35}},
      "progress": "string e.g. 1/3 Cleared",
      "current_clues": "string, bullet points joined by \\n",
      "status": "Active|Completed|Failed",
      "reward_xp": integer,
      "reward_gold": integer,
      "reward_item": "string or empty",
      "next_chapter_quest": {{
        "title": "string, unique evocative title for Chapter N+1",
        "archetype": "string, creative main quest archetype for Chapter N+1",
        "objective": "string, rich main objective for Chapter N+1",
        "sub_quests": [
          {{"id": 1, "archetype": "string, creative sub-quest archetype", "text": "string, sub-quest goal 1"}},
          {{"id": 2, "archetype": "string, creative sub-quest archetype", "text": "string, sub-quest goal 2"}},
          {{"id": 3, "archetype": "string, creative sub-quest archetype", "text": "string, sub-quest goal 3"}}
        ]
      }}
    }}
  ],
  "npc_memories": [
    {{"npc_name": "string", "memory_fact": "string, what they specifically remember about the player's action this turn", "sentiment_delta": 1, "importance": 1}}
  ]
}}"""

CLASSIFY_SCHEMA = """{
  "stat": "STR|PER|END|CHA|INT|AGI|LUK|ITEM",
  "requirement": 2-12,
  "mp_cost": 0,
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
        {"stage_index": 1, "stage_label": "string, arrival/lead task", "target_location": "Zone -> Primary Place A", "target_npc": "string or empty", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "string, investigation/obstacle task", "target_location": "Zone -> Primary Place B", "target_npc": "string or empty", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "string, resolution/extraction/delivery task", "target_location": "Zone -> Primary Place C", "target_npc": "string or empty", "completion_trigger": "skill_check"}
      ]
    },
    {
      "id": 2,
      "archetype": "string, creative sub-quest archetype 2 (e.g. Investigation / Alchemy / Heist)",
      "text": "string, specific concrete sub-quest goal 2",
      "waypoints": [
        {"stage_index": 1, "stage_label": "string, arrival/lead task", "target_location": "Zone -> Primary Place D", "target_npc": "string or empty", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "string, investigation/obstacle task", "target_location": "Zone -> Primary Place D", "target_npc": "string or empty", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "string, resolution/extraction/delivery task", "target_location": "Zone -> Primary Place E", "target_npc": "string or empty", "completion_trigger": "skill_check"}
      ]
    },
    {
      "id": 3,
      "archetype": "string, creative sub-quest archetype 3 (e.g. Diplomacy / Monster Hunting / Interception)",
      "text": "string, specific concrete sub-quest goal 3",
      "waypoints": [
        {"stage_index": 1, "stage_label": "string, arrival/lead task", "target_location": "Zone -> Primary Place F", "target_npc": "string or empty", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "string, investigation/obstacle task", "target_location": "Zone -> Primary Place F", "target_npc": "string or empty", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "string, resolution/extraction/delivery task", "target_location": "Zone -> Primary Place F", "target_npc": "string or empty", "completion_trigger": "skill_check"}
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
