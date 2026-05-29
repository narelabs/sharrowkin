# Implementation Plan

## Overview 

Реализация в 22 задачах по 9 блокам:

1. **Backend Event_Stream и Resilience** (1–3): контракт событий с `seq`, `EventBus`, `retry_async`, `with_timeout`, `PhaseGuard`, `Checkpoint v2` с round-trip и миграцией.
2. **Backend сессии и роутер** (4, 7): `SessionRegistry` с replay buffer и heartbeat, persisted event log, рефактор `/api/agent/ws` под envelope `v=1` и `resume`.
3. **Backend интеграция в агент** (5, 6): обёртка фаз в `PhaseGuard`, ретраи LLM, degrade memory, deterministic mode для тестов.
4. **UI Visual_System** (8, 9): tokens.css в oklch, контраст-чек на CI, примитивы (Surface/Card/Badge/Button/IconBadge/Background/MotionGate), Reduced motion toggle.
5. **UI Event_Stream client** (10, 11): zod-схемы, `AgentSessionStore` с reducer-логикой и persistence, `AgentSocketClient` с heartbeat watchdog, reconnect, seq-gap detection.
6. **UI компоненты состояния** (12–15): Phase_Timeline и Status_Indicator без unmount, Connection_Indicator, Diagnostics panel + banner.
7. **UI интеграция** (16–18): рефактор `chat-shell` на store, виртуализация и performance, drawer-режим < 1024 px.
8. **Observability и тесты** (19, 20): OpenTelemetry spans, test harness, Playwright-сценарии.
9. **Cleanup и документация** (21, 22): удаление legacy формата и градиентов, документация event-stream и Visual_System.

PBT покрывают: round-trip checkpoint, retry bound, phase wall-clock bound, reducer determinism, phase set invariance, error stickiness.

## Task Dependency Graph

```
1 (Event_Stream)
 ├─▶ 4 (SessionRegistry) ──▶ 7 (WebSocket router) ──▶ 21 (cleanup)
 ├─▶ 5 (agent refactor) ─┬─▶ 19 (OTel spans)
 │                       └─▶ 6 (deterministic mode)
 └─▶ 10 (UI types/store) ──▶ 11 (SocketClient) ──▶ 16 (ChatShell integration)
2 (Resilience) ──▶ 5
3 (Checkpoint v2) ──▶ 4
                   ──▶ 5

8 (tokens.css) ──▶ 9 (primitives) ─┬─▶ 12 (PhaseTimeline)
                                   ├─▶ 13 (StatusBadge)
                                   ├─▶ 14 (ConnectionStatus)
                                   └─▶ 15 (Diagnostics)
                                      │
10 (store) ────────────────────────────┤
11 (SocketClient) ─────────────────────┤
                                       ▼
                                      16 (ChatShell) ──▶ 17 (perf)
                                                     ──▶ 18 (layout)
                                                     ──▶ 20 (E2E)

16, 17, 18, 19, 20 ──▶ 21 (cleanup) ──▶ 22 (docs)
```

Уровни параллелизма:

- **Wave 1**: 1, 2, 3, 8 — независимые фундаменты.
- **Wave 2**: 4 (need 1, 3), 5 (need 1, 2, 3), 9 (need 8), 10 (need 1).
- **Wave 3**: 6 (need 5), 7 (need 4), 11 (need 10), 12/13/14/15 (need 9, 10).
- **Wave 4**: 16 (need 11–15), 19 (need 5).
- **Wave 5**: 17, 18, 20 (need 16).
- **Wave 6**: 21 (need 7, 16, 17, 18).
- **Wave 7**: 22 (need 21).

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3", "8"] },
    { "wave": 2, "tasks": ["4", "5", "9", "10"] },
    { "wave": 3, "tasks": ["6", "7", "11", "12", "13", "14", "15"] },
    { "wave": 4, "tasks": ["16", "19"] },
    { "wave": 5, "tasks": ["17", "18", "20"] },
    { "wave": 6, "tasks": ["21"] },
    { "wave": 7, "tasks": ["22"] }
  ],
  "dependencies": {
    "1": [],
    "2": [],
    "3": [],
    "8": [],
    "4": ["1", "3"],
    "5": ["1", "2", "3"],
    "9": ["8"],
    "10": ["1"],
    "6": ["5"],
    "7": ["4"],
    "11": ["10"],
    "12": ["9", "10"],
    "13": ["9", "10"],
    "14": ["9", "10"],
    "15": ["9", "10"],
    "16": ["11", "12", "13", "14", "15"],
    "19": ["5"],
    "17": ["16"],
    "18": ["16"],
    "20": ["16"],
    "21": ["7", "16", "17", "18"],
    "22": ["21"]
  }
}
```

## Notes

- Все задачи выполняются строго в порядке зависимостей.
- Property-based тесты пишутся на Hypothesis (Python) и fast-check (TypeScript).
- Каждая задача либо добавляет код, либо рефакторит существующий, и завершается с проходящими тестами.
- Старый формат событий и старая Phase_Timeline сосуществуют с новыми до явной задачи на удаление, чтобы не ломать UI промежуточно.

## Tasks

- [x] 1. Backend: Event_Stream contract и EventBus
  - [x] 1.1 Создать `agent/event_stream.py` с pydantic-моделями всех типов событий (`session_info`, `phase_change`, `status`, `thinking`, `content`, `tool_call`, `tool_activity`, `task_update`, `log`, `error`, `heartbeat`, `agent_complete`, `repo_selector`)
    - Поля envelope: `v=1`, `type`, `session_id`, `seq`, `ts`, `payload`
    - Канонические enum: `PhaseId`, `PhaseStatus`, `AgentStatus`
    - _Requirements: 8.1, 8.2, 8.3, 8.6, 8.7_
  - [x] 1.2 Реализовать `EventBus` с per-session монотонным `seq`, инжектируемым sink, и удобными хелперами (`phase_change`, `status`, `thinking`, `tool_call`, `log`, `heartbeat`, `agent_complete`)
    - _Requirements: 8.1, 8.2_
  - [x] 1.3 Написать unit-тесты для EventBus: монотонность seq, валидация payload, обработка неизвестного type через ошибку схемы
    - _Requirements: 8.1, 8.2, 13.4_

- [x] 2. Backend: Resilience_Layer
  - [x] 2.1 Создать `agent/resilience.py` с `RetryPolicy`, `TransientError`, `PermanentError` и `default_classify` (httpx timeouts, 408/425/429/5xx → transient)
    - _Requirements: 6.3_
  - [x] 2.2 Реализовать `retry_async(fn, *, policy, classify)` с exponential backoff + jitter и cancellation safety
    - _Requirements: 6.3_
  - [x] 2.3 Реализовать `with_timeout(fn, *, seconds, on_timeout)` поверх `asyncio.wait_for`, с гарантированной отменой задачи
    - _Requirements: 6.7_
  - [x] 2.4 Реализовать `PhaseGuard` (async context manager): эмиссия `phase_change(running)` на входе, `phase_change(done|error)` на выходе, ловит исключения, не пробрасывает наружу, ограничивает 600 с по умолчанию
    - _Requirements: 6.1, 6.2, 6.7_
  - [x] 2.5 Реализовать `degrade_on_error(fn, fallback, *, code)` для memory-вызовов
    - _Requirements: 6.6_
  - [x] 2.6 Property-based тесты Resilience_Layer (Hypothesis): `retry_async` соблюдает `max_attempts` и верхнюю границу времени; `PhaseGuard` всегда завершается ≤ `max_seconds + ε`; ни одно исключение не пробрасывается наружу
    - _Requirements: 13.2, Property 4, Property 5, Property 6_

- [x] 3. Backend: Checkpoint v2
  - [x] 3.1 Создать `agent/checkpoints.py` с dataclass-ами `Checkpoint`, `CheckpointPhase`, `ToolCallSnapshot` (slots, frozen)
    - _Requirements: 7.2_
  - [x] 3.2 Реализовать `serialize(c) -> str` и `deserialize(raw) -> Checkpoint` как чистые функции (sorted keys JSON, tuple↔list)
    - _Requirements: 13.3, 7.2_
  - [x] 3.3 Реализовать `CheckpointStore` с методами `save`, `load_latest`, `list_recoverable`, `quarantine`, `prune(keep=50)`, путь `.sharrowkin/checkpoints/`
    - _Requirements: 7.1, 7.5, 7.7_
  - [x] 3.4 Реализовать `migrate_legacy(raw_dict) -> Checkpoint`: автоматическое определение по отсутствию `schema_version`, маппинг существующих полей `.sharrowkin/checkpoints/checkpoint_default_*.json`, запись migrated копии обратно
    - _Requirements: 7.6_
  - [x] 3.5 Property-based тест round-trip: `∀ c, deserialize(serialize(c)) == c`; стратегия Hypothesis для `Checkpoint`
    - _Requirements: 13.3, Property 3_
  - [x] 3.6 Тесты `prune` (ровно 50 файлов остаётся), `quarantine` (битый файл переезжает в `corrupt/`), `list_recoverable` (фильтр по `expires_at` и `current_phase != commit:done`)
    - _Requirements: 7.5, 7.7_

- [x] 4. Backend: SessionRegistry с replay buffer и heartbeat
  - [x] 4.1 Создать `api/sessions/session_registry.py` (или расширить существующий `sessions/`): per-session ring buffer 1024 событий + `next_seq`
    - _Requirements: 3.4, 8.2_
  - [x] 4.2 Реализовать `attach_socket` / `detach_socket`, очередь исходящих событий с **backpressure без потерь** (выкинуть `put_nowait` с дропом)
    - _Requirements: 3.4, 11.2_
  - [x] 4.3 Реализовать `heartbeat_loop`: эмиссия `heartbeat` event каждые 10–15 с, пока сокет открыт
    - _Requirements: 3.6_
  - [x] 4.4 Реализовать `resume(session_id, last_seq)`: replay из ring buffer, fallback на восстановление из Checkpoint v2 если `last_seq` слишком старый
    - _Requirements: 3.3, 3.4, 7.4_
  - [x] 4.5 Persisted event log на диск (`.sharrowkin/runs/<session>/events.jsonl`) для случаев, когда `last_seq` старше ring buffer
    - _Requirements: 3.4, 7.4_

- [ ] 5. Backend: рефакторинг `SharrowkinAgent.run` под EventBus и PhaseGuard
  - [-] 5.1 В `agent/core.py` добавить инжекцию `EventBus` в `run()` (старые dict-эмиттеры остаются параллельно, помечаются deprecated)
    - _Requirements: 8.1, 8.2_
  - [~] 5.2 Обернуть каждую фазу (`_observe`, `_recall`, `_reason`, `_stabilize`, `_commit`) в `PhaseGuard`; перевести внутренние ошибки на `bus.log(error) + phase_change(error)`
    - _Requirements: 6.1, 6.2, 6.7_
  - [~] 5.3 Обернуть LLM-вызовы (`GeminiClient.*`) в `retry_async` с `RetryPolicy(max_attempts=3, base_delay=1, max_delay=30, jitter=0.25)`
    - _Requirements: 6.3_
  - [~] 5.4 Обернуть memory-вызовы (DSM, RLD, TraceMemory, ConversationHistory) в `degrade_on_error`
    - _Requirements: 6.6_
  - [~] 5.5 Реализовать политику Stabilize: счётчик подряд-ошибок, после 2 — `bus.status(error, reason="stabilize_repeated_failure")` и выход
    - _Requirements: 6.5_
  - [~] 5.6 Триггерить запись `Checkpoint v2` после каждой завершённой фазы и не реже раз в 60 с (`asyncio.create_task` с таймером)
    - _Requirements: 7.1_
  - [~] 5.7 По окончании цикла гарантированно эмитить `agent_complete(outcome)` (success/error/stopped)
    - _Requirements: 6.2, Property 6_
  - [~] 5.8 Integration-тест с deterministic mode: `Scenario` со смесью ok/transient/permanent в каждой фазе → проверка последовательности событий и сохранённого checkpoint
    - _Requirements: 13.1, Property 6_

- [ ] 6. Backend: deterministic mode для тестов
  - [~] 6.1 Добавить параметр `deterministic_scenario` в `SharrowkinAgent.__init__`; при наличии — фазы не зовут LLM/tools, а воспроизводят сценарий через `EventBus`
    - _Requirements: 13.1_
  - [~] 6.2 Реализовать `Scenario` DSL: список `(phase, action)` где `action ∈ {ok, transient_error, permanent_error, tool_ok(...), tool_error(...), thinking(...)}`
    - _Requirements: 13.1_
  - [~] 6.3 Тест: deterministic run с ровно одним transient-ом в `reason` → агент ретраит и успешно завершает фазу
    - _Requirements: 6.3, 13.1_

- [ ] 7. Backend: WebSocket-роутер на новый протокол
  - [~] 7.1 В `api/routers/agent.py` подключить `SessionRegistry`, перевести `agent_websocket` на схему envelope `{v, type, session_id, seq, ts, payload}`
    - _Requirements: 8.1, 8.2_
  - [~] 7.2 Принимать клиентские сообщения `start` и `resume {session_id, last_seq}`; для `resume` — replay через `SessionRegistry.resume`
    - _Requirements: 3.3, 3.4_
  - [~] 7.3 Эмитить `heartbeat` через `SessionRegistry.heartbeat_loop`; на закрытии WS — `detach_socket`, **сессия продолжается в фоне**
    - _Requirements: 3.6_
  - [~] 7.4 На старте процесса: сканировать `recoverable` чекпоинты, помечать их в API `GET /api/agent/sessions/recoverable`
    - _Requirements: 7.3_
  - [~] 7.5 Endpoint `POST /api/agent/sessions/{id}/resume` для UI-кнопки `Reconnect` после исчерпания backoff
    - _Requirements: 3.5_

- [ ] 8. UI: Visual_System tokens
  - [~] 8.1 Создать `ui/styles/tokens.css` с CSS-переменными в группах color/typography/spacing/radius/elevation/motion под `:root[data-theme="dark"]` и `:root[data-theme="light"]`, oklch для цветов
    - _Requirements: 4.1, 4.5, 10.7_
  - [~] 8.2 Импортировать `tokens.css` в `ui/app/globals.css` перед Tailwind layers
    - _Requirements: 4.1_
  - [~] 8.3 CI-чек контраста: скрипт, считающий WCAG ratio для пар (`text/surface`, `text-muted/surface`, `accent/bg`) в обеих темах; фейлит если < 4.5/3
    - _Requirements: 4.5_
  - [~] 8.4 `TokenProvider` (`ui/components/visual/token-provider.tsx`): синхронизация темы с `next-themes` через `useLayoutEffect`, проставка `data-theme` без ремаунта
    - _Requirements: 4.3, 4.4_

- [ ] 9. UI: Visual_System primitives
  - [~] 9.1 `Surface`, `Card`, `Divider` (`ui/components/visual/{surface,card,divider}.tsx`), потребляют только токены
    - _Requirements: 4.1, 4.2, 4.6_
  - [~] 9.2 `Badge` с вариантами `neutral/success/warning/danger/info` и `Button` с вариантами `primary/secondary/ghost/destructive` × `sm/md`
    - _Requirements: 4.2, 4.6_
  - [~] 9.3 `IconBadge` (slot для lucide), состояния `idle/active/done/error` через `data-state`, без gradient-классов
    - _Requirements: 4.2, 4.6_
  - [~] 9.4 `Background` (`ui/components/visual/background.tsx`): single-instance через `MotionBudgetProvider`, prop `intensity: "off" | "subtle" | "full"`, ≤ 8 частиц
    - _Requirements: 4.7, 5.1_
  - [~] 9.5 `MotionGate` (`ui/components/visual/motion-gate.tsx`): объединяет `prefers-reduced-motion`, ручной toggle (localStorage `sharrowkin.motion.reduced`), Page Visibility API; при запрете — статический fallback
    - _Requirements: 5.2, 5.5, 5.6_
  - [~] 9.6 Settings-страница: тоггл `Reduced motion` в `ui/app/settings/`
    - _Requirements: 5.3_

- [ ] 10. UI: Event_Stream client + AgentSessionStore
  - [~] 10.1 Создать `ui/lib/agent-stream/types.ts` с типами `AgentEvent<T,P>`, `PhaseId`, `PhaseStatus`, `AgentStatus`, `ConnectionState`, `SessionState`, `TelemetryEntry`, `ToolActivity`
    - _Requirements: 8.1, 8.5_
  - [~] 10.2 Создать `ui/lib/agent-stream/schema.ts` с zod-схемами на каждый `type`, синхронно с pydantic-моделями бэкенда
    - _Requirements: 8.5, 13.4_
  - [~] 10.3 Реализовать `AgentSessionStore` (`ui/lib/agent-stream/store.ts`) на `useSyncExternalStore` или Zustand: redux-style reducer `applyEvent(event)`, селекторы `selectPhases`, `selectStatus`, `selectDiagnostics`, `selectThinking`, `selectToolActivity`, `selectConnection`
    - _Requirements: 1.2, 1.3, 1.4, 1.6, 2.1, 2.4, 2.6, 9.3, 11.4_
  - [~] 10.4 Reducer-логика: фазы инициализируются всегда канонической пятёркой, `phase_change` для неизвестной фазы → diagnostics + no-op, error stickiness, thinking ring buffer 500, diagnostics ring buffer 100
    - _Requirements: 1.2, 1.4, 2.4, 9.3, 11.4, Property 1, Property 7_
  - [~] 10.5 Persistence: debounced (100 мс) сериализация `phases/status/sessionId/lastSeq/runtimeMs` в `localStorage` под ключом `sharrowkin.session.<sessionId>`; восстановление в `useLayoutEffect` на маунте
    - _Requirements: 1.7_
  - [~] 10.6 Property-based тест reducer (fast-check): инвариант `set(phases.keys()) == 5`; error stickiness; идемпотентность повторного применения события с тем же `seq`
    - _Requirements: Property 1, Property 7, Property 8_

- [ ] 11. UI: AgentSocketClient
  - [~] 11.1 Реализовать `AgentSocketClient` (`ui/lib/agent-stream/socket-client.ts`) с методами `connect`, `resume`, `send`, `close`, `onEvent`, `onConnectionChange`
    - _Requirements: 3.1, 3.2, 3.3_
  - [~] 11.2 Heartbeat watchdog: 45 с от последнего события; на просрочке — `connection = "reconnecting"` и рестарт сокета
    - _Requirements: 3.7_
  - [~] 11.3 Reconnect: backoff 1→2→4→8→16→30, до 5 попыток; на успех `resume {session_id, last_seq}`; на исходе попыток — `connection="offline"`, `status="error"`, manual `Reconnect` action
    - _Requirements: 3.1, 3.5_
  - [~] 11.4 Seq gap detection: при `event.seq > lastSeq + 1` — отправить `resume` с текущим `lastSeq`
    - _Requirements: 8.2, Property 2_
  - [~] 11.5 Schema validation на входящих: zod parse fail → `diagnostics.push({level: error, source: schema})`, событие отброшено без throw
    - _Requirements: 8.5_
  - [~] 11.6 Critical event lane: `phase_change`, `status`, `error`, `agent_complete` применяются синхронно (микротаска), остальные через `requestAnimationFrame`-batched
    - _Requirements: 11.2_

- [ ] 12. UI: Phase_Timeline на новом store
  - [~] 12.1 Переписать `ui/components/chat/agent-phase-timeline.tsx`: ровно 5 узлов с `key={phaseId}`, без unmount/remount при смене статуса
    - _Requirements: 1.2, 1.5, Property 1_
  - [~] 12.2 Удалить `animate-spin-slow`, `animate-ping`, `animate-float`, gradient-цвета; заменить на `Surface`+`IconBadge`+`MotionGate`, статус через `data-status`
    - _Requirements: 4.6, 5.1_
  - [~] 12.3 Подписаться на store через `selectPhases`, не принимать пропсы из `chat-shell`
    - _Requirements: 1.1, 1.3_
  - [~] 12.4 Один CSS-keyframes для running (sweeping line через `--motion-base`); reduced-motion версия — статичная подсветка
    - _Requirements: 5.2, 11.5_

- [ ] 13. UI: Status_Indicator на новом store
  - [~] 13.1 Переписать `ui/components/chat/agent-status-badge.tsx`: один корневой узел, переходы через `data-status` + CSS transition
    - _Requirements: 2.5_
  - [~] 13.2 Удалить `animate-glow-pulse`, `animate-gradient-shift`, ping-кольца, частицы; стили через токены
    - _Requirements: 4.6, 5.1_
  - [~] 13.3 Подписка на `selectStatus` + `selectConnection`: при offline — `message = "Backend offline"`, `status` не сбрасывается в `done`
    - _Requirements: 2.6_
  - [~] 13.4 Форматирование `runtimeMs` в секунды на `done`
    - _Requirements: 2.7_
  - [~] 13.5 Watchdog: если store не получал `status`/`heartbeat` 15 с при активной сессии — store сам ставит `connecting` (внутренний таймер)
    - _Requirements: 2.3_

- [ ] 14. UI: Connection_Indicator
  - [~] 14.1 Переписать `ui/components/chat/connection-status.tsx`: подписка на `selectConnection` из store, отображение `connected | reconnecting (attempt N) | offline`
    - _Requirements: 3.2_
  - [~] 14.2 Кнопка `Reconnect` для состояния `offline`, вызывает `socketClient.connect()` ещё раз
    - _Requirements: 3.5_

- [ ] 15. UI: Diagnostics surface
  - [~] 15.1 Создать `ui/components/chat/diagnostics-panel.tsx`: ring buffer из store, фильтр по уровню, виртуализация при > 100
    - _Requirements: 9.1, 9.3, 11.3_
  - [~] 15.2 Создать `ui/components/chat/diagnostics-banner.tsx`: non-modal баннер для последнего `error`-event, действия `Copy details` (включает session_id, seq, phase, message, workspace) и `Reset session`
    - _Requirements: 9.2, 9.5_
  - [~] 15.3 Tool-activity список аннотируется иконкой ошибки и truncated message при `tool_call.status="error"`
    - _Requirements: 9.4_
  - [~] 15.4 Unread badge при закрытой панели — счётчик `diagnosticsUnread`, сбрасывается на open
    - _Requirements: 9.6_

- [ ] 16. UI: интеграция ChatShell на новый store
  - [~] 16.1 В `ui/components/chat/chat-shell.tsx` удалить дублирующие `useState` для `agentState`, `agentPhases`, `toolActivity`, `runtimeHints` — заменить на селекторы store
    - _Requirements: 1.1, 2.5, 9.3_
  - [~] 16.2 Заменить inline `socketRef`/обработчики `ws.onmessage` на `AgentSocketClient`; передавать события напрямую в `store.applyEvent`
    - _Requirements: 8.1, 11.2_
  - [~] 16.3 Сохранить совместимость с текущими localStorage ключами `sharrowkin-session-messages-*`; добавить новый ключ `sharrowkin.session.*` (только session-state, не сообщения)
    - _Requirements: 1.7_

- [ ] 17. UI: виртуализация и performance
  - [~] 17.1 Виртуализировать `MessageList` через `react-virtuoso` (или `@tanstack/react-virtual`) при `length > 100`
    - _Requirements: 11.1, 11.3_
  - [~] 17.2 Виртуализировать tool-activity и diagnostics при `length > 100`
    - _Requirements: 11.3_
  - [~] 17.3 Composer: локальный `useState` для текста, не дёргает store на каждом нажатии
    - _Requirements: 11.1_
  - [~] 17.4 Long-task observer в dev: PerformanceObserver на `longtask`, лог в diagnostics; e2e-проверка < 5/мин
    - _Requirements: 11.5_

- [ ] 18. UI: layout adaptivity
  - [~] 18.1 В `ChatShell` добавить media-queryхук, при `width < 1024` сайдбары превращаются в `Drawer` (`ui/components/ui/sheet.tsx`), сессия не размонтируется
    - _Requirements: 12.4, 12.5_
  - [~] 18.2 Tauri-detection: `useTauri()` (`typeof window !== "undefined" && "__TAURI_INTERNALS__" in window`), фолбэки на HTTP/WS API там, где нужны нативные возможности
    - _Requirements: 12.1, 12.2, 12.3_

- [ ] 19. Observability: OpenTelemetry spans
  - [~] 19.1 В `agent/core.py` обернуть каждую фазу в `tracer.start_as_current_span("agent.phase", attributes={session_id, phase, seq_start, seq_end, outcome})`
    - _Requirements: 13.6_
  - [~] 19.2 Обернуть LLM-вызовы (`agent.llm_call`) и tool-вызовы (`agent.tool_call`) в spans с `attempt`, `duration_ms`, `tool_id`, `name`, `status`
    - _Requirements: 13.6_

- [ ] 20. UI test harness и E2E
  - [~] 20.1 Создать `ui/lib/agent-stream/test-harness.ts` с экспортируемой `injectEvents(events)`; tree-shake под `process.env.NODE_ENV !== "production"`
    - _Requirements: 13.5_
  - [~] 20.2 Storybook-сторис для Phase_Timeline и Status_Indicator с пресетами event-потоков
    - _Requirements: 13.5_
  - [~] 20.3 Playwright-сценарии: 5 фаз в порядке Observe→Commit; при потоке `phase_change` корневой DOM-узел Phase_Timeline не меняется (`data-mounted-id` стабилен); reconnect-баннер появляется при искусственном close + восстанавливает state; status="error" не возвращается в "done"; reduced-motion отключает анимационные классы
    - _Requirements: 1.5, 2.4, 3.5, 5.2, Property 1, Property 7_

- [ ] 21. Cleanup и удаление legacy
  - [~] 21.1 Удалить старый формат событий в WebSocket (без `v`, без `seq`); WS принимает только envelope `v=1`
    - _Requirements: 8.1_
  - [~] 21.2 Удалить gradient-классы из `agent-hero-section.tsx`, `agent-aura-background.tsx`, `animated-orb.tsx`, `agent-energy-visualization.tsx` — где не используются Visual_System примитивы
    - _Requirements: 4.2, 4.6, 4.7_
  - [~] 21.3 Удалить дубликат стейтов в `chat-shell.tsx` (`agentState` + `agentPhases` + `toolActivity` после миграции на store)
    - _Requirements: 1.1_
  - [~] 21.4 Прогнать `npm run build` и `pytest` — фейлов нет, контраст-чек CI зелёный
    - _Requirements: 4.5, 11.5_

- [ ] 22. Документация
  - [~] 22.1 Создать `docs/event-stream.md` с финальной таблицей `type → payload` (источник правды)
    - _Requirements: 8.3, 8.4_
  - [~] 22.2 Обновить `SHARROWKIN_QUICKSTART.md` с инструкциями по resume и diagnostics
    - _Requirements: 7.3, 9.1_
  - [~] 22.3 Краткий README для `ui/components/visual/` с примерами использования примитивов
    - _Requirements: 4.1, 4.2_
