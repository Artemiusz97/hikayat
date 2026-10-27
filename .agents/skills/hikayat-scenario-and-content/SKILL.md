---
name: hikayat-scenario-and-content
description: "Use this skill whenever authoring or expanding Hikayat game content: scenarios, genres, starting hooks, 3-tier spatial locations, classes, weapons/armor/consumables ([ITEM_JSON]/[GEAR_JSON]), spells, factions, bounties/clues, procedural namegen, or 5-language localization (en, pl, ms, zh, de)."
---

# Hikayat Scenario, Content & Localization Authoring Guide

All content in Hikayat feeds directly into deterministic Python mechanics. Always follow the exact schemas below rather than inventing ad-hoc JSON fields.

---

## 1. Full 8-Point Scenario / Genre Expansion Checklist

When adding or overhauling a playable scenario (see `tests/test_anomalous_incursions.py` as the reference pattern), wire **all 8 touchpoints**:

1. **`data/scenarios.json`**: Register scenario key (`name`, `display_name`, `emoji`, `dropdown_label`, `tags`, `description`, `tone_guidelines`).
2. **`scenario_data.py`**: Add scenario key aliases in `resolve_scenario_key()` and tag aliases in `resolve_tag_keys()`.
3. **`data/genres.json`**: Define genre/modifier metadata:
   - `category`: `"genre"` or `"modifier"`.
   - `allowed_mechanics`: Subset of `"merchant_encounters"`, `"relationship_meter"`, `"contact_list"`, `"faction_reputation"`, `"tactical_combat"`, `"smartphone_hub"`, etc.
   - `starting_hooks`: Provide **6 balanced hooks** — 2 `"hub_launchpad"`, 2 `"in_media_res"`, 2 `"delve_threshold"`. Each hook includes `starting_minute`, `hook`, `suggested_location` (3-tier `➔` path), `directive`, `focal_point`, `scheduled_roles`, `initial_physical_state` (`posture`, `posture_qualifier`, `holding`, `stance`, `composure`, `is_wet`), `starting_prop` (`name`, `item_type`, `effect`), and `visual_cues`.
4. **`data/class_templates.json`**: Add scenario classes with `description`, `starting_items` (`[name, item_type, effect_desc, qty]`), and `starter_gear` slot map (`Head`, `Weapon`, `Armor`, `Top`, `Bottom`, `Gloves`, `Shoes`, `Shield` -> `[name, desc, tier]`).
5. **`data/starting_weapons.json`**: Map scenario key to its list of canonical starter weapon names (`[]` if unarmed slice-of-life/high-school).
6. **`data/locations_seed.json` & `mechanics/world/locations/`**: Seed the 3-tier world graph and register any dynamic `{session_*}` location tokens in `hierarchy.py` (`resolve_session_location_tokens`).
7. **`namegen.py` & `data/namegen_data.json`**: Add culturally/thematically appropriate name pools, settlement/agency generators, and faction names.
8. **Scenario Rosters & Gear Tables** (if specialized): Hook into `mechanics/social/` (`school_roster.py`, `agent_roster.py`) and `mechanics/combat/items/`.

---

## 2. 3-Tier Spatial Locations (`data/locations_seed.json`)

World geography uses a 3-tier hierarchy joined by `" ➔ "` (`Zone ➔ Primary Facility ➔ Sub-Location`):

```json
{
  "id": "zone_school_main",
  "name": "Main Academy Campus",
  "is_hub": true,
  "theme": "Modern Multistory High School Academic Wing",
  "features": "Polished linoleum corridors, classroom wings, library, rooftop.",
  "sensory": "School bells, muffled lectures, cedar chalkboards, bright daylight.",
  "primary_locations": [
    {
      "id": "loc_homeroom",
      "name": "Homeroom Classroom",
      "sub_locations": [
        {
          "id": "sub_homeroom_classroom_entrance",
          "name": "Classroom Sliding Door Entrance",
          "is_entrance": 1
        },
        {
          "id": "sub_player_desk",
          "name": "Player's Desk"
        }
      ]
    }
  ]
}
```
- **Entrance Invariant**: Every `primary_location` **must** mark at least one `sub_location` with `"is_entrance": 1` so `graph_seeder.py` and `pathfinding.py` can wire bidirectional traversal edges.
- Access restrictions, curfew rules, and key gates are evaluated in `mechanics/world/locations/access_gate.py`.

---

## 3. Equipment, Weapons, Consumables & Spells

- **Stats (`character_data.py`)**: 7 stats (`STR`, `PER`, `END`, `CHA`, `INT`, `AGI`, `LUK`), base `1`, point-buy pool `5`, hard cap `10`.
  - HP: `200 + (END * 100)` | Mana: `50 + (END * 25)` | Inventory slots: `30 + (STR * 3)`.
- **Rarity Tiers (`mechanics/combat/equipment/tables.py`)**: `3` = Standard (70%), `2` = Enchanted/Superior (25%), `1` = Legendary/Relic (5%).
- **Weapon & Armor Archetypes (`mechanics/combat/items/`)**:
  - Weapons (`weapons.py` -> `WEAPON_ARCHETYPES`): `mass` (`light`/`medium`/`heavy`), `handedness` (`1H`/`Versatile`/`2H`), `attack_types`, `default_damage` (`physical`/`magical`/`ballistic`...), `multiplier`, `crit_bonus`, `base_acc`, `base_eva`, optional `projectile_type`.
  - Armor & Slots (`armors.py`, `shields.py`, `headwear.py`, `gloves.py`, `shoes.py`, `accessories.py`, `clothing.py`): Damage Threshold (`base_dt`, `type_dt`) + affixes from `RANDOM_AFFIX_POOL`.
- **SQLite Item Effect Envelopes (`envelope.py`, `equipment/metadata.py`)**:
  - Structured items serialize metadata into the `effect` column with prefix `[ITEM_JSON]{...}`, `[GEAR_JSON]{...}`, or `[SPELLBOOK_JSON]{...}` via `serialize_item()` / `build_equipment_effect_str()`.
  - Key items (`item_type == "Key Item"`) are protected from dropping.
- **Spells (`mechanics/combat/spells/`)**: Register canonical spells in `registry.py`, class starter kits in `kits.py`, and procedural scaling in `procedural.py`.

---

## 4. Dual-Layer 5-Language Localization (`en`, `pl`, `ms`, `zh`, `de`)

Whenever adding item categories, 2H weapon keywords, enemy affixes, movement prefixes, or UI labels, update **both** layers across all 5 locales:
1. **Backend Mechanics (`localization/{en,pl,ms,zh,de}.py`)**: `ENEMY_AFFIXES`, `ITEM_ICON_KEYWORDS`, `TWO_HANDED_KEYWORDS`, and localized intent/item lemmas aggregated by `localization/__init__.py`.
2. **Frontend SPA (`web/src/locales/{en,pl,ms,zh,de}.json`)**: Mirror every new `react-i18next` translation key across all 5 JSON files.

---

## 5. Content Validation Commands
```bash
python -c "import scenario_data, character_data; scenario_data.load_genres(reload=True); character_data.load_class_templates(reload=True)"
pytest tests/test_locations.py tests/test_class_templates.py tests/test_tags_scenarios_refactor.py -q
```
