"""Gemini REST client for Sharrowkin."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import requests

# Manually load .env variables if present - check multiple locations
env_locations = [
    Path(__file__).parent.parent.parent / ".env",  # backend/backend/.env
    Path(__file__).parent.parent.parent.parent / ".env",  # backend/.env
]

for env_path in env_locations:
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    # Only set if not already set (first file wins)
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = val.strip()


@dataclass(slots=True)
class GeneratedPatch:
    rationale: str
    subtasks: list[str]
    files: dict[str, str]
    commands: list[str]


AUTONOMOUS_AGENT_POLICY = """
You are Sharrowkin, a cloud-based autonomous developer agent that works exclusively with GitHub repositories.

CRITICAL: You do NOT have access to local filesystems. All file operations must go through GitHub API.

Operate with high agency:
- Do not ask the user follow-up questions unless the task is impossible, destructive, or requires external credentials.
- Infer safe defaults from the repository, existing conventions, and conversation context.
- For ambiguous implementation details, choose the smallest reversible path and state the assumption in the rationale.
- Read/inspect relevant files before changing them; preserve public APIs and existing style.
- After edits, run the cheapest relevant validation commands available in the repository.
- If validation fails, diagnose the concrete failure and choose a different fix path instead of repeating the same patch.
- Never include secrets, never exfiltrate files, and never run git commit/push/merge commands.

GitHub API Integration (REQUIRED):
You work ONLY with GitHub repositories through these API endpoints:

1. List repositories:
   GET http://127.0.0.1:8000/api/github/repos
   Returns: list of user's repositories

2. Clone repository to server workspace:
   Use github_clone_repo(token, owner, repo) tool
   This clones the repository to /tmp/sharrowkin-workspace/repos/{repo}
   After cloning, you can analyze files locally

3. Get repository tree (file structure):
   GET http://127.0.0.1:8000/api/github/repos/{owner}/{repo}/tree?sha=main&recursive=true
   Returns: complete file tree with paths

4. Get file contents:
   GET http://127.0.0.1:8000/api/github/repos/{owner}/{repo}/file?path={file_path}&ref=main
   Returns: decoded file content as text

5. Get directory contents:
   GET http://127.0.0.1:8000/api/github/repos/{owner}/{repo}/contents?path={dir_path}&ref=main
   Returns: list of files/folders in directory

6. Update/create file:
   PUT http://127.0.0.1:8000/api/github/repos/{owner}/{repo}/file
   Body: {"path": "...", "content": "...", "message": "...", "branch": "main", "sha": "..."}

7. List branches:
   GET http://127.0.0.1:8000/api/github/repos/{owner}/{repo}/branches

8. Create PR:
   POST http://127.0.0.1:8000/api/github/repos/{owner}/{repo}/pr
   Body: {"title": "...", "body": "...", "head": "...", "base": "main"}

WORKFLOW:
1. When user asks about repositories: call GET /api/github/repos
2. When user asks to clone a repo: use github_clone_repo(token, owner, repo)
3. When user asks about files in a repo: call GET /api/github/repos/{owner}/{repo}/tree
4. When user asks to read a file: call GET /api/github/repos/{owner}/{repo}/file?path=...
5. When user asks to edit files:
   - First read the file to get its SHA
   - Then call PUT /api/github/repos/{owner}/{repo}/file with new content
6. When user asks to create PR: call POST /api/github/repos/{owner}/{repo}/pr

NEVER:
- Try to access local filesystem (no /home, /Users, C:\\, etc.)
- Use commands like 'ls', 'cat', 'find' - they won't work
- Assume files exist locally - always fetch from GitHub API

The GitHub token is automatically provided by the system.
""".strip()


def _autonomous_json_system_prompt() -> str:
    return (
        f"{AUTONOMOUS_AGENT_POLICY}\n\n"
        "Return only strict JSON with keys: rationale, subtasks, commands, and files. "
        " - 'rationale': concise explanation of decisions, assumptions, and validation plan.\n"
        " - 'subtasks': list of decomposed subtasks for complex goals.\n"
        " - 'commands': terminal commands to execute for inspection or validation when useful; do not include git commit/push/merge.\n"
        " - 'files': object mapping relative file paths to complete replacement contents.\n"
        "Do not wrap JSON in markdown."
    )


def _get_response_text(response: requests.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        chunks = []
        for line in response.iter_lines():
            if line:
                line_str = line.decode("utf-8").strip()
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
            return data["content"][0]["text"]
        elif isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        elif isinstance(data, dict) and "candidates" in data and len(data["candidates"]) > 0:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return ""


class GeminiConfigurationError(RuntimeError):
    pass


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

    @property
    def configured(self) -> bool:
        return bool(self.api_key) or bool(self.omniroute_base_url)

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        if not self.api_key and not self.omniroute_base_url:
            raise GeminiConfigurationError(
                "Neither GEMINI_API_KEY nor ANTHROPIC_BASE_URL is set."
            )
            
        if self.omniroute_base_url:
            base_url = self.omniroute_base_url.rstrip("/")
            url = f"{base_url}/messages"
            headers = {
                "x-api-key": self.omniroute_token,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            system = system_instruction or "You are Sharrowkin, a local autonomous developer agent."
            payload = {
                "model": self.omniroute_model,
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "stream": False,
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=90, stream=True)
                if response.status_code == 404:
                    # Try OpenAI fallback
                    openai_url = f"{base_url}/chat/completions"
                    openai_headers = {
                        "Authorization": f"Bearer {self.omniroute_token}",
                        "Content-Type": "application/json",
                    }
                    openai_payload = {
                        "model": self.omniroute_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "stream": False,
                    }
                    openai_response = requests.post(openai_url, headers=openai_headers, json=openai_payload, timeout=90, stream=True)
                    openai_response.raise_for_status()
                    return _get_response_text(openai_response)
                
                response.raise_for_status()
                return _get_response_text(response)
            except Exception as e:
                raise RuntimeError(f"Omniroute call failed: {e}")
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
            try:
                response = requests.post(url, json=payload, timeout=90)
                response.raise_for_status()
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                raise RuntimeError(f"Gemini call failed: {e}")

    def classify_intent(self, task: str) -> dict[str, object]:
        import re
        
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
            "create", "write", "fix", "add", "delete", "remove", "change",
            "make", "run", "install", "update", "refactor", "build", "test",
            "deploy", "debug", "implement", "file", "code", "function",
            "analyze", "scan", "study",
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
            raw_response = self.generate_text(prompt, system_instruction)
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

    def generate_patch(
        self,
        *,
        task: str,
        workspace_summary: str,
        memory_context: str,
        previous_error: str = "",
        action_history: list[str] = None,
        file_contents: dict[str, str] = None,
        conversation_history: list[dict] = None,
    ) -> GeneratedPatch:
        if not self.api_key and not self.omniroute_base_url:
            raise GeminiConfigurationError(
                "Neither GEMINI_API_KEY nor ANTHROPIC_BASE_URL is set. "
                "Add one of them to the environment to enable code generation."
            )

        prompt = self._build_prompt(task, workspace_summary, memory_context, previous_error, action_history, file_contents)

        # Build messages array with conversation history
        messages = []
        if conversation_history:
            # Add previous conversation turns (limit to last 10 to avoid token overflow)
            for msg in conversation_history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current prompt as final user message
        messages.append({"role": "user", "content": prompt})

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
            payload = {
                "model": self.omniroute_model,
                "max_tokens": 8192,
                "system": system_prompt,
                "messages": messages,
                "temperature": 0.2,
                "stream": False,  # Explicitly request non-streaming response
            }
            
            import time
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=90, stream=True)
                    
                    # Check for 402 Specifically
                    if response.status_code == 402:
                        raise GeminiConfigurationError(
                            "Omniroute proxy returned 402 (Payment Required). "
                            "Please check your API key, billing status, or funds/credits on your Omniroute console. "
                            f"Response details: {response.text[:200]}"
                        )
                    
                    response.raise_for_status()
                    text = _get_response_text(response)
                    return parse_generated_patch(text)
                    
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code == 402:
                        raise GeminiConfigurationError(
                            "Omniroute proxy returned 402 (Payment Required). "
                            "Please check your API key, billing status, or funds/credits on your Omniroute console. "
                            f"Response details: {e.response.text[:200]}"
                        )
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    # Fallback check if the proxy returned 404 on /messages (e.g. OpenAI compatibility)
                    if response.status_code == 404 and attempt == 0:
                        # Try OpenAI-compatible chat completion endpoint as fallback
                        openai_url = f"{base_url}/chat/completions"
                        openai_headers = {
                            "Authorization": f"Bearer {self.omniroute_token}",
                            "Content-Type": "application/json",
                        }
                        openai_payload = {
                            "model": self.omniroute_model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.2,
                            "stream": False,  # Explicitly request non-streaming response
                        }
                        try:
                            openai_response = requests.post(openai_url, headers=openai_headers, json=openai_payload, timeout=90, stream=True)
                            if openai_response.status_code == 402:
                                raise GeminiConfigurationError(
                                    "Omniroute proxy returned 402 (Payment Required) on fallback. "
                                    "Please check your API key, billing status, or funds/credits on your Omniroute console. "
                                    f"Response details: {openai_response.text[:200]}"
                                )
                            openai_response.raise_for_status()
                            text = _get_response_text(openai_response)
                            return parse_generated_patch(text)
                        except GeminiConfigurationError:
                            raise
                        except Exception:
                            pass
                    raise
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
            import time
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, json=payload, timeout=90)
                    response.raise_for_status()
                    data = response.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return parse_generated_patch(text)
                except requests.exceptions.HTTPError as e:
                    if response.status_code >= 500 and attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    raise

    def _build_prompt(
        self,
        task: str,
        workspace_summary: str,
        memory_context: str,
        previous_error: str,
        action_history: list[str] = None,
        file_contents: dict[str, str] = None,
    ) -> str:
        sections = [
            "AUTONOMOUS OPERATING POLICY",
            AUTONOMOUS_AGENT_POLICY,
            "TASK",
            task,
            "WORKSPACE AST SUMMARY",
            workspace_summary,
            "RLD AND DSM MEMORY CONTEXT",
            memory_context,
        ]
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
    text = raw.strip()
    
    # 1. Try to extract from markdown code blocks
    import re
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if code_block_match:
        text = code_block_match.group(1).strip()
        
    # 2. Try parsing, and fall back to scanning outer braces if it fails
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidate = text[start_idx:end_idx+1].strip()
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                # Last resort: try repairing candidate
                try:
                    repaired = repair_truncated_json(candidate)
                    parsed = json.loads(repaired)
                except Exception:
                    raise ValueError(
                        f"Failed to parse JSON even after bracket extraction. "
                        f"Content: {candidate[:300]!r}. Error: {exc}"
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
                    raise ValueError(
                        f"Could not locate a valid JSON block in LLM response. "
                        f"Content: {raw[:300]!r}. Error: {exc}"
                    )
            else:
                raise ValueError(
                    f"Could not locate a valid JSON block in LLM response. "
                    f"Content: {raw[:300]!r}"
                )
            
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must parse to a JSON object.")
    rationale_raw = parsed.get("rationale", "")
    subtasks_raw = parsed.get("subtasks", [])
    files_raw = parsed.get("files", {})
    commands_raw = parsed.get("commands", [])

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
