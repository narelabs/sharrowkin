"""Gemini REST client for Sharrowkin."""

from __future__ import annotations

import json
import os
import asyncio
import re
from dataclasses import dataclass

import httpx
from aiolimiter import AsyncLimiter  # ✅ NEW: Rate limiting


# Manually load .env variables if present
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()


@dataclass(slots=True)
class GeneratedPatch:
    rationale: str
    subtasks: list[str]
    files: dict[str, str]
    commands: list[str]


@dataclass(slots=True)
class ToolCallRequest:
    """A single tool invocation requested by the model.

    ``id`` correlates the call with its result on the next turn (Anthropic
    ``tool_use_id`` / OpenAI ``tool_call_id``).
    """
    id: str
    name: str
    args: dict


@dataclass(slots=True)
class ChatTurn:
    """One assistant turn in a tool-calling loop.

    ``raw_assistant_content`` holds the provider-native assistant message
    content (Anthropic content blocks list, or an OpenAI message dict) so the
    caller can append it verbatim to the running ``messages`` before sending
    the tool results back — this is what keeps the multi-turn tool protocol
    valid.
    """
    text: str
    tool_calls: list[ToolCallRequest]
    raw_assistant_content: object
    stop_reason: str
    api_format: str  # "anthropic" | "openai"


AUTONOMOUS_AGENT_POLICY = """
You are Sharrowkin, an autonomous developer agent with full access to the local workspace.

Operate with high agency:
- Do not ask the user follow-up questions unless the task is impossible, destructive, or requires external credentials.
- Infer safe defaults from the workspace, existing conventions, and conversation context.
- For ambiguous implementation details, choose the smallest reversible path and state the assumption in the rationale.
- Read/inspect relevant files before changing them; preserve public APIs and existing style.
- After edits, run the cheapest relevant validation commands available (tests, linters, type checkers).
- If validation fails, diagnose the concrete failure and choose a different fix path instead of repeating the same patch.
- Never include secrets or credentials in code or patches.

You have access to:
- Local filesystem: read, write, edit files in the workspace
- Terminal commands: run tests, linters, build tools, git commands
- AST analysis: understand code structure and dependencies
- Memory systems: DSM, RLD, TraceMemory for context and learning

Workflow:
1. Analyze the task and recall relevant memory context
2. Read necessary files to understand current state
3. Plan changes with minimal scope
4. Apply changes to files
5. Validate with tests/linters if available
6. Learn from the outcome (success or failure)
""".strip()


def _autonomous_json_system_prompt() -> str:
    return (
        f"{AUTONOMOUS_AGENT_POLICY}\n\n"
        "# Operating Mode\n\n"
        "You are an autonomous coding agent running in headless mode.\n"
        "No human is available to respond. Do not ask questions or request confirmation.\n"
        "If the task is ambiguous, make the best judgment call and proceed.\n"
        "Complete the entire task in a single pass.\n\n"
        "# Output Format\n\n"
        "You MUST respond with a single JSON object. Nothing else.\n"
        "Do NOT output markdown, explanations, or code outside the JSON.\n\n"
        "```\n"
        "{\n"
        '  "rationale": "Your reasoning and explanation of what you did",\n'
        '  "subtasks": ["step 1", "step 2"],\n'
        '  "commands": ["npm test", "python -m pytest"],\n'
        '  "files": {\n'
        '    "relative/path/file.ext": "COMPLETE file content"\n'
        "  }\n"
        "}\n"
        "```\n\n"
        "# Rules\n\n"
        "- For code tasks: put COMPLETE file contents in `files`. Use actual file contents from context as base.\n"
        "- For analysis/questions: put answer in `rationale`, leave `files` as `{}`.\n"
        "- `commands`: terminal commands to validate (tests, build). Empty `[]` if none needed.\n"
        "- All file paths relative to workspace root.\n"
        "- All file contents COMPLETE (not snippets).\n"
        "- If you cannot complete the task, return JSON with rationale explaining why.\n"
        "- NEVER return plain text, markdown, or code outside the JSON object.\n"
    )


def _to_anthropic_tool(tool: dict) -> dict:
    """Normalize a tool spec to Anthropic's flat shape.

    Accepts either the canonical ``{name, description, input_schema}`` form or
    the OpenAI ``{type: function, function: {...}}`` wrapper.
    """
    if "function" in tool:
        fn = tool["function"]
        return {
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        }
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "input_schema": tool.get("input_schema", tool.get("parameters", {"type": "object", "properties": {}})),
    }


def _to_openai_tool(tool: dict) -> dict:
    """Normalize a tool spec to OpenAI's ``{type: function, function: {...}}``."""
    if "function" in tool:
        return tool
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


async def _get_response_text(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        chunks = []
        async for line in response.aiter_lines():
            if line:
                line_str = line.strip()
                if line_str.startswith("data:"):
                    data_content = line_str[5:].strip()
                    if data_content == "[DONE]":
                        continue
                    try:
                        data_json = json.loads(data_content)
                        # OpenAI format
                        if "choices" in data_json and len(data_json["choices"]) > 0:
                            delta = data_json["choices"][0].get("delta", {})
                            if "content" in delta:
                                chunks.append(delta["content"])
                        # Anthropic format
                        elif "type" in data_json:
                            t = data_json["type"]
                            if t == "content_block_delta":
                                delta = data_json.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    chunks.append(delta.get("text", ""))
                            elif t == "completion":
                                chunks.append(data_json.get("completion", ""))
                    except Exception:
                        pass
        return "".join(chunks)
    else:
        # Standard JSON parsing
        try:
            data = response.json()
        except Exception:
            body_text = response.text or ""
            if "event: " in body_text or "data: " in body_text:
                chunks = []
                for line in body_text.splitlines():
                    line = line.strip()
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            continue
                        try:
                            chunk_data = json.loads(data_str)
                            if isinstance(chunk_data, dict):
                                if "delta" in chunk_data and isinstance(chunk_data["delta"], dict) and "text" in chunk_data["delta"]:
                                    chunks.append(chunk_data["delta"]["text"])
                                elif "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                    choice = chunk_data["choices"][0]
                                    if "delta" in choice and isinstance(choice["delta"], dict) and "content" in choice["delta"]:
                                        chunks.append(choice["delta"]["content"])
                        except Exception:
                            pass
                if chunks:
                    return "".join(chunks)
            return body_text

        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            err_msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Proxy returned an error: {err_msg}")
        
        if isinstance(data, dict) and "content" in data and len(data["content"]) > 0:
            # Anthropic format: check for tool_use blocks first
            for block in data["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    # Tool call response — return the input (arguments) as JSON string
                    tool_input = block.get("input", {})
                    return json.dumps(tool_input, ensure_ascii=False)
            # Fallback to text block
            for block in data["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
            return data["content"][0].get("text", "") if isinstance(data["content"][0], dict) else str(data["content"][0])
        elif isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
            message = data["choices"][0].get("message", {})
            # OpenAI format: check for tool_calls first
            tool_calls = message.get("tool_calls")
            if tool_calls and len(tool_calls) > 0:
                # Extract arguments from the first tool call
                args_str = tool_calls[0].get("function", {}).get("arguments", "{}")
                return args_str
            return message.get("content", "")
        elif isinstance(data, dict) and "candidates" in data and len(data["candidates"]) > 0:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return ""


class GeminiConfigurationError(RuntimeError):
    pass


async def retry_with_backoff(func, max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """Retry async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry

    Returns:
        Result of the function call

    Raises:
        Last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await func()
        except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_exception = e
            if attempt < max_retries - 1:
                print(f"[LLM Retry] Attempt {attempt + 1}/{max_retries} failed with timeout, retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                print(f"[LLM Retry] All {max_retries} attempts failed")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            # 429 (rate limit) and 408 (request timeout) are transient — retry
            # them with backoff, honoring a Retry-After header when present.
            # Other 4xx are genuine client errors; failing fast is correct.
            if 400 <= status < 500 and status not in (408, 429):
                raise
            last_exception = e
            if attempt < max_retries - 1:
                wait = delay
                if status == 429:
                    retry_after = e.response.headers.get("retry-after")
                    if retry_after:
                        try:
                            wait = max(delay, float(retry_after))
                        except ValueError:
                            pass
                print(f"[LLM Retry] Attempt {attempt + 1}/{max_retries} failed with status {status}, retrying in {wait}s...")
                await asyncio.sleep(wait)
                delay *= backoff_factor
            else:
                print(f"[LLM Retry] All {max_retries} attempts failed")
        except Exception as e:
            # Don't retry on unknown errors
            raise

    raise last_exception


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model

        # Omniroute proxy support (Anthropic-compatible endpoint)
        self.omniroute_base_url = os.getenv("ANTHROPIC_BASE_URL")
        self.omniroute_token = (
            os.getenv("ANTHROPIC_AUTH_TOKEN")
            or os.getenv("ANTHROPIC_API_KEY")
            or ""
        )
        self.omniroute_model = os.getenv("ANTHROPIC_MODEL") or "kr/claude-sonnet-4.5"

        # ✅ NEW: Connection pooling for better performance
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

        # ✅ NEW: Rate limiting (10 requests per minute to avoid API bans)
        self._rate_limiter = AsyncLimiter(max_rate=10, time_period=60)

    async def __aenter__(self):
        """Context manager support."""
        return self

    async def __aexit__(self, *args):
        """Close client on exit."""
        await self._client.aclose()

    async def close(self):
        """Explicitly close the client."""
        await self._client.aclose()

    @property
    def configured(self) -> bool:
        return bool(self.api_key) or bool(self.omniroute_base_url)

    async def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        if not self.api_key and not self.omniroute_base_url:
            raise GeminiConfigurationError(
                "Neither GEMINI_API_KEY nor ANTHROPIC_BASE_URL is set."
            )

        # Apply rate limiting to the actual HTTP call, not just the config check
        async with self._rate_limiter:
            if self.omniroute_base_url:
                base_url = self.omniroute_base_url.rstrip("/")
                system = system_instruction or "You are Sharrowkin, a local autonomous developer agent."

                # Detect API type by base URL
                is_openai_compatible = "ecomagent" in base_url or "openai" in base_url or "localhost" in base_url

                max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))

                if is_openai_compatible:
                    # Use OpenAI format directly for EcoMagent and similar APIs
                    url = f"{base_url}/chat/completions"
                    headers = {
                        "Content-Type": "application/json",
                    }
                    # Only add Authorization header if token is not empty
                    if self.omniroute_token:
                        headers["Authorization"] = f"Bearer {self.omniroute_token}"
                    payload = {
                        "model": self.omniroute_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": max_tokens,
                        "stream": False,
                    }
                else:
                    # Use Anthropic format for Omniroute proxy
                    url = f"{base_url}/messages"
                    headers = {
                        "x-api-key": self.omniroute_token,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    }
                    payload = {
                        "model": self.omniroute_model,
                        "max_tokens": max_tokens,
                        "system": system,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "stream": False,
                    }

                # ✅ NEW: Wrap HTTP calls with retry logic
                async def _make_request():
                    response = await self._client.post(url, headers=headers, json=payload)

                    # If Anthropic format fails with 404, try OpenAI fallback
                    if response.status_code == 404 and not is_openai_compatible:
                        openai_url = f"{base_url}/chat/completions"
                        openai_headers = {
                            "Content-Type": "application/json",
                        }
                        if self.omniroute_token:
                            openai_headers["Authorization"] = f"Bearer {self.omniroute_token}"
                        openai_payload = {
                            "model": self.omniroute_model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.2,
                            "max_tokens": max_tokens,
                            "stream": False,
                        }
                        openai_response = await self._client.post(openai_url, headers=openai_headers, json=openai_payload)
                        openai_response.raise_for_status()
                        return await _get_response_text(openai_response)

                    response.raise_for_status()
                    return await _get_response_text(response)

                try:
                    return await retry_with_backoff(_make_request, max_retries=3, initial_delay=1.0, backoff_factor=2.0)
                except Exception as e:
                    raise RuntimeError(f"Omniroute call failed after retries: {e}")
            else:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{self.model}:generateContent?key={self.api_key}"
                )
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2},
                }
                if system_instruction:
                    payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

                # ✅ NEW: Wrap Gemini API calls with retry logic
                async def _make_gemini_request():
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        response = await client.post(url, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]

                try:
                    return await retry_with_backoff(_make_gemini_request, max_retries=3, initial_delay=1.0, backoff_factor=2.0)
                except Exception as e:
                    raise RuntimeError(f"Gemini call failed after retries: {e}")

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> ChatTurn:
        """One round of a tool-calling conversation.

        Unlike ``generate_patch`` (one-shot JSON), this returns the model's
        tool calls so the caller can execute them and feed real results back
        on the next round. This is the primitive the ReAct ``ToolLoop`` is
        built on.

        ``messages`` is the running conversation in the provider's native
        shape (Anthropic content-block messages, or OpenAI messages). The
        caller owns the history; this method only performs a single request
        and parses the response.

        Returns a :class:`ChatTurn`. On transport failure the error propagates
        (the loop decides how to recover) — we do not silently swallow it into
        an empty turn the way ``generate_patch`` does.
        """
        if not self.api_key and not self.omniroute_base_url:
            raise GeminiConfigurationError(
                "Neither GEMINI_API_KEY nor ANTHROPIC_BASE_URL is set."
            )
        if not self.omniroute_base_url:
            raise GeminiConfigurationError(
                "chat_with_tools requires an Anthropic/OpenAI-compatible proxy "
                "(ANTHROPIC_BASE_URL). The native Gemini endpoint is not wired "
                "for the tool-loop."
            )

        tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", "8192"))
        base_url = self.omniroute_base_url.rstrip("/")
        is_openai_compatible = (
            "ecomagent" in base_url or "openai" in base_url or "localhost" in base_url
        )

        async with self._rate_limiter:
            if is_openai_compatible:
                turn = await self._chat_with_tools_openai(
                    base_url, messages, tools, system, tokens, temperature
                )
            else:
                turn = await self._chat_with_tools_anthropic(
                    base_url, messages, tools, system, tokens, temperature
                )
        return turn

    async def _chat_with_tools_anthropic(
        self, base_url, messages, tools, system, tokens, temperature
    ) -> ChatTurn:
        url = f"{base_url}/messages"
        headers = {
            "x-api-key": self.omniroute_token,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Anthropic tool schema: flat {name, description, input_schema}.
        anthropic_tools = [_to_anthropic_tool(t) for t in tools]
        payload = {
            "model": self.omniroute_model,
            "max_tokens": tokens,
            "system": system,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "tools": anthropic_tools,
        }

        async def _request():
            resp = await self._client.post(url, headers=headers, json=payload)
            if resp.status_code == 402:
                raise GeminiConfigurationError(
                    f"Omniroute proxy returned 402 (Payment Required). {resp.text[:200]}"
                )
            resp.raise_for_status()
            return resp.json()

        data = await retry_with_backoff(_request, max_retries=3, initial_delay=2.0, backoff_factor=2.0)

        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Proxy returned an error: {msg}")

        content_blocks = data.get("content", []) if isinstance(data, dict) else []
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        args=block.get("input", {}) or {},
                    )
                )

        return ChatTurn(
            text="".join(text_parts).strip(),
            tool_calls=tool_calls,
            raw_assistant_content=content_blocks,
            stop_reason=data.get("stop_reason", "") if isinstance(data, dict) else "",
            api_format="anthropic",
        )

    async def _chat_with_tools_openai(
        self, base_url, messages, tools, system, tokens, temperature
    ) -> ChatTurn:
        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.omniroute_token:
            headers["Authorization"] = f"Bearer {self.omniroute_token}"
        # OpenAI wants the system prompt as the first message, and tools wrapped
        # in {"type": "function", "function": {...}}.
        oai_messages = [{"role": "system", "content": system}] + messages
        oai_tools = [_to_openai_tool(t) for t in tools]
        payload = {
            "model": self.omniroute_model,
            "max_tokens": tokens,
            "messages": oai_messages,
            "temperature": temperature,
            "stream": False,
            "tools": oai_tools,
        }

        async def _request():
            resp = await self._client.post(url, headers=headers, json=payload)
            if resp.status_code == 402:
                raise GeminiConfigurationError(
                    f"Omniroute proxy returned 402 (Payment Required). {resp.text[:200]}"
                )
            resp.raise_for_status()
            return resp.json()

        data = await retry_with_backoff(_request, max_retries=3, initial_delay=2.0, backoff_factor=2.0)

        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"Proxy returned an error: {msg}")

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        text = message.get("content") or ""
        tool_calls: list[ToolCallRequest] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCallRequest(id=tc.get("id", ""), name=fn.get("name", ""), args=args)
            )

        return ChatTurn(
            text=(text or "").strip(),
            tool_calls=tool_calls,
            raw_assistant_content=message,
            stop_reason=choice.get("finish_reason", "") if isinstance(choice, dict) else "",
            api_format="openai",
        )

    async def classify_intent(self, task: str) -> dict[str, object]:
        # Fast heuristic: catch obvious greetings/conversational queries without LLM
        normalized = task.strip().lower()
        # Remove punctuation for matching
        clean = re.sub(r'[^\w\s]', '', normalized)
        
        greeting_patterns = {
            "привет", "здравствуй", "здравствуйте", "хай", "хей", "салам",
            "hello", "hi", "hey", "yo", "sup",
            "как дела", "как ты", "что нового", "как поживаешь",
            "кто ты", "что ты", "что ты умеешь", "что ты можешь",
            "who are you", "what are you", "how are you",
            "thanks", "thank you", "спасибо", "пока", "bye",
            "доброе утро", "добрый день", "добрый вечер", "good morning",
            "ку", "qq", "q", "прив", "даров", "здорова",
        }
        
        # Extended conversational patterns (questions about the agent, not coding tasks)
        conversational_phrases = {
            "ты тут", "ты здесь", "ты на месте", "ты живой", "ты работаешь",
            "ты онлайн", "ты готов", "ты слышишь", "алло",
            "are you there", "are you online", "are you ready",
            "что умеешь", "что можешь", "что ты делаешь", "чем занят",
            "расскажи о себе", "помоги", "помогите", "help",
            "изучил проект", "ты понял", "ты разобрался", "готов работать",
            "давай работать", "начнем", "поехали", "lets go",
            "да", "нет", "ок", "окей", "ладно", "хорошо", "понял",
            "yes", "no", "ok", "okay", "sure", "yep", "nope",
        }
        
        # Check if the entire message (cleaned) matches a greeting pattern
        if clean in greeting_patterns or clean in conversational_phrases:
            print(f"[INTENT] Heuristic match: '{task}' -> conversational")
            return {"is_conversational": True, "is_informational": False, "response": None}
        
        # Check if the message starts with a greeting/conversational phrase and is short
        words = clean.split()
        all_patterns = greeting_patterns | conversational_phrases
        if len(words) <= 8 and any(clean.startswith(g) for g in all_patterns):
            print(f"[INTENT] Heuristic prefix match: '{task}' -> conversational")
            return {"is_conversational": True, "is_informational": False, "response": None}

        # Retrospective / meta questions about what the agent already did.
        # These must be answered from conversation history, NOT by launching a
        # full repo scan (the old behaviour: "а что ты сделал" → informational
        # cycle over 160 files). Routed to conversational so the LLM replies
        # using _format_history context.
        retrospective_phrases = {
            "что ты сделал", "что сделал", "что ты делал", "что было сделано",
            "что ты изменил", "что изменил", "что поменял", "что ты поменял",
            "что ты натворил", "что нового сделал", "какие изменения",
            "что ты только что сделал", "что ты сейчас сделал", "че сделал",
            "чо сделал", "что там сделал", "покажи что сделал",
            "what did you do", "what have you done", "what did you change",
            "what changed", "what was changed", "what did you just do",
            "summarize what you did", "recap", "what was done",
        }
        if any(p in clean for p in retrospective_phrases):
            print(f"[INTENT] Retrospective question: '{task}' -> conversational")
            return {"is_conversational": True, "is_informational": False, "response": None}
        
        # Informational/read-only request heuristics (requests to explain, analyze, or study the project)
        info_keywords = {
            "изучи", "изучай", "просканируй", "проанализируй", "что за проект", "объясни",
            "как устроена", "как устроено", "структура", "опиши", "описание", "расскажи про",
            "explain", "analyze", "describe", "what is this project", "study", "show me", "структуру"
        }
        mutate_keywords = {
            "создай", "напиши", "исправь", "добавь", "добавлю", "удали", "измени",
            "сделай", "запусти", "установи", "обнови", "рефактор", "улучши", "улучшу",
            "create", "write", "fix", "add", "delete", "remove", "change",
            "make", "run", "install", "update", "refactor", "build", "test",
            "deploy", "debug", "implement"
        }
        
        has_info = any(k in clean for k in info_keywords)
        has_mutate = any(k in clean for k in mutate_keywords)
        if has_info and not has_mutate:
            print(f"[INTENT] Heuristic match: '{task}' -> informational")
            return {"is_conversational": False, "is_informational": True, "response": None}
        
        # Short messages (<=3 words) without code-related keywords are likely conversational
        code_keywords = {
            "создай", "напиши", "исправь", "добавь", "добавлю", "удали", "измени",
            "сделай", "запусти", "установи", "обнови", "рефактор", "улучши", "улучшу",
            "изучи", "изучай", "просканируй", "проанализируй", "проект", "репозиторий",
            "проверь", "статус", "покажи", "список", "найди", "поиск",
            "create", "write", "fix", "add", "delete", "remove", "change",
            "make", "run", "install", "update", "refactor", "build", "test",
            "deploy", "debug", "implement", "file", "code", "function",
            "analyze", "scan", "study", "check", "status", "show", "list", "find", "search",
            "файл", "код", "функцию", "класс", "модуль", "компонент",
        }
        if len(words) <= 3 and not any(w in code_keywords for w in words):
            print(f"[INTENT] Short non-code message: '{task}' -> conversational")
            return {"is_conversational": True, "is_informational": False, "response": None}
        
        # If LLM is not configured, use heuristic-only fallback
        if not self.configured:
            print(f"[INTENT] LLM not configured, defaulting to coding task: '{task}'")
            return {"is_conversational": False, "is_informational": False, "response": None}
        
        # For ambiguous queries, use LLM classification
        system_instruction = (
            "You are Sharrowkin, an expert AI developer agent. Classify the user query.\n"
            "Return a JSON object with three keys:\n"
            " - 'is_conversational': true if this is a greeting, small talk, or general question NOT about code/files.\n"
            " - 'is_informational': true if this is a request to analyze, study, explain, describe, or find info in the workspace/code, without making any modifications/running tests/creating/deleting/changing code or files.\n"
            " - 'response': if is_conversational is true, write a helpful response in the user's language. Otherwise null.\n"
            "Return ONLY the raw JSON object, no markdown."
        )
        
        prompt = f"User query: {task}"
        
        try:
            raw_response = await self.generate_text(prompt, system_instruction)
            text = raw_response.strip()
            print(f"[INTENT] LLM raw response: {text[:200]}")
            
            # Clean markdown if returned
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if code_block_match:
                text = code_block_match.group(1).strip()
            
            # Parse outer braces
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx:end_idx+1].strip()
                
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                is_conv = parsed.get("is_conversational", False)
                is_info = parsed.get("is_informational", False)
                resp = parsed.get("response", None)
                print(f"[INTENT] LLM classified: is_conversational={is_conv}, is_informational={is_info}")
                return {"is_conversational": is_conv, "is_informational": is_info, "response": resp}
        except Exception as exc:
            print(f"[INTENT] LLM classification failed: {exc}")
            
        return {"is_conversational": False, "is_informational": False, "response": None}

    async def generate_patch(
        self,
        *,
        task: str,
        workspace_summary: str,
        memory_context: str,
        previous_error: str = "",
        action_history: list[str] = None,
        file_contents: dict[str, str] = None,
        conversation_history: list[dict] = None,
        conversation_context: str = None,  # ✅ NEW: Formatted conversation context
    ) -> GeneratedPatch:
        if not self.api_key and not self.omniroute_base_url:
            raise GeminiConfigurationError(
                "Neither GEMINI_API_KEY nor ANTHROPIC_BASE_URL is set. "
                "Add one of them to the environment to enable code generation."
            )

        prompt = self._build_prompt(
            task,
            workspace_summary,
            memory_context,
            previous_error,
            action_history,
            file_contents,
            conversation_context  # ✅ NEW: Pass conversation context
        )
        
        # If Omniroute proxy is configured, route via Anthropic Messages API
        if self.omniroute_base_url:
            base_url = self.omniroute_base_url.rstrip("/")
            url = f"{base_url}/messages"
            headers = {
                "x-api-key": self.omniroute_token,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            system_prompt = _autonomous_json_system_prompt()

            # Build messages with conversation history
            messages = []

            # ✅ FIX: Only add system prompt if conversation_history is empty or doesn't start with system
            # This prevents sending the huge system prompt on every request
            if conversation_history:
                # Check if first message is already system prompt
                if conversation_history[0].get("role") != "system":
                    # Add system as first message only once
                    messages.append({"role": "system", "content": system_prompt})
                # Add conversation history (last 10 messages to avoid context overflow)
                messages.extend(conversation_history[-10:])
            else:
                # First request - add system prompt
                messages.append({"role": "system", "content": system_prompt})

            # Add current task as the latest user message
            messages.append({"role": "user", "content": prompt})

            # ═══════════════════════════════════════════════════════════════
            # Use tool_use (function calling) for structured output.
            # This is the mistral-vibe approach: instead of asking LLM to
            # return JSON in text (which it often ignores), we define a tool
            # and let the API enforce structured output.
            # ═══════════════════════════════════════════════════════════════
            tools_definition = [
                {
                    "type": "function",
                    "function": {
                        "name": "submit_patch",
                        "description": "Submit the code changes, analysis, and commands as a structured patch. Always call this tool with your results.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "rationale": {
                                    "type": "string",
                                    "description": "Your reasoning, analysis, or explanation of what you did"
                                },
                                "subtasks": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Decomposed steps (can be empty)"
                                },
                                "commands": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Terminal commands to run for validation (can be empty)"
                                },
                                "files": {
                                    "type": "object",
                                    "additionalProperties": {"type": "string"},
                                    "description": "Map of relative file paths to their COMPLETE new content. Empty object {} if no code changes."
                                }
                            },
                            "required": ["rationale", "subtasks", "commands", "files"]
                        }
                    }
                }
            ]

            payload = {
                "model": self.omniroute_model,
                "max_tokens": 8192,
                "messages": messages,
                "temperature": 0.2,
                "stream": False,
                "tools": tools_definition,
            }

            # ✅ NEW: Wrap with retry logic
            async def _make_patch_request():
                response = await self._client.post(url, headers=headers, json=payload)

                # Check for 402 Specifically
                if response.status_code == 402:
                    raise GeminiConfigurationError(
                        "Omniroute proxy returned 402 (Payment Required). "
                        "Please check your API key, billing status, or funds/credits on your Omniroute console. "
                        f"Response details: {response.text[:200]}"
                    )

                # Fallback check if the proxy returned 404 on /messages (e.g. OpenAI compatibility)
                if response.status_code == 404:
                    # Try OpenAI-compatible chat completion endpoint as fallback
                    openai_url = f"{base_url}/chat/completions"
                    openai_headers = {
                        "Content-Type": "application/json",
                    }
                    if self.omniroute_token:
                        openai_headers["Authorization"] = f"Bearer {self.omniroute_token}"
                    openai_payload = {
                        "model": self.omniroute_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "stream": False,
                    }
                    openai_response = await self._client.post(openai_url, headers=openai_headers, json=openai_payload)
                    if openai_response.status_code == 402:
                        raise GeminiConfigurationError(
                            "Omniroute proxy returned 402 (Payment Required) on fallback. "
                            "Please check your API key, billing status, or funds/credits on your Omniroute console. "
                            f"Response details: {openai_response.text[:200]}"
                        )
                    openai_response.raise_for_status()
                    return await _get_response_text(openai_response)

                response.raise_for_status()
                return await _get_response_text(response)

            try:
                text = await retry_with_backoff(_make_patch_request, max_retries=3, initial_delay=2.0, backoff_factor=2.0)
                return parse_generated_patch(text)
            except GeminiConfigurationError:
                raise
            except Exception as e:
                # Instead of crashing, return a fallback patch so the agent can continue
                print(f"[WARN] Omniroute patch generation failed: {e}")
                return GeneratedPatch(
                    rationale=f"[LLM error: {e}]",
                    subtasks=[],
                    files={},
                    commands=[],
                )
        else:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self.api_key}"
            )
            payload = {
                "systemInstruction": {
                    "parts": [
                        {
                            "text": _autonomous_json_system_prompt()
                        }
                    ]
                },
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            }

            # ✅ NEW: Wrap with retry logic
            async def _make_gemini_patch_request():
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text

            try:
                text = await retry_with_backoff(_make_gemini_patch_request, max_retries=3, initial_delay=2.0, backoff_factor=2.0)
                return parse_generated_patch(text)
            except Exception as e:
                # Instead of crashing, return a fallback patch so the agent can continue
                print(f"[WARN] Gemini patch generation failed: {e}")
                return GeneratedPatch(
                    rationale=f"[LLM error: {e}]",
                    subtasks=[],
                    files={},
                    commands=[],
                )

    def _build_prompt(
        self,
        task: str,
        workspace_summary: str,
        memory_context: str,
        previous_error: str,
        action_history: list[str] = None,
        file_contents: dict[str, str] = None,
        conversation_context: str = None,  # Deprecated - kept for compatibility but not used
    ) -> str:
        sections = [
            "AUTONOMOUS OPERATING POLICY",
            AUTONOMOUS_AGENT_POLICY,
        ]

        # ✅ REMOVED: Don't add conversation_context to prompt - it's already in conversation_history
        # This was causing duplication and bloating the context

        sections.extend([
            "TASK",
            task,
            "WORKSPACE AST SUMMARY",
            workspace_summary,
            "RLD AND DSM MEMORY CONTEXT",
            memory_context,
        ])
        if file_contents:
            file_sections = []
            for path, content in file_contents.items():
                # Truncate very large files
                if len(content) > 8000:
                    content = content[:8000] + "\n... [truncated]"
                file_sections.append(f"--- FILE: {path} ---\n{content}")
            sections.extend(["CURRENT FILE CONTENTS (read before editing)", "\n\n".join(file_sections)])
        if action_history:
            formatted_actions = "\n".join(f"- {a}" for a in action_history)
            sections.extend(["PREVIOUS ACTIONS (DO NOT REPEAT FAILED ACTIONS)", formatted_actions])
        if previous_error:
            sections.extend(["PREVIOUS PYTEST OUTPUT OR PATCH ERROR", previous_error])
        sections.append(
            "Generate the smallest safe patch. Return complete replacement text only for files you change. "
            "You MUST use the actual file contents provided above as the base for your edits. "
            "You can specify shell commands in 'commands' if you need to inspect, install packages, run scripts, or compile things. "
            "Prefer autonomous progress over asking questions: make a safe assumption, implement, and validate."
        )
        return "\n\n".join(sections)


def repair_truncated_json(s: str) -> str:
    """Attempts to repair a truncated JSON string by closing opened brackets and braces."""
    s = s.strip()
    if not s:
        return "{}"
    
    try:
        json.loads(s)
        return s
    except json.JSONDecodeError:
        pass

    # Basic repair algorithm for truncated JSON
    in_string = False
    escape = False
    stack = []
    repaired_chars = []
    
    for char in s:
        if escape:
            escape = False
            repaired_chars.append(char)
            continue
            
        if char == '\\':
            escape = True
            repaired_chars.append(char)
            continue
            
        if char == '"':
            in_string = not in_string
            repaired_chars.append(char)
            continue
            
        if not in_string:
            if char in '{[':
                stack.append(char)
            elif char in '}]':
                if stack:
                    top = stack[-1]
                    if (char == '}' and top == '{') or (char == ']' and top == '['):
                        stack.pop()
        
        repaired_chars.append(char)
        
    if in_string:
        if repaired_chars and repaired_chars[-1] == '\\':
            repaired_chars.pop()
        repaired_chars.append('"')
        
    temp_str = "".join(repaired_chars).strip()
    while temp_str and temp_str[-1] in ', \n\t\r':
        temp_str = temp_str[:-1].strip()
        
    new_stack = []
    in_string = False
    escape = False
    for char in temp_str:
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in '{[':
                new_stack.append(char)
            elif char in '}]':
                if new_stack:
                    new_stack.pop()
                    
    suffix = []
    for bracket in reversed(new_stack):
        if bracket == '{':
            suffix.append('}')
        elif bracket == '[':
            suffix.append(']')
            
    repaired_json = temp_str + "".join(suffix)
    try:
        json.loads(repaired_json)
        return repaired_json
    except json.JSONDecodeError:
        for end in ["]}", "}", "]}", '"]}', '"]}"']:
            try:
                candidate = temp_str + end
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
    return s


def parse_generated_patch(raw: str) -> GeneratedPatch:
    # ✅ DEBUG: Log raw response
    print(f"[DEBUG] LLM raw response length: {len(raw)} chars")
    print(f"[DEBUG] LLM raw response preview: {raw[:500]!r}")

    text = raw.strip()

    if not text:
        raise ValueError(f"LLM returned empty response. Raw: {raw[:200]!r}")

    # ═══════════════════════════════════════════════════════════════════
    # FALLBACK: If the response is clearly not JSON at all (pure text/code),
    # return it as a "rationale-only" patch instead of crashing.
    # This handles the case where LLM ignores the JSON format instruction
    # and returns a natural language analysis or raw code.
    # ═══════════════════════════════════════════════════════════════════
    def _make_fallback_patch(content: str, reason: str) -> GeneratedPatch:
        """Return a no-op patch with the LLM's text as rationale."""
        print(f"[WARN] parse_generated_patch fallback: {reason}")
        # Truncate to reasonable length for rationale
        rationale = content[:4000] if len(content) > 4000 else content
        return GeneratedPatch(
            rationale=f"[LLM format error: {reason}]\n\n{rationale}",
            subtasks=[],
            files={},
            commands=[],
        )

    # Quick check: if the text doesn't contain '{' at all, it's definitely not JSON
    # Try to wrap it as a rationale-only response
    if '{' not in text:
        # LLM returned pure text — wrap it as a valid patch with no file changes
        return GeneratedPatch(
            rationale=text[:4000],
            subtasks=[],
            files={},
            commands=[],
        )

    # 1. Try to extract from markdown code blocks
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if code_block_match:
        text = code_block_match.group(1).strip()
        print(f"[DEBUG] Extracted from markdown block: {len(text)} chars")

    # 2. Remove common LLM prefixes/suffixes
    # Remove "Here's the JSON:", "The response is:", etc.
    text = re.sub(r'^(Here\'s|Here is|The response is|Response:).*?[\n\r]+', '', text, flags=re.IGNORECASE)
    # Remove trailing explanations after JSON
    text = re.sub(r'\}\s*[\n\r]+[A-Z].*$', '}', text, flags=re.DOTALL)

    print(f"[DEBUG] After cleanup: {len(text)} chars, preview: {text[:200]!r}")

    # 3. Try parsing, and fall back to scanning outer braces if it fails
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Find the first '{' and last '}' to extract JSON object
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = text[start_idx:end_idx+1].strip()

            # Try to detect if this looks like Python code instead of JSON
            # Python code has patterns like: variable_name=value, def function():, etc.
            python_patterns = [
                r'^\s*def\s+\w+\s*\(',     # def function( at line start
                r'^\s*class\s+\w+',        # class Name at line start
                r'^\s*import\s+\w+',       # import module at line start
                r'^\s*from\s+\w+\s+import', # from X import Y at line start
            ]
            if any(re.search(pattern, candidate, re.MULTILINE) for pattern in python_patterns):
                # Double-check: if it also contains JSON-like structure, don't reject
                if '"files"' not in candidate and '"operations"' not in candidate and '"rationale"' not in candidate:
                    return _make_fallback_patch(
                        raw,
                        f"LLM returned Python code instead of JSON"
                    )

            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                # Last resort: try repairing candidate
                try:
                    repaired = repair_truncated_json(candidate)
                    parsed = json.loads(repaired)
                except Exception:
                    return _make_fallback_patch(
                        raw,
                        f"Failed to parse JSON after bracket extraction: {exc}"
                    )
        else:
            # Maybe the whole text was truncated, try to repair from the start brace '{'
            start_idx = text.find('{')
            if start_idx != -1:
                candidate = text[start_idx:].strip()
                try:
                    repaired = repair_truncated_json(candidate)
                    parsed = json.loads(repaired)
                except Exception as exc:
                    return _make_fallback_patch(
                        raw,
                        f"Could not locate valid JSON block: {exc}"
                    )
            else:
                return _make_fallback_patch(
                    raw,
                    "No JSON object found in response"
                )

    if not isinstance(parsed, dict):
        raise ValueError("LLM response must parse to a JSON object.")

    # ═══ Handle alternative formats that LLM sometimes returns ═══
    
    # Format: {"operations": [{"type": "write", "path": "...", "content": "..."}]}
    if "operations" in parsed and isinstance(parsed["operations"], list):
        files_from_ops: dict[str, str] = {}
        for op in parsed["operations"]:
            if isinstance(op, dict) and op.get("type") == "write" and "path" in op and "content" in op:
                files_from_ops[op["path"]] = op["content"]
        if files_from_ops:
            return GeneratedPatch(
                rationale=parsed.get("rationale", parsed.get("plan", "Files created via operations format")),
                subtasks=parsed.get("subtasks", []),
                files=files_from_ops,
                commands=parsed.get("commands", []),
            )

    # Format: {"file_operations": [{"operation": "create", "file_path": "...", "content": "..."}]}
    if "file_operations" in parsed and isinstance(parsed["file_operations"], list):
        files_from_ops: dict[str, str] = {}
        for op in parsed["file_operations"]:
            if isinstance(op, dict) and "content" in op:
                path = op.get("file_path") or op.get("path") or op.get("filename", "")
                if path:
                    files_from_ops[path] = op["content"]
        if files_from_ops:
            return GeneratedPatch(
                rationale=parsed.get("rationale", parsed.get("explanation", "Files created")),
                subtasks=[],
                files=files_from_ops,
                commands=parsed.get("commands", []),
            )

    rationale_raw = parsed.get("rationale", parsed.get("explanation", parsed.get("reasoning", "")))
    subtasks_raw = parsed.get("subtasks", parsed.get("steps", []))
    files_raw = parsed.get("files", {})
    commands_raw = parsed.get("commands", parsed.get("shell_commands", []))

    if not isinstance(rationale_raw, str) or not isinstance(files_raw, dict):
        raise ValueError("Gemini response must contain string rationale and object files.")

    files: dict[str, str] = {}
    for path, content in files_raw.items():
        if not isinstance(path, str) or not isinstance(content, str):
            raise ValueError("Each files entry must map a path string to content string.")
        files[path] = content

    subtasks = [t for t in subtasks_raw if isinstance(t, str)]
    commands = [c for c in commands_raw if isinstance(c, str)]

    return GeneratedPatch(
        rationale=rationale_raw,
        subtasks=subtasks,
        files=files,
        commands=commands
    )
