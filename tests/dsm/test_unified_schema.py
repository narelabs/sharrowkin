from __future__ import annotations

import time
import pytest
from memory.common.schema import (
    MemoryKind,
    PriorityVector,
    UnifiedMemorySegment
)


def test_unified_segment_serialization():
    segment = UnifiedMemorySegment(
        id="test-123",
        text="Sample content",
        embedding=[0.1, 0.2, 0.3],
        kind=MemoryKind.EPISODIC,
        value="Custom value",
        description="A test segment",
        category_path=("Test", "Subcategory"),
        utility=0.85
    )
    
    serialized = segment.to_dict()
    assert serialized["id"] == "test-123"
    assert serialized["kind"] == "episodic"
    assert serialized["value"] == "Custom value"
    assert serialized["utility"] == 0.85
    assert serialized["schema_version"] == 1
    
    deserialized = UnifiedMemorySegment.from_dict(serialized)
    assert deserialized.id == "test-123"
    assert deserialized.kind == MemoryKind.EPISODIC
    assert deserialized.value == "Custom value"
    assert deserialized.utility == 0.85
    assert deserialized.schema_version == 1
    assert deserialized.category_path == ("Test", "Subcategory")


def test_legacy_dsm_migration():
    # Simulated dict of legacy MemorySegment (without kind, value, utility, schema_version)
    legacy_dict = {
        "id": "legacy-dsm-id",
        "text": "Legacy DSM Segment Content",
        "description": "DSM legacy record",
        "category_path": ["General", "Code"],
        "embedding": [0.5, 0.5],
        "links": ["link1"],
        "priorities": {
            "relevance": 0.7,
            "importance": 0.6,
            "recency": 0.8,
            "frequency": 0.1
        },
        "created_at": 1000.0,
        "updated_at": 2000.0,
        "last_accessed_at": 2000.0,
        "access_count": 5,
        "metadata": {"foo": "bar"},
        "compressed_from": []
    }
    
    migrated = UnifiedMemorySegment.from_dict(legacy_dict)
    assert migrated.id == "legacy-dsm-id"
    assert migrated.kind == MemoryKind.SEMANTIC  # Default fallback
    assert migrated.value == "Legacy DSM Segment Content"  # Defaults to text
    assert migrated.utility == 1.0  # Default utility
    assert migrated.schema_version == 1  # Standard current version
    assert migrated.priorities.relevance == 0.7
    assert migrated.metadata == {"foo": "bar"}
    assert migrated.links == {"link1"}


def test_legacy_dpm_migration():
    # Simulated dict of legacy MemoryRecord (DPM)
    # uses 'key' instead of 'embedding', and 'last_used_at'
    legacy_dpm_dict = {
        "id": "legacy-dpm-id",
        "kind": "temporal",
        "text": "Legacy DPM Memory text",
        "key": [0.9, 0.1],
        "value": "Legacy DPM value",
        "created_at": 3000.0,
        "last_used_at": 4000.0,
        "utility": 0.95,
        "metadata": {"source": "dpm-test"}
    }
    
    migrated = UnifiedMemorySegment.from_dict(legacy_dpm_dict)
    assert migrated.id == "legacy-dpm-id"
    assert migrated.kind == MemoryKind.TEMPORAL
    assert migrated.embedding == [0.9, 0.1]  # Successfully copied from key
    assert migrated.value == "Legacy DPM value"
    assert migrated.utility == 0.95
    assert migrated.created_at == 3000.0
    assert migrated.last_accessed_at == 4000.0
    assert migrated.metadata == {"source": "dpm-test"}
