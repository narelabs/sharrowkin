# Technical Design

## Overview

Стабилизация и визуальный апгрейд Sharrowkin делается тремя слоями: **(1) единый Event_Stream** (контракт UI ↔ агент), **(2) Resilience_Layer + Checkpoint v2** на бэкенде (агент гарантированно доводит задачу до конца или явного fail с возможностью продолжить), **(3) Visual_System + детерминированные store-ы Phase_Timeline/Status_Indicator** на UI.

Архитектура целенаправленно делает Phase_Timeline и Status_Indicator чистой функцией от упорядоченного потока событий. UI больше не хранит отдельные «куски правды» в локальных стейтах компонентов и не пересоздаёт таймлайн при каждом сообщении. Бэкенд эмитит каждое событие с `seq`, и любой клиент может пере-подключиться и получить ровно недостающий хвост, восстановив идентичный UI-стейт.

Текущий код-база уже эмитит `phase_change`, `thinking`, `task_update` и т.п. (`agent/core.py:_phase`, `core/agent.py:_phase`, `api/routers/agent.py`), но: события не нумерованы, нет heartbeat, нет resume, нет схемы, исключения в фазах роняют процесс, чекпоинты не восстанавливают runtime-состояние, а в UI каждый компонент сам интерпретирует строки фаз. Это и стабилизируем.

## Architecture

### High-level diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        UI_Shell (Next.js)                        │
│                                                                  │
│   ┌──────────────────────┐     ┌────────────────────────────┐    │
│   │ AgentSessionStore    │◀───▶│ Visual_System primitives    │    │
│   │ (single Zustand     ) │     │ (Surface/Card/Badge/Button │    │
│   │  reducer + selectors)│     │  /Background, tokens.css)   │    │
│   └─────────┬────────────┘     └─────────────┬──────────────┘    │
│             │                                │                    │
│   Phase_Timeline · Status_Indicator · Diagnostics · MessageList   │
│   WorkspacePanel · Composer · TerminalEmulator · Background       │
└─────────────┬────────────────────────────────┬───────────────────┘
              │                                │
              │  AgentSocketClient (resume,    │
              │  heartbeat watchdog, seq gap   │
              │  detection, replay buffer)     │
              ▼                                │
       ┌──────────────────────────────────────────────┐
       │     /api/agent/ws  (FastAPI WebSocket)       │
       │  EventBus emits → JSON schema validator →    │
       │  send_json (with seq)                        │
       └──────┬─────────────────────────────────┬─────┘
              │                                 │
   ┌──────────▼──────────────┐       ┌──────────▼─────────────┐
   │  SessionRegistry        │       │  CheckpointStore v2    │
   │  (in-memory + Checkpoint│◀─────▶│  .sharrowkin/          │
   │   replay buffer)        │       │  checkpoints/          │
   └──────────┬──────────────┘       └────────────────────────┘
              │
   ┌──────────▼──────────────────────────────────────────────┐
   │           SharrowkinAgent.run() (agent/core.py)         │
   │   ┌─────────────────────────────────────────────────┐   │
   │   │           Resilience_Layer (new)                │   │
   │   │  retry · timeout · degrade · phase guard ·      │   │
   │   │  bounded LLM/tool wrapper                       │   │
   │   └────────────┬────────────────────────────────────┘   │
   │   Observe → Recall → Reason → Stabilize → Commit        │
   └─────────────────────────────────────────────────────────┘
```

### Module boundaries

- `agent/event_stream.py` (new): `EventBus`, `EventEnvelope`, schema validators, `seq` counter per session.
- `agent/resilience.py` (new): `retry_async`, `with_timeout`, `degrade_on_error`, `PhaseGuard` context manager.
- `agent/checkpoints.py` (new, replaces ad-hoc save in `memory/persistence.py` for run-state): `Checkpoint` dataclass, `serialize`/`deserialize`, `CheckpointStore`.
- `agent/core.py`: `SharrowkinAgent.run` рефакторится так, чтобы каждая фаза была обёрнута в `PhaseGuard` и эмитила через `EventBus`, а не возвращала dict-ы напрямую.
- `api/routers/agent.py`: WebSocket-роут переносит свою логику в `AgentSocketClient` сервер-сайда (heartbeat, resume, replay).
- `ui/lib/agent-stream/` (new): `AgentSocketClient`, `agentSessionStore` (Zustand или `useSyncExternalStore` + ref-reducer), schema (zod) синхронный с бэкендом.
- `ui/components/visual/` (new): `Surface`, `Card`, `Badge`, `Button`, `IconBadge`, `Divider`, `Background`, `MotionGate`, `TokenProvider`.
- `ui/components/chat/agent-phase-timeline.tsx`, `agent-status-badge.tsx`, `connection-status.tsx`: переписываются под новый store и Visual_System.
- `ui/components/chat/diagnostics-panel.tsx` (new).

## Event_Stream contract

### Envelope

Каждое событие — JSON-объект:

```json
{
  "v": 1,
  "type": "phase_change",
  "session_id": "session_ab12cd34",
  "seq": 42,
  "ts": "2026-05-25T18:45:54.123Z",
  "payload": { ... }
}
```

- `v` — версия схемы. `v = 1` фиксируется этой спецификацией.
- `seq` — монотонный 0-based счётчик внутри `session_id`. После `resume` бэкенд продолжает с `seq + 1`.
- `ts` — ISO-8601 UTC, для упорядочивания и observability.
- `payload` — типизированный объект, схема зависит от `type`.

### Канонические типы и payload

| `type`            | Назначение                          | Ключевые поля payload                                       |
|-------------------|-------------------------------------|-------------------------------------------------------------|
| `session_info`    | Старт/восстановление сессии         | `mode: "new" \| "resume"`, `last_seq?`, `recoverable?`      |
| `phase_change`    | Переход фазы                        | `phase: PhaseId`, `status: PhaseStatus`, `reason?`          |
| `status`          | Глобальный Status_Indicator         | `status: AgentStatus`, `message?`, `runtime_ms?`            |
| `thinking`        | Live reasoning stream               | `text: string`, `delta: boolean`                            |
| `content`         | Финальный контент ассистента        | `text: string`, `done: boolean`                             |
| `tool_call`       | Запуск/завершение tool call         | `tool_id`, `name`, `status`, `error?`                       |
| `tool_activity`   | Прогресс tool                       | `tool_id`, `progress?`, `target?`                           |
| `task_update`     | Обновление узла task plan           | `task_id`, `status`, `parent_id?`                           |
| `log`             | Структурированный лог               | `level: "debug"\|"info"\|"warning"\|"error"`, `message`, `code?`, `phase?`, `details?` |
| `error`           | Прерывающая ошибка                  | `code`, `message`, `phase?`, `recoverable: boolean`         |
| `heartbeat`       | Пульс (только живой канал)          | `agent_alive: boolean`                                      |
| `agent_complete`  | Конец Run_Session                   | `outcome: "done"\|"error"\|"stopped"`, `runtime_ms`         |
| `repo_selector`   | UI-промпт выбора репо               | `repos: RepoRef[]`, `prompt`                                |

`PhaseId` ∈ `{"observe","recall","reason","stabilize","commit"}` (lowercase). `PhaseStatus` ∈ `{"pending","running","done","error","skipped"}`. `AgentStatus` совпадает с UI-стороной (`idle` … `stopped`).

Для UI: любой неизвестный `type` или `v ≠ 1` логируется в Telemetry_Channel и игнорируется без throw (Req 8.5).

### Sequencing & resume

`SessionRegistry` хранит per-`session_id` ring buffer последних N (1024) событий и `next_seq`. На `resume`-сообщение от UI с полем `last_seq`:

- если `last_seq < next_seq − buffer.size`, бэкенд отвечает `session_info { mode: "resume", recoverable: false }` и поднимает сессию из Checkpoint v2 (полное состояние агента восстанавливается из чекпоинта, replay начинается с `seq = last_seq + 1`, недостающее восстанавливается из persisted log на диске).
- иначе бэкенд отдаёт все события с `seq > last_seq` из памяти и затем продолжает live-эмиссию.

Это закрывает Requirements 3.3, 3.4, 7.4.

### Schema enforcement

`agent/event_stream.py` содержит pydantic-модели на каждый `type`. `EventBus.emit(event)` валидирует payload перед отправкой; нарушения превращаются в `log` event уровня `error` с `code=schema_violation` (Req 13.4) и не попадают в основной поток. На UI используется тот же контракт через сгенерированные zod-схемы (`ui/lib/agent-stream/schema.ts`), чтобы любая поломка контракта ловилась и в рантайме, и в типах.

## Backend: Resilience_Layer

### Public API

```python
# agent/resilience.py
class TransientError(Exception): ...
class PermanentError(Exception): ...

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.25

async def retry_async(fn, *, policy: RetryPolicy, classify=default_classify): ...
async def with_timeout(fn, *, seconds: float, on_timeout: Callable | None = None): ...

class PhaseGuard:
    def __init__(self, *, phase: PhaseId, bus: EventBus, max_seconds: float = 600.0): ...
    async def __aenter__(self) -> "PhaseGuard": ...
    async def __aexit__(self, exc_type, exc, tb): ...
```

`PhaseGuard` инкапсулирует требования 6.1, 6.2, 6.7:

- эмитит `phase_change(running)` на входе, `phase_change(done)` на нормальном выходе;
- ловит любое исключение, эмитит `log(error)` + `phase_change(error)` с `reason=exception_type`, и **не** ре-райзит наружу — главный цикл `run()` просто получает `PhaseOutcome.error` и решает по политике (см. ниже);
- запускает `asyncio.wait_for` с таймаутом 600 с; на таймаут эмитит `phase_change(error, reason="phase_timeout")`.

`retry_async` оборачивает LLM-вызов: классификатор по умолчанию различает `httpx.TimeoutException`, `ReadTimeout`, HTTP 408/425/429/500/502/503/504 как `TransientError`, всё остальное — `PermanentError`. Бэкоф: `min(max_delay, base_delay * 2 ** (attempt-1))` плюс ±`jitter * delay`. Это закрывает Req 6.3.

`degrade_on_error` — небольшая обёртка для memory-вызовов: при исключении логирует `log(warning, code=memory_degraded)` и возвращает заранее заданный fallback, что позволяет агенту продолжать в in-memory режиме (Req 6.6).

### Phase loop policy

Псевдокод нового `SharrowkinAgent.run`:

```python
async def run(self, task: str, workspace_path: str, plan_mode: str = "autonomous"):
    bus = self._bus
    state = self._init_state(task, workspace_path)
    phases = [
        ("observe",    self._observe),
        ("recall",     self._recall),
        ("reason",     self._reason),
        ("stabilize",  self._stabilize),
        ("commit",     self._commit),
    ]
    stabilize_failures = 0

    for phase_id, fn in phases:
        async with PhaseGuard(phase=phase_id, bus=bus) as guard:
            await fn(state, bus, guard)
            await self._checkpoint_after(phase_id, state)

        if guard.outcome == "error":
            if phase_id == "stabilize":
                stabilize_failures += 1
                if stabilize_failures >= 2:
                    bus.status("error", reason="stabilize_repeated_failure")
                    break
                continue                  # одна повторная попытка
            if phase_id in ("observe", "recall"):
                continue                  # не критично
            bus.status("error", reason=f"{phase_id}_failed")
            break

    bus.agent_complete(outcome=self._final_outcome())
```

Это даёт Req 6.1–6.5 и явный путь до Checkpoint persistence + `agent_complete` event при любом исходе. Tool-call ошибки разбираются внутри фаз через `_tool_call(..., status="error")` и не прерывают фазу, если есть оставшаяся работа (Req 6.4).

## Backend: Checkpoint v2

### Format

```python
# agent/checkpoints.py
SCHEMA_VERSION = 2

@dataclass(slots=True, frozen=True)
class CheckpointPhase:
    id: PhaseId
    status: PhaseStatus
    started_at: str | None
    completed_at: str | None
    error: str | None

@dataclass(slots=True, frozen=True)
class Checkpoint:
    schema_version: int
    session_id: str
    workspace: str
    task: str
    plan_mode: str
    current_phase: PhaseId
    phases: tuple[CheckpointPhase, ...]
    conversation_ref: str               # путь к conversations/session_*.json
    in_flight_tool_calls: tuple[ToolCallSnapshot, ...]
    last_event_seq: int
    cognitive_state: dict[str, Any]     # dim, energy_ledger, attractors snapshot
    created_at: str
    expires_at: str                     # created_at + 24h

def serialize(c: Checkpoint) -> str: ...
def deserialize(raw: str) -> Checkpoint: ...
```

`serialize`/`deserialize` — чистые функции на JSON: сортированные ключи, `tuple` ↔ `list`, `dataclass` ↔ `dict`. Свойство round-trip `deserialize(serialize(c)) == c` доказывается property-based тестом в `tests/test_checkpoint_roundtrip.py` (Hypothesis-стратегия для `Checkpoint`, см. секцию Testing).

### Store rules

- Запись после каждой завершённой фазы и не реже чем раз в 60 с (Req 7.1) — таймер запускается в `SharrowkinAgent.run` и сбрасывается после каждой явной записи.
- Файлы: `.sharrowkin/checkpoints/checkpoint_<session>_<ts>.json`, плюс симлинк/копия `latest_<session>.json`.
- `recoverable` ⇔ `expires_at > now` ∧ `current_phase != commit:done` ∧ файл валиден.
- Битые файлы переезжают в `.sharrowkin/checkpoints/corrupt/<filename>.json`, с `log(error, code=checkpoint_corrupt)` (Req 7.5).
- Legacy формат (текущие `checkpoint_default_*.json` без `schema_version`) определяется по отсутствию ключа `schema_version`; `migrate_legacy(raw_dict) -> Checkpoint` мапит существующие поля и подставляет дефолты, после чего пишет migrated копию обратно (Req 7.6).
- Pruning: при создании нового checkpoint считаем все файлы для текущего workspace, отсортированные по `created_at`, и удаляем старше 50-го (Req 7.7).

### Resume

`SessionRegistry.resume(session_id, last_seq)` восстанавливает `Checkpoint` с диска, перестраивает `AgentRunState` (`task`, `workspace`, `cognitive_state`), включает replay буфер для seq < buffer.size и продолжает выполнение начиная с фазы `next_pending(checkpoint.phases)` (Req 7.4). Тот же путь используется UI после `prefers reconnect` после краха процесса.

## UI: Visual_System

### Tokens

`ui/styles/tokens.css` (single source) экспортирует CSS-переменные двух тем под селекторы `:root[data-theme="dark"]` (default) и `:root[data-theme="light"]`. Группы:

- **color**: `--color-bg`, `--color-surface`, `--color-surface-2`, `--color-border`, `--color-border-strong`, `--color-text`, `--color-text-muted`, `--color-accent`, `--color-accent-strong`, `--color-success`, `--color-warning`, `--color-danger`, `--color-info`. Все используют oklch для предсказуемого контраста.
- **typography**: `--font-sans`, `--font-mono`, шкалы `--text-xs`…`--text-2xl`, `--leading-tight/relaxed`.
- **spacing/radius**: `--space-1`…`--space-12`, `--radius-sm/md/lg/xl/full`.
- **elevation**: `--shadow-card`, `--shadow-overlay`, `--shadow-focus`.
- **motion**: `--motion-fast: 120ms`, `--motion-base: 200ms`, `--motion-slow: 360ms`, `--ease-standard: cubic-bezier(.2,.8,.2,1)`.

Контрастность проверяется на CI: для текстовых пар (`text` vs `surface`, `text-muted` vs `surface`, `accent` vs `bg`) считается WCAG ratio и фейлит, если ниже 4.5/3 (Req 4.5).

`TokenProvider` в `ui/components/visual/token-provider.tsx` синхронизирует тему через `next-themes` и проставляет `data-theme` без ремаунта (Req 4.4): через `useLayoutEffect` на `documentElement`, без сброса дочерних эффектов.

### Primitives

```
Surface     — base panel (bg + border + radius)
Card        — Surface + padding + elevation slot
Badge       — pill, варианты: neutral/success/warning/danger/info
Button      — варианты: primary/secondary/ghost/destructive, размеры: sm/md
IconBadge   — круглый бейдж со слотом для lucide icon, состояния: idle/active/done/error
Divider     — горизонтальный/вертикальный
Background  — единственный «cinematic» слой (orbs/aurora/particles), управляемый Motion_Budget
MotionGate  — обёртка, применяющая правила Reduced_Motion и видимости страницы
```

Все компоненты потребляют только токены. Все нынешние ad-hoc градиенты (`from-blue-500 to-purple-500`, `bg-gradient-to-br …`, `shadow-blue-500/50` и т.п. в `agent-phase-timeline.tsx`, `agent-status-badge.tsx`) переносятся в варианты примитивов либо удаляются (Req 4.2, 4.6, 4.7).

### Background и Motion_Budget

`Background` — единственный компонент, имеющий право на «кинематографичную» подложку. Принимает проп `intensity: "off" | "subtle" | "full"`, рассчитывает количество частиц как `min(8, intensity_factor)` и держит ≤ 1 такого инстанса в дереве через React Context (`MotionBudgetProvider`). Если внутри одного маршрута пытаются смонтироваться два Background — второй no-op + `console.warn` в dev.

`MotionGate` объединяет три источника:

1. `prefers-reduced-motion: reduce` (matchMedia).
2. Пользовательский тоггл `Reduced motion` в `app/settings`, сохраняется в `localStorage` ключом `sharrowkin.motion.reduced`.
3. Page Visibility API: при `document.hidden` приостанавливаются `requestAnimationFrame`-driven анимации через `AnimationController.pause()`.

Когда любой источник запрещает движение — рендер заменяется на статический fallback (Req 5.2, 5.5, 5.6). Унмаунт декоративных слоёв при смене маршрута происходит через `useEffect` cleanup в Background ≤ 300 мс (Req 5.4).

## UI: Phase_Timeline и Status_Indicator

### Single source of truth: AgentSessionStore

```ts
// ui/lib/agent-stream/store.ts
type PhaseId = "observe" | "recall" | "reason" | "stabilize" | "commit"
type PhaseStatus = "pending" | "running" | "done" | "error" | "skipped"

interface PhaseEntry {
  id: PhaseId
  status: PhaseStatus
  startedAt?: string
  completedAt?: string
  description?: string
}

interface SessionState {
  sessionId: string | null
  status: AgentStatus
  message?: string
  runtimeMs?: number
  phases: Record<PhaseId, PhaseEntry>   // строго все 5
  lastSeq: number
  connection: "online" | "reconnecting" | "offline"
  reconnectAttempt: number
  diagnostics: TelemetryEntry[]         // ring buffer 100
  diagnosticsUnread: number
  thinking: string                      // rolling buffer 500
  toolActivity: ToolActivity[]
}
```

Store — единственный потребитель Event_Stream. Phase_Timeline и Status_Indicator подписываются через **селекторы**, и не получают пропсов от родителя. Это устраняет рассинхрон между `agentState`, `agentPhases`, `toolActivity` в `chat-shell.tsx`, который сейчас живёт в трёх отдельных стейтах.

Reducer применяет события атомарно. Каноническая 5-фазная структура `phases` инициализируется при `session_info(mode: "new")` и **не сбрасывается** ничем, кроме явного старта новой сессии (Req 1.2, 1.6). Неизвестная фаза в `phase_change` логируется и не трогает `phases` (Req 1.4).

Когда подряд идёт несколько `phase_change` для одной фазы в пределах одного microtask, store применяет `last-write-wins` (Req 1.3), чтобы не было «прыжков» рендера.

### Animation that never re-mounts

Phase_Timeline рендерит ровно 5 узлов с `key={phaseId}`. Анимация «running»-индикатора живёт внутри узла в виде CSS-анимации на псевдоэлементе или `motion.span`, но сам узел не уходит/возвращается при смене статуса (Req 1.5). Пинг-кольца, частицы, glow заменяются на:

- статус-цвет (через токен),
- одна тонкая «sweeping»-анимация для running (через `--motion-base`),
- иконка lucide соответствующего состояния.

Старые `animate-spin-slow`, `animate-ping`, `animate-float` из `agent-phase-timeline.tsx` удаляются. Это даёт визуально спокойный таймлайн уровня Linear/Vercel (Req 4 в целом) и убирает CPU-нагрузку (Req 5.1, 11.5).

Status_Indicator также рендерит один корневой узел (Req 2.5), переходы статусов — `data-status` attribute + CSS transition. `error`-состояние «прилипает» (Req 2.4) до явного reset из UI (см. ниже). Если соединение оффлайн — поле `message` меняется на `Backend offline`, но `status` не превращается в `done` (Req 2.6). На завершение сессии `runtimeMs` форматируется в секунды (Req 2.7).

### Persistence

`AgentSessionStore` сериализует `phases`, `status`, `sessionId`, `lastSeq`, `runtimeMs` в `localStorage` ключом `sharrowkin.session.<sessionId>` после каждого изменения (debounce 100 мс). На маунте `ChatShell` пытается восстановить state в течение одного `useLayoutEffect` (Req 1.7). Это совместимо с `STORAGE_KEY = "sharrowkin-session-messages-${sessionId}"` который уже используется в `chat-shell.tsx` — добавляем второй ключ под session-state.

## UI: AgentSocketClient

`ui/lib/agent-stream/socket-client.ts` инкапсулирует всё, что сейчас живёт в монолитной `sendMessage` в `chat-shell.tsx`.

```ts
class AgentSocketClient {
  connect(input: { task: string; workspace: string; sessionId: string; lastSeq?: number }): void
  resume(sessionId: string, lastSeq: number): void
  send(message: ClientMessage): void
  close(reason: "user" | "navigate"): void
  onEvent(handler: (e: AgentEvent) => void): Unsub
}
```

Внутри:

- **heartbeat watchdog**: таймер 45 с от последнего `heartbeat` или любого события; на просрочке — `connection = "reconnecting"`, рестарт сокета (Req 3.7).
- **reconnect**: экспоненциальный backoff 1→2→4→8→16→30 с, до 5 попыток (Req 3.1). После успеха шлёт `resume {session_id, last_seq}` (Req 3.3). После 5 неудач — `connection = "offline"`, store ставит `status = error` и поднимается явная UI-кнопка `Reconnect` (Req 3.5).
- **seq gap detection**: если приходит событие с `seq > lastSeq + 1`, клиент шлёт `resume` с текущим `lastSeq`. Это страхует на случай потери сообщения через прокси.
- **schema validation**: каждое входящее событие парсится zod-схемой; нарушение → запись в diagnostics, событие отбрасывается (Req 8.5).

## UI: Diagnostics surface

Новый `DiagnosticsPanel` (правая sidebar tab) рендерит ring buffer `diagnostics` (последние 100, Req 9.3) с фильтром по уровню. На каждом `log` (warning/error) и `error` event store увеличивает `diagnosticsUnread` если панель закрыта (Req 9.6). Эта же панель показывает банер для `error` events с действиями `Copy details` (включает `session_id`, `seq`, `phase`, message, workspace — Req 9.5) и `Reset session` (только из `error`-состояния — это и есть путь сброса для Req 2.4).

Tool-activity список аннотируется иконкой ошибки и обрезанным сообщением, когда соответствующий `tool_call` имеет `status="error"` (Req 9.4). Это уже частично сделано в `appendToolActivity`, переносится 1:1 на новый store.

## Performance

- **Virtualization**: `react-virtual` (или `react-virtuoso`, уже совместим с tree of messages) для `MessageList`, tool-activity, diagnostics при `length > 100` (Req 11.3). Виртуализация активируется только сверх лимита, чтобы маленькие списки оставались простыми.
- **Thinking coalescing**: store режет `thinking` строку до 500 последних chunk-ов (Req 11.4). Реализация — кольцевой массив, по `flush` — `text = chunks.join("")`.
- **Critical event lane**: `phase_change`, `status`, `error`, `agent_complete` применяются **синхронно** в `socketClient.onEvent` через `flushSync`-equivalent (микротаска); остальные — через `requestAnimationFrame`-batched updates. Это гарантирует, что при бурсте 50 ev/s критические не теряются (Req 11.2).
- **Composer latency**: composer держит локальный `useState` для текста, не трогает основной store; main-thread long tasks контролируются Profiler-ом в e2e (Req 11.5, 11.1).

## Platform compatibility

Tauri-context определяется через `typeof window !== "undefined" && "__TAURI_INTERNALS__" in window`. `useTauri()` хук возвращает фичефлаги. На браузер падает HTTP/WS fallback там, где Tauri даёт нативный путь (например, чтение workspace-файлов) — это уже отражено в текущем `runRealCommand` через `/api/terminal` (Req 12.3).

Layout: основная сетка `ChatShell` (LeftSidebar | Center | RightSidebar) уже резизится. Добавляется breakpoint 1024 px: при `width < 1024` сайдбары превращаются в `Drawer` (нагружается из `ui/components/ui/sheet.tsx`), сессия не размонтируется (Req 12.4, 12.5).

## Testing & observability

### Deterministic mode

`SharrowkinAgent(deterministic_scenario=Scenario)` — конструкторный флаг. `Scenario` содержит упорядоченный список `(phase, action)` пар, где `action` ∈ `{ok, transient_error, permanent_error, tool_ok(...), tool_error(...), thinking(...)}`. В этом режиме фазы **не зовут LLM/tool**, а воспроизводят сценарий через те же эмиттеры. Используется в integration/property-тестах Resilience_Layer (Req 13.1, 13.2).

### Property-based tests

Под `tests/test_resilience_pbt.py` и `tests/test_checkpoint_pbt.py`:

- **Resilience_Layer**: hypothesis-генератор `RetryPolicy` + `failure_pattern` показывает, что: (а) количество попыток ≤ `max_attempts`, (б) суммарная задержка ≤ `Σ min(max_delay, base*2^k) * (1+jitter)`, (в) `with_timeout` всегда завершается ≤ `seconds + ε`.
- **Checkpoint round-trip**: `deserialize(serialize(c)) == c` для произвольных `Checkpoint` (Req 13.3).

### Synthetic event injection (UI)

`ui/lib/agent-stream/test-harness.ts` экспортирует `injectEvents(events: AgentEvent[])` для тестов. На production-сборке функция отсутствует (tree-shake под `process.env.NODE_ENV !== "production"`). Storybook/Playwright прогоняют сценарии Phase_Timeline и Status_Indicator через эту инъекцию (Req 13.5).

### OpenTelemetry

`monitoring/telemetry.get_tracer()` уже импортируется в `agent/core.py`. Spans:

- `agent.phase` per phase, attributes: `session_id`, `phase`, `seq_start`, `seq_end`, `outcome`.
- `agent.llm_call` per вызов, attributes: `provider`, `model`, `attempt`, `duration_ms`.
- `agent.tool_call` per tool, attributes: `tool_id`, `name`, `status`.

Все теги — на span. Это выполняет Req 13.6 без изменения существующих экспортёров.

## Migration plan

1. Внедрить `agent/event_stream.py` + `agent/resilience.py` без переключения старого кода. Покрыть unit + property tests.
2. Подключить `EventBus` к существующему `SharrowkinAgent.run` (минимально-инвазивно): обернуть фазы в `PhaseGuard`, оставить старые dict-эмиттеры рядом, выдавать оба формата в WebSocket некоторое время с флагом `v`.
3. Реализовать `Checkpoint v2` + миграцию legacy. Развернуть на dev окружении, дать поработать сутки, убедиться что recovery работает.
4. UI-сторона: добавить `tokens.css` и Visual_System примитивы, **не** трогая существующие компоненты (новые рядом). Прогон контраст-теста в CI.
5. Перевести `Phase_Timeline` и `Status_Indicator` на новый store + примитивы. Удалить старые градиенты/частицы.
6. Перевести `AgentSocketClient`, реализовать heartbeat/resume/diagnostics/banner.
7. Переключить чат-shell на store, удалить дубликаты state-полей.
8. Убрать legacy event-form в WebSocket, оставить только `v=1`.
9. Добавить Drawer-режим < 1024 px и Reduced motion toggle в settings.

## Out of scope

- Перевод всех остальных страниц (`workflow`, `dashboard`, `review`, `settings`) на новый Visual_System помечен как «follow-up». В этой спеке гарантируется только тот факт, что Visual_System не ломает их (используются текущие токены через прослойку), и что чат, агент, terminal, workspace panel, diagnostics — полностью на новой системе.
- Замена движка терминала и diff-viewer-а (используется существующая реализация `TerminalEmulator`/`FileDiffViewer`/`DiffViewer`). Меняется только их обвязка под Visual_System.
- Полный отказ от `framer-motion`. Оставляем для микро-анимаций примитивов; убираем только из агентских индикаторов и идл-фоновых эффектов.

## Components and Interfaces

### Backend (Python)

```python
# agent/event_stream.py
class EventBus:
    def __init__(self, session_id: str, sink: Callable[[dict], Awaitable[None]]) -> None: ...
    @property
    def next_seq(self) -> int: ...
    async def emit(self, type: str, payload: dict) -> None: ...
    async def heartbeat(self) -> None: ...
    async def status(self, status: AgentStatus, message: str = "", **kw) -> None: ...
    async def phase_change(self, phase: PhaseId, status: PhaseStatus, **kw) -> None: ...
    async def log(self, level: str, message: str, **kw) -> None: ...
    async def thinking(self, text: str, delta: bool = True) -> None: ...
    async def tool_call(self, tool_id: str, name: str, status: str, **kw) -> None: ...
    async def agent_complete(self, outcome: str, runtime_ms: int) -> None: ...

# agent/resilience.py
class RetryPolicy: ...
async def retry_async(fn, *, policy, classify=default_classify): ...
async def with_timeout(fn, *, seconds, on_timeout=None): ...

class PhaseGuard:
    outcome: Literal["pending", "ok", "error", "timeout"]
    async def __aenter__(self) -> "PhaseGuard": ...
    async def __aexit__(self, exc_type, exc, tb) -> bool: ...

# agent/checkpoints.py
@dataclass(slots=True, frozen=True)
class Checkpoint: ...
def serialize(c: Checkpoint) -> str: ...
def deserialize(raw: str) -> Checkpoint: ...
class CheckpointStore:
    def save(self, c: Checkpoint) -> Path: ...
    def load_latest(self, session_id: str) -> Checkpoint | None: ...
    def list_recoverable(self, workspace: Path) -> list[Checkpoint]: ...
    def quarantine(self, path: Path, reason: str) -> Path: ...
    def prune(self, workspace: Path, keep: int = 50) -> int: ...
```

`api/routers/agent.py` получает `SessionRegistry`:

```python
class SessionRegistry:
    async def get_or_create(self, session_id: str, *, workspace: Path) -> Session: ...
    async def resume(self, session_id: str, last_seq: int) -> ReplayResult: ...
    async def attach_socket(self, session_id: str, ws: WebSocket) -> None: ...
    async def detach_socket(self, session_id: str, ws: WebSocket) -> None: ...
    async def heartbeat_loop(self, session_id: str) -> None: ...
```

### UI (TypeScript)

```ts
// ui/lib/agent-stream/types.ts
type PhaseId = "observe" | "recall" | "reason" | "stabilize" | "commit"
type PhaseStatus = "pending" | "running" | "done" | "error" | "skipped"
type AgentStatus =
  | "idle" | "connecting" | "running" | "thinking"
  | "stabilizing" | "done" | "error" | "stopped"
type ConnectionState = "online" | "reconnecting" | "offline"

interface AgentEvent<T extends string = string, P = unknown> {
  v: 1
  type: T
  session_id: string
  seq: number
  ts: string
  payload: P
}

// ui/lib/agent-stream/socket-client.ts
class AgentSocketClient {
  connect(input: ConnectInput): void
  resume(sessionId: string, lastSeq: number): void
  send(message: ClientMessage): void
  close(reason: "user" | "navigate"): void
  onEvent(handler: (e: AgentEvent) => void): () => void
  onConnectionChange(handler: (s: ConnectionState, attempt: number) => void): () => void
}

// ui/lib/agent-stream/store.ts
interface AgentSessionStore {
  getState(): SessionState
  subscribe(listener: () => void): () => void
  applyEvent(e: AgentEvent): void
  resetSession(sessionId: string): void
  markDiagnosticsRead(): void
}
```

UI components (re-export of Visual_System and chat surfaces):

```
ui/components/visual/
  background.tsx        — single cinematic surface with intensity prop
  surface.tsx, card.tsx, badge.tsx, button.tsx, icon-badge.tsx, divider.tsx
  motion-gate.tsx       — applies Reduced_Motion + Page Visibility rules
  token-provider.tsx    — sets data-theme and exposes useToken()

ui/components/chat/
  agent-phase-timeline.tsx   (rewritten, store-driven, single mount)
  agent-status-badge.tsx     (rewritten, single root node)
  connection-status.tsx      (drives from ConnectionState in store)
  diagnostics-panel.tsx      (new)
  diagnostics-banner.tsx     (new, non-modal error banner)
```

## Data Models

### Session state (UI)

```ts
interface PhaseEntry {
  id: PhaseId
  status: PhaseStatus
  startedAt?: string
  completedAt?: string
  description?: string
  errorReason?: string
}

interface ToolActivity {
  id: string
  name: string
  status: "queued" | "running" | "done" | "error"
  message?: string
  target?: string
  startedAt: string
  completedAt?: string
  errorMessage?: string
}

interface TelemetryEntry {
  id: string
  ts: string
  level: "debug" | "info" | "warning" | "error"
  source: "agent" | "ui" | "schema" | "socket"
  code?: string
  phase?: PhaseId
  message: string
  details?: Record<string, unknown>
}

interface SessionState {
  sessionId: string | null
  status: AgentStatus
  message?: string
  startedAt?: string
  updatedAt?: string
  runtimeMs?: number
  phases: Record<PhaseId, PhaseEntry>
  lastSeq: number
  connection: ConnectionState
  reconnectAttempt: number
  diagnostics: TelemetryEntry[]
  diagnosticsUnread: number
  thinking: string
  toolActivity: ToolActivity[]
}
```

### Checkpoint (Backend)

См. `Checkpoint` dataclass выше. JSON-схема (для doc и валидации):

```json
{
  "schema_version": 2,
  "session_id": "session_ab12cd34",
  "workspace": "C:/Users/danik/Documents/sharrowkin",
  "task": "Refactor X",
  "plan_mode": "autonomous",
  "current_phase": "reason",
  "phases": [
    {"id":"observe","status":"done","started_at":"...","completed_at":"...","error":null},
    ...
  ],
  "conversation_ref": ".sharrowkin/conversations/session_1779715079.json",
  "in_flight_tool_calls": [
    {"tool_id":"abc","name":"run_pytest","args_digest":"...","started_at":"..."}
  ],
  "last_event_seq": 142,
  "cognitive_state": {"dim": 128, "energy_ledger": {...}, "attractors": [...]},
  "created_at": "2026-05-25T18:45:54Z",
  "expires_at": "2026-05-26T18:45:54Z"
}
```

## Correctness Properties

### Property 1: Phase set invariance
∀ session, `set(phases.keys()) == {observe,recall,reason,stabilize,commit}` всегда; reducer не имеет путей удаления или добавления ключей.

**Validates: Requirements 1.2, 1.4, 1.6, 10.1**

### Property 2: Seq monotonicity
Для любых двух подряд применённых событий `e1`, `e2` в UI store: `e2.seq == e1.seq + 1`. Backend гарантирует это для свежих событий и через replay-буфер после resume.

**Validates: Requirements 8.1, 8.2, 3.3, 3.4**

### Property 3: Checkpoint round-trip
`∀ c: Checkpoint, deserialize(serialize(c)) == c` — pure-function pair, проверяется property-based тестом.

**Validates: Requirements 13.3, 7.2**

### Property 4: Retry bound
`retry_async` делает ≤ `policy.max_attempts` вызовов и завершается за ≤ `Σ_{k=0..max_attempts-1} min(max_delay, base*2^k) * (1+jitter)` секунд для любых классификаторов.

**Validates: Requirements 6.3, 13.2**

### Property 5: Phase wall-clock bound
`PhaseGuard.__aexit__` срабатывает за ≤ `max_seconds + ε` секунд. Превышение порождает `phase_change(error, reason="phase_timeout")`, а не зависание.

**Validates: Requirements 6.7, 13.2**

### Property 6: Process survival
`SharrowkinAgent.run` никогда не пробрасывает исключения из фаз наружу. На любом пути выполнения цикл завершается событием `agent_complete` с явным `outcome ∈ {done, error, stopped}`.

**Validates: Requirements 6.1, 6.2, 6.5**

### Property 7: Error stickiness
После применения события `status(error)` UI store не возвращает `status` в `done` ни от какого последующего события; единственный путь сброса — явный `resetSession()` или старт новой сессии.

**Validates: Requirements 2.4, 2.6, 9.2**

### Property 8: Reducer determinism
Применение последовательности событий `[e1, e2, …, en]` через `applyEvent` даёт состояние, идентичное батч-применению той же последовательности (одинаково на всех клиентах при одинаковом входном потоке).

**Validates: Requirements 1.3, 11.2, 13.5**

## Error Handling

| Class                      | Detection                                  | Response                                                                                                |
|----------------------------|--------------------------------------------|---------------------------------------------------------------------------------------------------------|
| Phase exception            | `PhaseGuard.__aexit__`                     | `log(error)` + `phase_change(error, reason=ExceptionType)`; checkpoint; main loop applies phase policy. |
| LLM transient error        | `retry_async` classifier                   | До 3 попыток с backoff+jitter; на превышении — `phase_change(error, reason="llm_unavailable")`.         |
| Tool exception             | `try/except` вокруг tool runner            | `tool_call(error)` event с `error.type/message`; фаза продолжается, если есть оставшаяся работа.        |
| Stabilize repeated failure | счётчик в run-loop                         | После 2 неудач: `status(error, reason="stabilize_repeated_failure")`, checkpoint, выход цикла.          |
| Memory subsystem failure   | `degrade_on_error` обёртка                 | `log(warning, code="memory_degraded")`, fallback на in-memory структуры.                                 |
| Phase timeout              | `asyncio.wait_for`                         | `phase_change(error, reason="phase_timeout")`, checkpoint, политика фазы.                               |
| Checkpoint corrupt         | `deserialize` raises                       | Файл переезжает в `checkpoints/corrupt/`, `log(error, code="checkpoint_corrupt")`, сессия с нуля.        |
| Schema violation (UI in)   | zod parse fail                             | `diagnostics.push({level:"error", source:"schema"})`, событие отбрасывается.                            |
| WebSocket close            | `socket.onclose`                           | Reconnect backoff 1→30 с до 5 попыток; на исходе — `connection=offline`, `status=error`.                |
| Heartbeat miss             | watchdog 45 с                              | Таймер триггерит reconnect-flow.                                                                        |
| Unknown event type         | reducer default branch                     | `diagnostics.push`, событие отбрасывается, `phases` не трогаются.                                       |

## Testing Strategy

### Unit
- `agent/event_stream.py`: схема валидируется per `type`, `seq` монотонен, `EventBus.emit` шлёт через инжектированный sink.
- `agent/resilience.py`: `retry_async` классификация transient/permanent, `with_timeout` cancel-safety, `PhaseGuard` поведение на `ok` / exception / `wait_for` timeout.
- `agent/checkpoints.py`: `serialize`/`deserialize` симметрия; `migrate_legacy` на zip-фикстурах текущих файлов из `.sharrowkin/checkpoints/`; `prune` оставляет ровно 50.
- UI store reducer: применение каждого `type` с табличными кейсами; проверка инвариантов 1, 2, 7.

### Property-based (Hypothesis / fast-check)
- `Checkpoint round-trip`: стратегия для `Checkpoint` → `deserialize(serialize(c)) == c`.
- `Retry bound`: для случайных `RetryPolicy` и паттернов ошибок проверяется верхняя граница попыток и времени.
- `Reducer associativity over batches`: применение событий последовательно vs батчем даёт одинаковый стейт (UI store).
- `Phase set invariance`: на любой последовательности валидных + невалидных событий store сохраняет 5 канонических фаз.

### Integration
- Deterministic-mode сценарий: запускаем `SharrowkinAgent` со `Scenario` (мок LLM/tools), проверяем итоговую последовательность событий и checkpoint содержимое.
- WebSocket resume: тест поднимает FastAPI in-process, шлёт серию событий, рвёт сокет, переподключается, проверяет восстановление по `seq`.
- Checkpoint recovery: убиваем агента в середине `reason`, рестартуем, ожидаем `session_info(mode="resume", recoverable=true)` и продолжение с нужной фазы.

### UI E2E
- Storybook + Playwright прогоняют синтетический Event_Stream через `injectEvents` для:
  - корректного рендеринга 5 фаз в порядке Observe→Commit;
  - неизменности корня Phase_Timeline и Status_Indicator при потоке `phase_change` (DOM-snapshot до/после с проверкой того, что `data-mounted-id` не меняется);
  - reconnect-баннера при потере соединения и восстановления стейта;
  - сохранения статуса `error` до явного reset;
  - корректной работы Reduced_Motion (DOM не имеет анимационных классов при включённом флаге).

### Performance
- Profiler-snapshot Composer-а под нагрузкой `MessageList` ≥ 500 (Req 11.1).
- Burst-тест 50 ev/s, проверка отсутствия дропов критичных событий (Req 11.2).
- Long-task observer в e2e, порог 5/мин (Req 11.5).
