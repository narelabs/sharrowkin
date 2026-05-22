"""Core type definitions for Sharrowkin Agent.

Extracted and adapted from Google Antigravity SDK.
"""

from __future__ import annotations

import enum
from typing import Any, Callable
import pydantic


# =============================================================================
# Tool types
# =============================================================================


class BuiltinTools(str, enum.Enum):
    """Identifiers for builtin tools.

    Attributes:
        LIST_DIR: List directory contents.
        SEARCH_DIR: Search within directories (grep).
        FIND_FILE: Find files by name.
        VIEW_FILE: View file contents.
        CREATE_FILE: Create a new file.
        EDIT_FILE: Edit an existing file.
        RUN_COMMAND: Execute a shell command.
        ASK_QUESTION: Ask the user a question.
        START_SUBAGENT: Invoke a subagent.
        MEMORY_SEARCH: Search DSM memory.
        MEMORY_WRITE: Write to DSM memory.
        ANALYZE_DATA_FLOW: Analyze data flow in code.
        GET_CONTEXT: Get enriched context for code entity.
        FINISH: Finish the conversation.
    """

    LIST_DIR = "list_directory"
    SEARCH_DIR = "search_directory"
    FIND_FILE = "find_file"
    VIEW_FILE = "view_file"
    CREATE_FILE = "create_file"
    EDIT_FILE = "edit_file"
    RUN_COMMAND = "run_command"
    ASK_QUESTION = "ask_question"
    START_SUBAGENT = "start_subagent"
    MEMORY_SEARCH = "memory_search"
    MEMORY_WRITE = "memory_write"
    ANALYZE_DATA_FLOW = "analyze_data_flow"
    GET_CONTEXT = "get_context"
    FINISH = "finish"

    @classmethod
    def read_only(cls) -> list["BuiltinTools"]:
        """Returns tools that only read state."""
        return [
            cls.LIST_DIR,
            cls.SEARCH_DIR,
            cls.FIND_FILE,
            cls.VIEW_FILE,
            cls.MEMORY_SEARCH,
            cls.GET_CONTEXT,
            cls.FINISH,
        ]

    @classmethod
    def file_tools(cls) -> list["BuiltinTools"]:
        """Returns tools that perform file operations."""
        return [
            cls.VIEW_FILE,
            cls.CREATE_FILE,
            cls.EDIT_FILE,
        ]


class ToolCall(pydantic.BaseModel):
    """A tool call in the agent trajectory.

    Attributes:
        id: Unique identifier for the call.
        name: Tool identifier (BuiltinTools or custom string).
        args: Keyword arguments for the tool.
        canonical_path: Normalized filesystem path for file-related tools.
    """

    name: BuiltinTools | str
    args: dict[str, Any] = pydantic.Field(default_factory=dict)
    id: str | None = None
    canonical_path: str | None = None


class ToolResult(pydantic.BaseModel):
    """Result of a tool execution.

    Attributes:
        id: Identifier correlating with ToolCall.id.
        name: The name of the tool that was executed.
        result: The tool's return value.
        error: Error message if execution failed.
        exception: The original exception if execution failed.
    """

    model_config = pydantic.ConfigDict(
        extra="ignore", arbitrary_types_allowed=True
    )

    name: BuiltinTools | str
    id: str | None = None
    result: Any = None
    error: str | None = None
    exception: Exception | None = pydantic.Field(default=None, exclude=True)


PythonTool = Callable[..., Any]


# =============================================================================
# Step types
# =============================================================================


class UsageMetadata(pydantic.BaseModel):
    """Token usage metadata from the model API.

    Attributes:
        prompt_token_count: Number of tokens in the prompt.
        cached_content_token_count: Number of cached tokens.
        candidates_token_count: Number of tokens in generated candidates.
        thoughts_token_count: Number of tokens used for thinking.
        total_token_count: Sum of all tokens.
    """

    prompt_token_count: int | None = None
    cached_content_token_count: int | None = None
    candidates_token_count: int | None = None
    thoughts_token_count: int | None = None
    total_token_count: int | None = None


class StepType(str, enum.Enum):
    """High-level type of a step."""

    TEXT_RESPONSE = "TEXT_RESPONSE"
    TOOL_CALL = "TOOL_CALL"
    SYSTEM_MESSAGE = "SYSTEM_MESSAGE"
    COMPACTION = "COMPACTION"
    FINISH = "FINISH"
    UNKNOWN = "UNKNOWN"


class StepSource(str, enum.Enum):
    """Source of a step."""

    SYSTEM = "SYSTEM"
    USER = "USER"
    MODEL = "MODEL"
    UNKNOWN = "UNKNOWN"


class StepTarget(str, enum.Enum):
    """Target of a step interaction."""

    USER = "TARGET_USER"
    ENVIRONMENT = "TARGET_ENVIRONMENT"
    UNSPECIFIED = "TARGET_UNSPECIFIED"
    UNKNOWN = "UNKNOWN"


class StepStatus(str, enum.Enum):
    """Status of a step."""

    ACTIVE = "ACTIVE"
    DONE = "DONE"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    ERROR = "ERROR"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"


class Step(pydantic.BaseModel):
    """Structure representing one action in the agent trajectory.

    Attributes:
        id: Unique string identifier for the step.
        step_index: Integer index of the step in the trajectory.
        type: The high-level type of the step.
        source: The source that generated the step.
        target: The target interacting with this step.
        status: The status of the step.
        content: The output of the step.
        thinking: Model reasoning/thinking for this step.
        content_delta: Text added since the last update.
        thinking_delta: Thinking added since the last update.
        tool_calls: List of tool calls associated with the step.
        error: Short error message if the step failed.
        is_complete_response: True if this is a completed model response.
        structured_output: Structured output from finish step.
        usage_metadata: Token usage for this step's model invocation.
    """

    id: str = ""
    step_index: int = 0
    type: StepType = StepType.UNKNOWN
    source: StepSource = StepSource.UNKNOWN
    target: StepTarget = StepTarget.UNKNOWN
    status: StepStatus = StepStatus.UNKNOWN
    content: str = ""
    content_delta: str = ""
    thinking: str = ""
    thinking_delta: str = ""
    tool_calls: list[ToolCall] = pydantic.Field(default_factory=list)
    error: str = ""
    is_complete_response: bool | None = None
    structured_output: Any | None = None
    usage_metadata: UsageMetadata | None = None

    model_config = pydantic.ConfigDict(extra="allow")


# =============================================================================
# Hook types
# =============================================================================


class HookResult(pydantic.BaseModel):
    """Result of a decision hook execution.

    Attributes:
        allow: Whether execution should proceed.
        message: Optional explanation or response message.
    """

    model_config = pydantic.ConfigDict(extra="ignore")

    allow: bool = True
    message: str = ""


class QuestionResponse(pydantic.BaseModel):
    """Individual response for an AskQuestion entry.

    Attributes:
        selected_option_ids: List of option IDs selected.
        freeform_response: Freeform text response.
        skipped: If true, the question is marked as skipped.
    """

    model_config = pydantic.ConfigDict(extra="ignore")

    selected_option_ids: list[str] | None = None
    freeform_response: str = ""
    skipped: bool = False


class QuestionHookResult(pydantic.BaseModel):
    """Result of an interaction containing a list of responses.

    Attributes:
        responses: List of QuestionResponse objects.
        cancelled: If true, the interaction was cancelled.
    """

    model_config = pydantic.ConfigDict(extra="ignore")

    responses: list[QuestionResponse]
    cancelled: bool = False


# =============================================================================
# Memory types (DSM/RLD specific)
# =============================================================================


class MemorySegment(pydantic.BaseModel):
    """A segment in DSM memory.

    Attributes:
        id: Unique identifier.
        content: Text content of the segment.
        category: Category path (e.g., "programming/python").
        embedding: Dense embedding vector.
        importance: Importance score (0-1).
        timestamp: Creation timestamp.
    """

    id: str
    content: str
    category: str
    embedding: list[float] | None = None
    importance: float = 0.5
    timestamp: float = 0.0


class ReasoningGene(pydantic.BaseModel):
    """A reasoning gene in RLD.

    Attributes:
        id: Unique identifier.
        task_context: Description of the task.
        transformation_delta: The transformation applied.
        reasoning_steps: Intermediate reasoning steps.
        tools_used: Tools used in this reasoning.
        solution_schema: Schema of the solution.
        utility: Utility score (0-1).
        stability: Stability score (0-1).
    """

    id: str
    task_context: str
    transformation_delta: str
    reasoning_steps: list[str] = pydantic.Field(default_factory=list)
    tools_used: list[str] = pydantic.Field(default_factory=list)
    solution_schema: dict[str, Any] = pydantic.Field(default_factory=dict)
    utility: float = 0.5
    stability: float = 0.5


# =============================================================================
# Phase 3 types (Code Analysis)
# =============================================================================


class DataFlowIssue(pydantic.BaseModel):
    """A data flow issue detected in code.

    Attributes:
        severity: Severity level (error, warning, info).
        message: Description of the issue.
        variable: Variable name involved.
        line: Line number where issue occurs.
        issue_type: Type of issue (unused, uninitialized, shadowing).
    """

    severity: str
    message: str
    variable: str
    line: int
    issue_type: str


class EnrichedContext(pydantic.BaseModel):
    """Enriched context for a code entity (Phase 3).

    Attributes:
        node_id: Identifier of the code entity.
        name: Name of the entity.
        type: Type of entity (function, class, method).
        file_path: Path to the file.
        line_number: Line number in the file.
        context: Rich context information.
        data_flow: Data flow analysis results.
    """

    node_id: str
    name: str
    type: str
    file_path: str
    line_number: int
    context: dict[str, Any] = pydantic.Field(default_factory=dict)
    data_flow: dict[str, Any] = pydantic.Field(default_factory=dict)


# =============================================================================
# Content types
# =============================================================================


Content = str | dict[str, Any]


# =============================================================================
# Error types
# =============================================================================


class SharrowkinConnectionError(Exception):
    """Base class for connection errors in Sharrowkin Agent."""


class SharrowkinValidationError(Exception):
    """Validation error in Sharrowkin Agent.

    Attributes:
        message: Human-readable error description.
        errors: Structured error list.
    """

    def __init__(
        self,
        message: str,
        errors: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.errors = errors or []

    @classmethod
    def from_pydantic(
        cls, exc: pydantic.ValidationError
    ) -> "SharrowkinValidationError":
        """Constructs from a Pydantic ValidationError."""
        return cls(
            message=str(exc),
            errors=exc.errors() if hasattr(exc, "errors") else []
        )
