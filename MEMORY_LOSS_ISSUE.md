# 🔴 CRITICAL ISSUE: Agent Memory Loss in Frontend

**Date**: 2026-05-23 18:56 UTC  
**Issue**: Агент забывает что делал минуту назад при работе через frontend  
**Status**: ❌ **CONFIRMED - Root Cause Found**

---

## Problem Description

**User Report**: "Агент забывает то что сделал минуту назад, возможно она тонет в тонны промптов и забывает про задачу"

**Symptoms**:
- Agent forgets previous tasks
- No context between requests
- Each request starts fresh
- Memory systems not persisting

---

## Root Cause Analysis

### Issue 1: New Agent Instance Per Request ❌

**File**: `api/routers/agent.py:82`

```python
@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    # ...
    
    # ❌ PROBLEM: Creates NEW agent for EVERY request
    agent = SharrowkinAgent()
    _active_agents[session_id] = agent
    
    # Run agent
    async for event in agent.run(task, workspace_path=str(workspace)):
        await websocket.send_json(event)
```

**Why This Is Bad**:
1. **No conversation history** - `self.conversation_history: list[dict] = []` starts empty
2. **No memory persistence** - Memory systems initialized fresh
3. **No context accumulation** - Previous tasks forgotten
4. **No learning** - Each request is isolated

### Issue 2: Memory Not Saved After Task ❌

**File**: `agent/core.py` - Missing Phase 5 (Commit)

```python
async def run(self, task: str, workspace_path: str):
    # Phase 1: Observe ✅
    # Phase 2: Recall ✅
    # Phase 3: Reason ✅
    # Phase 4: Stabilize ✅
    # Phase 5: Commit ❌ MISSING!
    
    # Memory is NEVER saved to disk
    # DSM, RLD, TraceMemory - all lost after task
```

**Result**: Even if agent was reused, memory wouldn't persist

### Issue 3: Conversation History Not Passed to LLM ❌

**File**: `agent/core.py:_reason()` method

```python
async def _reason(self, state: AgentRunState, memory: MemoryBridge, iteration: int):
    # Build prompt
    prompt = f"""
Task: {state.task}
Workspace: {state.workspace_summary}
Memory: {state.memory_context}
"""
    
    # ❌ PROBLEM: self.conversation_history NOT included in prompt
    response = await self.gemini.generate(prompt)
```

**Why This Is Bad**:
- LLM doesn't see previous messages
- No multi-turn conversation
- Each request is isolated

---

## Evidence

### Test 1: Memory Systems Status
```
[INFO] Retrieving memory context (DSM + RLD + TraceMemory + MemoryField).
[SUCCESS] Memory loaded: 0 similar solutions, 0 reasoning patterns.
```

**Result**: Memory systems return 0 results (nothing saved)

### Test 2: Agent Initialization
```python
# api/routers/agent.py:82
agent = SharrowkinAgent()  # NEW instance

# agent/core.py:217
self.conversation_history: list[dict] = []  # EMPTY
```

**Result**: Fresh agent every time

### Test 3: WebSocket Flow
```
Request 1: "Create math_helper.py"
  → New agent created
  → Task completed
  → Agent deleted (line 121)
  → Memory lost

Request 2: "Create string_ops.py using same style"
  → New agent created (no memory from Request 1)
  → Doesn't know about math_helper.py
  → Starts fresh
```

---

## Impact

### Current Behavior ❌
```
User: "Create calculator.py"
Agent: [creates file] ✅

User: "Now create tests for calculator.py"
Agent: "What calculator.py?" ❌ (forgot previous task)

User: "Use the same style as before"
Agent: "What style?" ❌ (no memory)
```

### Expected Behavior ✅
```
User: "Create calculator.py"
Agent: [creates file] ✅
       [saves to memory]

User: "Now create tests for calculator.py"
Agent: "I remember creating calculator.py with functions add, subtract..." ✅
       [recalls from memory]

User: "Use the same style as before"
Agent: "Using the same docstring style with Args/Returns/Examples" ✅
       [recalls pattern from memory]
```

---

## Solution

### Fix 1: Persistent Agent Sessions (HIGH PRIORITY) ⭐

**File**: `api/routers/agent.py`

```python
# Global agent instances (persistent across requests)
_agent_sessions: dict[str, tuple[SharrowkinAgent, MemoryBridge]] = {}

@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    await websocket.accept()
    
    data = await websocket.receive_text()
    message = json.loads(data)
    
    session_id = message.get("session_id", f"session_{uuid.uuid4()}")
    task = message.get("task")
    workspace_path = message.get("workspace")
    
    # ✅ SOLUTION: Reuse existing agent or create new one
    if session_id in _agent_sessions:
        agent, memory = _agent_sessions[session_id]
        print(f"[WebSocket] Reusing agent for session {session_id}")
    else:
        agent = SharrowkinAgent()
        memory = MemoryBridge(workspace_path)
        _agent_sessions[session_id] = (agent, memory)
        print(f"[WebSocket] Created new agent for session {session_id}")
    
    # Run agent with persistent memory
    async for event in agent.run(task, workspace_path):
        await websocket.send_json(event)
    
    # DON'T delete agent - keep for next request
    # Agent will be cleaned up on explicit /clear or timeout
```

**Benefits**:
- ✅ Agent persists across requests
- ✅ Conversation history maintained
- ✅ Memory accumulates
- ✅ Context preserved

### Fix 2: Add Memory Commit Phase (HIGH PRIORITY) ⭐

**File**: `agent/core.py`

```python
async def _commit(self, state: AgentRunState, memory: MemoryBridge):
    """Phase 5: Commit - Save to memory systems."""
    
    yield self._phase("Commit", "running")
    
    # 1. Save to TraceMemory
    if state.changes_made:
        trace = {
            "task": state.task,
            "files_changed": state.current_changed_files,
            "success": True,
            "timestamp": time.time()
        }
        memory.trace_memory.store(trace)
    
    # 2. Save to DSM
    for file in state.current_changed_files:
        memory.dsm.write(
            content=f"Modified {file} for task: {state.task[:100]}",
            category=["code", "recent_changes"],
            importance=0.8
        )
    
    # 3. Extract RLD genes (reasoning patterns)
    if state.success:
        gene = {
            "pattern": "file_creation",
            "context": state.task,
            "success_rate": 1.0
        }
        memory.rld.add_gene(gene)
    
    # 4. Update MemoryField (strategy attractors)
    memory.field.reinforce("code_generation", success=True)
    
    yield self._phase("Commit", "done")
    yield self._log("success", f"Saved to memory: {len(state.current_changed_files)} files")

# Add to main run() loop
async def run(self, task: str, workspace_path: str):
    # ... existing phases ...
    
    # Phase 5: Commit
    async for event in self._commit(state, memory):
        yield event
```

**Benefits**:
- ✅ Memory persists to disk
- ✅ Future tasks can recall
- ✅ Patterns extracted
- ✅ Learning accumulates

### Fix 3: Include Conversation History in LLM Prompt (MEDIUM PRIORITY)

**File**: `agent/core.py:_reason()`

```python
async def _reason(self, state: AgentRunState, memory: MemoryBridge, iteration: int):
    # Build conversation context
    conversation_context = ""
    if self.conversation_history:
        conversation_context = "\n\n=== PREVIOUS CONVERSATION ===\n"
        # Last 3 messages for context
        for msg in self.conversation_history[-3:]:
            conversation_context += f"{msg['role']}: {msg['content'][:200]}...\n"
    
    # Build full prompt
    prompt = f"""
{conversation_context}

=== CURRENT TASK ===
Task: {state.task}

=== WORKSPACE ===
{state.workspace_summary}

=== MEMORY ===
{state.memory_context}

Generate code to complete the task.
"""
    
    response = await self.gemini.generate(prompt)
    
    # Save to conversation history
    self.conversation_history.append({
        "role": "user",
        "content": state.task
    })
    self.conversation_history.append({
        "role": "assistant",
        "content": response
    })
```

**Benefits**:
- ✅ LLM sees previous context
- ✅ Multi-turn conversations work
- ✅ Better understanding

### Fix 4: Add Session Management Endpoints (LOW PRIORITY)

**File**: `api/routers/agent.py`

```python
@router.post("/session/clear")
async def clear_session(session_id: str):
    """Clear agent session and memory."""
    if session_id in _agent_sessions:
        del _agent_sessions[session_id]
        return {"success": True, "message": "Session cleared"}
    raise HTTPException(404, "Session not found")

@router.get("/session/info")
async def get_session_info(session_id: str):
    """Get session information."""
    if session_id not in _agent_sessions:
        raise HTTPException(404, "Session not found")
    
    agent, memory = _agent_sessions[session_id]
    return {
        "session_id": session_id,
        "conversation_length": len(agent.conversation_history),
        "memory_segments": len(memory.dsm.segments) if memory.dsm else 0,
        "rld_genes": len(memory.rld.genes) if memory.rld else 0
    }
```

---

## Implementation Priority

### Phase 1: Critical Fixes (2-3 hours) ⭐⭐⭐
1. **Persistent Agent Sessions** (1h)
   - Modify `api/routers/agent.py`
   - Add session management
   - Test multi-request flow

2. **Memory Commit Phase** (1-2h)
   - Add `_commit()` method
   - Save to DSM, RLD, TraceMemory
   - Test memory persistence

**Impact**: Fixes 90% of memory loss issue

### Phase 2: Enhancements (1-2 hours) ⭐⭐
3. **Conversation History in LLM** (1h)
   - Include previous messages in prompt
   - Test multi-turn conversations

4. **Session Management API** (1h)
   - Add clear/info endpoints
   - Add session timeout

**Impact**: Improves context awareness

---

## Testing Plan

### Test 1: Multi-Request Memory
```
Request 1: "Create calculator.py with add and subtract"
Expected: File created ✅

Request 2: "Now add multiply and divide to calculator.py"
Expected: Agent remembers calculator.py, adds functions ✅

Request 3: "Create tests for calculator.py"
Expected: Agent remembers all functions, creates tests ✅
```

### Test 2: Style Consistency
```
Request 1: "Create math_helper.py with docstrings"
Expected: File created with style ✅

Request 2: "Create string_ops.py using same style"
Expected: Agent recalls style, matches it ✅
```

### Test 3: Session Persistence
```
Request 1: "Create file1.py"
Close browser

Request 2 (same session_id): "Create file2.py"
Expected: Agent remembers file1.py ✅
```

---

## Conclusion

### Root Cause ❌
1. **New agent per request** - No persistence
2. **No memory commit** - Nothing saved
3. **No conversation history** - No context

### Solution ✅
1. **Persistent sessions** - Reuse agent
2. **Memory commit phase** - Save to disk
3. **Conversation history** - Include in prompts

### Impact
- **Before**: Agent forgets everything after each request
- **After**: Agent remembers all previous tasks and context

### Priority
**CRITICAL** - Implement Phase 1 fixes (2-3 hours) immediately

---

**Report Created**: 2026-05-23 18:56 UTC  
**Issue Severity**: CRITICAL  
**Estimated Fix Time**: 2-3 hours (Phase 1)  
**Status**: ❌ **BROKEN** → ✅ **FIXABLE**
