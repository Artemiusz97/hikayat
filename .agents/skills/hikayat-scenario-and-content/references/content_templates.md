# Hikayat Content & Schema Templates (`data/`, `mechanics/`)

Minimal valid shapes matching Hikayat's schema loaders (`scenario_data.py`, `character_data.py`, `mechanics/world/locations/`, `mechanics/combat/items/envelope.py`, `mechanics/combat/equipment/metadata.py`).

---

## 1. Genre & Starting Hook Entry (`data/genres.json`)

Every genre/modifier defines `category`, `prompt_instructions`, `allowed_mechanics`, and **6 `starting_hooks`** (2 `"hub_launchpad"`, 2 `"in_media_res"`, 2 `"delve_threshold"`):

```json
{
  "<scenario_key>": {
    "name": "Display Genre Name",
    "category": "genre",
    "prompt_instructions": [
      "Core tonal and narrative directive 1.",
      "Core mechanic/stakes directive 2."
    ],
    "allowed_mechanics": [
      "merchant_encounters",
      "relationship_meter",
      "contact_list",
      "faction_reputation",
      "tactical_combat"
    ],
    "starting_hooks": [
      {
        "archetype": "hub_launchpad",
        "starting_minute": 540,
        "hook": "at 09:00 AM inside a bustling hub venue as regulars trade rumors",
        "suggested_location": "{session_kingdom} ➔ Hub Facility ➔ Main Hall",
        "directive": "Open Hub Exploration: establish 2-3 NPCs, spatial anchors, and open choices.",
        "focal_point": "Corner booth beside the notice board",
        "scheduled_roles": ["Venue Host", "Local Informant"],
        "initial_physical_state": {
          "posture": "sitting",
          "posture_qualifier": "at the timber table",
          "holding": "warm mug",
          "stance": "Relaxed",
          "composure": "composed",
          "is_wet": 0
        },
        "starting_prop": {
          "name": "Stamped Guild Pass",
          "item_type": "tool",
          "effect": "Grants initial entry credentials inside the hub district."
        },
        "visual_cues": "warm lantern glow, timber rafters, ambient crowd, detailed interior"
      }
    ]
  }
}
```

---

## 2. Class Template Entry (`data/class_templates.json`)

```json
{
  "<scenario_key>": {
    "<Class Name>": {
      "description": "Concise one-sentence class archetype description.",
      "starting_items": [
        ["Emblem Focus", "Quest", "Short functional effect text.", 1]
      ],
      "starter_gear": {
        "Head": ["Traveler Hood", "Lightweight hood shielding against rain.", 1],
        "Weapon": ["Iron Broadsword", "Balanced steel blade.", 2],
        "Armor": ["Brigandine Jerkin", "Riveted leather coat.", 2],
        "Top": ["Woven Linen Tunic", "Breathable tunic worn beneath armor.", 1],
        "Bottom": ["Sturdy Riding Trousers", "Reinforced wool trousers.", 1],
        "Gloves": ["Leather Half-Gloves", "Supple grip gloves.", 1],
        "Shoes": ["Cobbled Leather Boots", "Weatherproof buckled boots.", 1],
        "Shield": ["Oak Buckler", "Light round parrying shield.", 1]
      }
    }
  }
}
```

---

## 3. Structured SQLite Item Effect Envelopes

- **Consumable / General Item (`mechanics/combat/items/envelope.py`):**
  ```python
  from mechanics.combat.items.envelope import serialize_item

  effect_str = serialize_item({
      "category": "consumable",
      "hp_restore": 50,
      "mp_restore": 25,
      "uses": 1,
  })  # Produces: [ITEM_JSON]{"category":"consumable",...}
  ```

- **Equipment / Gear (`mechanics/combat/equipment/metadata.py`):**
  ```python
  from mechanics.combat.equipment.metadata import build_equipment_effect_str, normalize_dual_tier_metadata

  meta = normalize_dual_tier_metadata({
      "name": "Balanced Steel Longsword",
      "item_type": "Weapon",
      "archetype": "longsword",
      "quality_tier": "regular",     # worn | regular | high_quality | masterwork
      "enchantment_tier": "none",    # none | tier_3 | tier_2 | tier_1
      "tier": 3,
      "base_dt": 0,
      "multiplier": 1.15,
      "stat_modifiers": {},
  })
  effect_str = build_equipment_effect_str(meta)  # Produces: [GEAR_JSON]{...}
  ```
