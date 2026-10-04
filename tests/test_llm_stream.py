import pytest
import asyncio
from llm_client import StreamingNarrativeExtractor

@pytest.mark.asyncio
async def test_streaming_narrative_extractor():
    collected = []
    
    async def cb(token: str):
        collected.append(token)
        
    extractor = StreamingNarrativeExtractor(cb)
    
    # Simulate a JSON chunked response
    chunks = [
        '{\n  "scene_title": "The Tavern",\n  ',
        '"narrative": "You step into the \\"Tavern\\".\\nIt is ',
        'warm and cozy.\\n\\n\\u2728 Magic!",\n  "choices": []\n}'
    ]
    
    for chunk in chunks:
        await extractor.process_chunk(chunk)
        
    extracted_text = "".join(collected)
    expected = 'You step into the "Tavern".\nIt is warm and cozy.\n\n✨ Magic!'
    
    assert extracted_text == expected, f"Expected {expected}, got {extracted_text}"

@pytest.mark.asyncio
async def test_streaming_narrative_extractor_split_chunks():
    collected = []
    
    async def cb(token: str):
        collected.append(token)
        
    extractor = StreamingNarrativeExtractor(cb)
    
    # Simulate tiny chunks breaking escaping
    stream = '{"narrative": "A\\\\B\\"C\\nD"}'
    
    for char in stream:
        await extractor.process_chunk(char)
        
    extracted_text = "".join(collected)
    expected = 'A\\B"C\nD'
    
    assert extracted_text == expected, f"Expected {expected}, got {extracted_text}"
