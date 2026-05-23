from __future__ import annotations

import numpy as np
import pytest
from memory.common.embedding import (
    UnifiedHashEmbeddingModel,
    SentenceTransformerEmbeddingModel,
    EmbeddingAdapter
)
from dsm.embedding import HashEmbeddingModel


def test_unified_hash_embedding_shape_and_type():
    model = UnifiedHashEmbeddingModel(dim=128)
    vec = model.encode("Hello world")
    
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (128,)
    assert vec.dtype == np.float32
    
    # Test batch shape
    batch_vecs = model.encode_batch(["hello", "world"])
    assert isinstance(batch_vecs, np.ndarray)
    assert batch_vecs.shape == (2, 128)


def test_hash_embedding_value_parity():
    legacy_model = HashEmbeddingModel(dim=256)
    unified_model = UnifiedHashEmbeddingModel(dim=256)
    
    text = "Detailed test sentence to ensure mathematical hash parity across model implementations."
    
    legacy_vec = legacy_model.encode(text)
    unified_vec = unified_model.encode(text)
    
    assert isinstance(legacy_vec, list)
    assert isinstance(unified_vec, np.ndarray)
    
    # Convert legacy list to array and check close equality
    assert np.allclose(np.array(legacy_vec, dtype=np.float32), unified_vec)


def test_embedding_adapter_creation():
    model = EmbeddingAdapter.create("hash", dim=128)
    assert isinstance(model, UnifiedHashEmbeddingModel)
    assert model.dim == 128
    
    # Check that invalid backend raises ValueError
    with pytest.raises(ValueError):
        EmbeddingAdapter.create("invalid-backend-name")
