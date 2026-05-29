"""Memory module - DSM, RLD, NARE-Field, optimizations."""

from .bridge import MemoryBridge
from .field import MemoryField
from .trace import TraceMemory
from .conversation import ConversationHistory, Message
from .dsm import DynamicSegmentedMemory, MemorySegment, ActiveContext
from .rld import RecursiveLatentDNA, ReasoningGene

__all__ = [
    "MemoryBridge",
    "MemoryField",
    "TraceMemory",
    "ConversationHistory",
    "Message",
    # DSM
    "DynamicSegmentedMemory",
    "MemorySegment",
    "ActiveContext",
    # RLD
    "RecursiveLatentDNA",
    "ReasoningGene",
]
