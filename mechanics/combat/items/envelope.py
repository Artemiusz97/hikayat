from __future__ import annotations
import json
from typing import Dict, Any

ITEM_PREFIX = "[ITEM_JSON]"

def serialize_item(data: dict) -> str:
    """Serializes item metadata into [ITEM_JSON]{...} format."""
    return f"{ITEM_PREFIX}{json.dumps(data, separators=(',', ':'))}"

def parse_item(item: dict) -> dict:
    """Reads the effect field and returns a unified dict."""
    if not item or not isinstance(item, dict):
        return {}
        
    if "metadata" in item and isinstance(item["metadata"], dict):
        return dict(item["metadata"])
        
    effect = str(item.get("effect", ""))
    
    if effect.startswith(ITEM_PREFIX):
        try:
            return json.loads(effect[len(ITEM_PREFIX):])
        except Exception:
            return {}
            
    return {}

def is_item_json(item: dict) -> bool:
    """Returns True if the item is encoded with the ITEM_PREFIX."""
    if not item or not isinstance(item, dict):
        return False
    effect = str(item.get("effect", ""))
    return effect.startswith(ITEM_PREFIX)
