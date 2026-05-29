# Requirements Document

## Introduction

Sharrowkin страдает от трёх связанных проблем, которые мешают довести продукт до «идеального» состояния:

1. **Агент теряет состояние посередине задачи.** Долгие задачи обрываются: процесс падает, LLM или инструмент таймаутит, WebSocket рвётся, после рестарта агент не возобновляет работу с последнего успешного шага. Чекпоинты сохраняются (`.sharrowkin/checkpoints/`), но не используются как полноценная точка возобновления, а ошибки тулзов и LLM не обрабатываются единообразно.
2. **UI нестабильно показывает состояние агента и таймплан.** Таймплан задач и текущая фаза (`Observe → Recall → Reason → Stabilize → Commit`) то отображаются, то исчезают, иногда показывают устаревшие данные. Часть событий теряется (очередь WebSocket переполняется и `put_nowait` отбрасывает события), при перезагрузке страницы таймплан не восстанавливается, потому что нет персистентности на стороне UI.
3. **UI выглядит несогласованно и дублируется.** Параллельно существуют две ветки фронтенда (`ui/app` + `ui/components` и почти пустая `ui/src`), нет единой дизайн-системы, компоненты не покрывают состояния загрузки/ошибки/пустоты, доступность не проверена.

Эта спецификация описывает требования к комплексной стабилизации бэкенда агента, надёжному real-time отображению состояния и UI-редизайну на единой дизайн-системе. Цель — чтобы любая запущенная задача либо доводилась до конца, либо корректно возобновлялась после сбоя, а пользователь в любой момент видел актуальный таймплан и фазу агента.

## Glossary

- **Agent_Core** — Python-процесс агента (`agent/core.py:SharrowkinAgent`), который исполняет цикл из пяти фаз и стримит события.
- **Phase** — одна из пяти фаз когнитивного цикла агента: `Observe`, `Recall`, `Reason`, `Stabilize`, `Commit`.
- **Run** — одно исполнение задачи агентом от старта до завершения (успех, отказ или принудительная остановка), идентифицируемое `run_id`.
- **Run_State** — машинно-читаемое состояние Run: `pending`, `running`, `paused`, `succeeded`, `failed`, `cancelled`, `interrupted`.
- **Checkpoint** — снимок состояния Run, достаточный для возобновления исполнения с последнего успешно завершённого шага. Хранится в `.sharrowkin/checkpoints/`.
- **Timeline** — упорядоченная последовательность шагов задачи (план + статус каждого шага), отображаемая в UI.
- **Timeline_Step** — единица таймплана: фаза, инструмент, под-задача или пользовательское сообщение, со статусом `pending | running | done | failed | skipped`.
- **Event** — сообщение, отправляемое Agent_Core в UI через WebSocket (`phase_change`, `task_update`, `tool_call`, `log`, `thinking`, `status`, `heartbeat`, `error` и т. д.).
- **Event_Stream** — упорядоченный поток Events для конкретного Run, доставляемый в UI.
- **UI_Client** — клиентское React/Next.js-приложение в `ui/app`, потребляющее Event_Stream и отображающее Timeline и состояние агента.
- **Session** — серверная сессия пользователя, привязанная к `session_id`, переживающая разрывы WebSocket в пределах `SESSION_TIMEOUT`.
- **Tool_Call** — вызов внешнего инструмента из фазы агента (например `run_pytest`, `apply_changes`, `github_*`, `run_terminal_command`).
- **Idempotency_Key** — детерминированный ключ Tool_Call, по которому повторный вызов с теми же входами возвращает результат предыдущего вызова без побочных эффектов.
- **Design_System** — набор переиспользуемых React-компонентов, токенов цвета/типографики/спейсинга и правил композиции, лежащий в `ui/components/ui/` и используемый всеми экранами.
- **A11y_Baseline** — минимальный уровень доступности: контраст ≥ WCAG AA, навигация с клавиатуры по всем интерактивным элементам, корректные ARIA-роли.

## Requirements

### Requirement 1: Возобновление прерванного Run после сбоя

**User Story:** Как пользователь, я хочу, чтобы при падении процесса агента, разрыве WebSocket или принудительной остановке Run возобновлялся с последнего успешного шага, а не начинался заново, чтобы не терять часы работы и не накапливать дублирующиеся изменения.

#### Acceptance Criteria

1. WHEN Agent_Core завершает Phase или Tool_Call успешно, THE Agent_Core SHALL записать Checkpoint в `.sharrowkin/checkpoints/<run_id>/` до возврата управления следующему шагу.
2. WHEN Agent_Core стартует и обнаруживает Checkpoint для незавершённого Run в состоянии `running` или `interrupted`, THE Agent_Core SHALL возобновить Run с последнего записанного Checkpoint без повторного исполнения уже завершённых шагов.
3. IF Checkpoint повреждён или не проходит валидацию схемы, THEN THE Agent_Core SHALL пометить Run как `failed` с причиной `checkpoint_corrupted` и оставить исходный Checkpoint-файл нетронутым для пост-мортема.
4. WHEN процесс Agent_Core завершается некорректно (SIGKILL, краш, OOM), THE Agent_Core SHALL при следующем старте перевести все Run в состоянии `running` старше 30 секунд в состояние `interrupted`.
5. WHILE Run находится в состоянии `interrupted`, THE Agent_Core SHALL предоставить API-метод `POST /api/agent/resume` принимающий `run_id` и возобновляющий исполнение с последнего Checkpoint.
6. THE Agent_Core SHALL гарантировать, что объём Checkpoint для одного Run не превышает 50 МБ, и при превышении SHALL обрезать историю промежуточных шагов с сохранением последних 100 шагов и итогового состояния.

### Requirement 2: Идемпотентность Tool_Call и устойчивость к ретраям

**User Story:** Как пользователь, я хочу, чтобы повторный запуск Tool_Call после сбоя или возобновления Run не создавал дублирующихся файлов, коммитов, PR или других побочных эффектов, чтобы возобновление было безопасным.

#### Acceptance Criteria

1. THE Agent_Core SHALL вычислять Idempotency_Key для каждого Tool_Call как детерминированный хеш от имени инструмента, нормализованных аргументов и `run_id`.
2. WHEN Agent_Core выполняет Tool_Call, для которого уже зафиксирован успешный результат с тем же Idempotency_Key в текущем Run, THE Agent_Core SHALL вернуть закэшированный результат без повторного выполнения побочных эффектов.
3. WHERE Tool_Call помечен как `mutating` (`apply_changes`, `run_terminal_command`, `github_create_pr`), THE Agent_Core SHALL до выполнения записать запись `tool_call_started` в журнал Run и после завершения — `tool_call_completed` с результатом.
4. IF Tool_Call возвращает ошибку, классифицируемую как `transient` (таймаут сети, 5xx, rate limit), THEN THE Agent_Core SHALL повторить вызов до 3 раз с экспоненциальной задержкой (база 1 секунда, множитель 2, jitter ±25%).
5. IF Tool_Call возвращает ошибку, классифицируемую как `permanent` (4xx кроме 429, синтаксическая ошибка, ошибка валидации), THEN THE Agent_Core SHALL прекратить ретраи и передать ошибку в Phase Stabilize с полным контекстом для перепланирования.

### Requirement 3: Таймауты и watchdog для долгих фаз

**User Story:** Как пользователь, я хочу, чтобы агент не зависал бесконечно ни на одном шаге, чтобы я мог рассчитывать на завершение задачи в обозримое время.

#### Acceptance Criteria

1. THE Agent_Core SHALL применять таймаут на уровне Phase, конфигурируемый в `AgentConfig.execution.phase_timeout_seconds` со значением по умолчанию 600 секунд.
2. THE Agent_Core SHALL применять таймаут на уровне Tool_Call, конфигурируемый в `AgentConfig.execution.tool_timeout_seconds` со значением по умолчанию 120 секунд, с возможностью переопределения per-tool.
3. WHEN Phase превышает свой таймаут, THE Agent_Core SHALL прервать Phase, записать Checkpoint, эмитировать Event `phase_timeout` и перевести Run в состояние `interrupted`.
4. WHEN Tool_Call превышает свой таймаут, THE Agent_Core SHALL терминировать дочерний процесс или отменить async-задачу, классифицировать ошибку как `transient_timeout` и применить логику ретраев из Requirement 2.
5. THE Agent_Core SHALL эмитировать `heartbeat` Event не реже одного раза в 15 секунд во время активной Phase, чтобы UI_Client мог отличить «агент работает» от «агент завис».

### Requirement 4: Доставка Event_Stream без потерь

**User Story:** Как пользователь, я хочу, чтобы UI отображал каждое событие агента ровно один раз и в правильном порядке, чтобы таймплан не «прыгал» и не терял шаги.

#### Acceptance Criteria

1. THE Agent_Core SHALL присваивать каждому Event монотонно возрастающий `seq` номер в пределах одного Run, начиная с 1.
2. THE Agent_Core SHALL персистить все Events для Run на диск (`.sharrowkin/runs/<run_id>/events.jsonl`) до отправки в WebSocket.
3. WHEN UI_Client подключается к WebSocket с параметром `last_seq`, THE Agent_Core SHALL отправить все Events с номером больше `last_seq` в порядке возрастания `seq` до отправки новых событий.
4. IF очередь отправки WebSocket переполнена, THEN THE Agent_Core SHALL применить backpressure (приостановить генерацию Events до освобождения места), а не отбрасывать Events.
5. WHEN WebSocket-соединение разрывается, THE UI_Client SHALL автоматически переподключиться с экспоненциальной задержкой (база 1 секунда, максимум 30 секунд) и передать `last_seq` для продолжения потока.
6. THE Event_Stream SHALL гарантировать, что для одного Run UI_Client получает каждый Event ровно один раз при условии, что клиент сохраняет `last_seq` между переподключениями.

### Requirement 5: Полный round-trip сериализации Run и Events

**User Story:** Как разработчик, я хочу, чтобы любой сохранённый Run и его Events можно было корректно прочитать обратно и восстановить идентичное состояние, чтобы возобновление и аудит работали детерминированно.

#### Acceptance Criteria

1. THE Agent_Core SHALL сериализовать Run-состояние и каждый Event в JSON по фиксированной версионированной схеме (`schema_version`).
2. FOR ALL валидных Run-состояний R, THE Agent_Core SHALL гарантировать, что `deserialize(serialize(R))` возвращает объект, эквивалентный R по всем наблюдаемым полям (round-trip property).
3. FOR ALL валидных Events E, THE Agent_Core SHALL гарантировать, что `deserialize(serialize(E))` возвращает объект, эквивалентный E (round-trip property).
4. WHEN Agent_Core читает сериализованный Run или Event с неизвестной `schema_version`, THE Agent_Core SHALL применить миграцию по реестру миграций или, при её отсутствии, отклонить запись с ошибкой `unsupported_schema`.
5. THE Agent_Core SHALL предоставлять pretty-printer для Run и Event, формирующий человекочитаемый JSON, который остаётся валидным входом для парсера (round-trip parse → print → parse).

### Requirement 6: Отображение Timeline в UI

**User Story:** Как пользователь, я хочу всегда видеть актуальный таймплан задачи с фазами, шагами и их статусами, чтобы понимать, чем агент сейчас занят и что осталось.

#### Acceptance Criteria

1. WHILE Run активен, THE UI_Client SHALL отображать Timeline со всеми Timeline_Step в порядке их создания.
2. WHEN UI_Client получает Event типа `task_update`, `phase_change` или `tool_call`, THE UI_Client SHALL обновить соответствующий Timeline_Step в течение 500 миллисекунд от момента получения Event.
3. THE Timeline SHALL отображать для каждого Timeline_Step его статус (`pending | running | done | failed | skipped`), название, длительность и иконку фазы или инструмента.
4. WHEN пользователь перезагружает страницу во время активного Run, THE UI_Client SHALL восстановить полный Timeline из последнего полученного снапшота и продолжить поток с `last_seq`.
5. IF UI_Client не получает ни одного Event в течение 30 секунд при активном Run, THEN THE UI_Client SHALL отобразить индикатор «соединение потеряно» и инициировать переподключение.
6. THE UI_Client SHALL сохранять Timeline в `localStorage` под ключом `run:<run_id>:timeline` после каждого обновления, чтобы пережить перезагрузку без обращения к серверу.

### Requirement 7: Корректность Timeline относительно Event_Stream

**User Story:** Как пользователь, я хочу быть уверен, что то, что показывает UI, соответствует тому, что реально делает агент, без устаревания и без потерянных шагов.

#### Acceptance Criteria

1. FOR ALL последовательностей Events `[e1, e2, ..., en]` для одного Run, THE UI_Client SHALL построить Timeline, в котором количество Timeline_Step равно количеству уникальных `(phase, step_id)` среди Events.
2. THE UI_Client SHALL гарантировать, что Timeline_Step никогда не возвращается из терминального статуса (`done`, `failed`, `skipped`) в нетерминальный (`pending`, `running`) — статусы движутся только вперёд (monotonicity invariant).
3. WHEN порядок применения двух Events E1 и E2, относящихся к разным Timeline_Step, меняется местами, THE результирующий Timeline SHALL быть идентичен (confluence для независимых Events).
4. THE UI_Client SHALL пересчитывать Timeline идемпотентно: повторное применение одного и того же Event с тем же `seq` SHALL не менять Timeline.
5. IF UI_Client получает Event со ссылкой на неизвестный `step_id`, THEN THE UI_Client SHALL создать новый Timeline_Step с этим `step_id` в статусе из Event, не теряя сообщение.

### Requirement 8: Видимость текущей фазы агента и прогресса

**User Story:** Как пользователь, я хочу в любой момент видеть, в какой фазе сейчас агент и сколько примерно осталось, чтобы оценивать ход выполнения.

#### Acceptance Criteria

1. THE UI_Client SHALL отображать индикатор текущей Phase из множества `Observe | Recall | Reason | Stabilize | Commit | Idle` в верхней части экрана Run.
2. WHEN Agent_Core эмитирует `phase_change` Event со статусом `started`, THE UI_Client SHALL обновить индикатор Phase в течение 500 миллисекунд.
3. THE UI_Client SHALL отображать счётчик завершённых и оставшихся Timeline_Step (например, «7 из 12») при наличии плана с известным числом шагов.
4. WHILE длительность Phase превышает 60 секунд без событий прогресса, THE UI_Client SHALL отобразить индикатор «фаза выполняется дольше обычного» с возможностью просмотреть последний `thinking` или `log` Event.
5. WHEN Agent_Core эмитирует Event `heartbeat`, THE UI_Client SHALL обновить отметку «последняя активность» отображаемую как относительное время («5 секунд назад»).

### Requirement 9: Отображение ошибок и состояний восстановления

**User Story:** Как пользователь, я хочу понимать, когда агент столкнулся с ошибкой, что он делает для восстановления и могу ли я вмешаться.

#### Acceptance Criteria

1. WHEN Agent_Core эмитирует Event типа `error` или `tool_call` со статусом `failed`, THE UI_Client SHALL отобразить соответствующий Timeline_Step с визуальным маркером ошибки и развёрнутым текстом ошибки по клику.
2. WHEN Agent_Core начинает retry Tool_Call, THE UI_Client SHALL отобразить под Timeline_Step счётчик попыток («попытка 2 из 3») без создания нового Timeline_Step.
3. WHEN Run переходит в состояние `interrupted`, THE UI_Client SHALL отобразить баннер «Run прерван» с кнопкой «Возобновить», вызывающей `POST /api/agent/resume`.
4. IF Run переходит в состояние `failed` с причиной `permanent`, THEN THE UI_Client SHALL отобразить итоговое сообщение об ошибке, кнопку «Перезапустить» и ссылку на лог-файл Run.
5. THE UI_Client SHALL предоставлять кнопку «Остановить», которая отправляет `POST /api/agent/stop` и переводит Run в состояние `cancelled` с подтверждением модальным окном.

### Requirement 10: Унификация фронтенда на единой дизайн-системе

**User Story:** Как пользователь, я хочу, чтобы интерфейс выглядел согласованно на всех экранах, без визуальных «кусочков» из разных эпох разработки.

#### Acceptance Criteria

1. THE UI_Client SHALL использовать единственную ветку фронтенда `ui/app` + `ui/components` для всех пользовательских экранов.
2. THE UI_Client SHALL использовать компоненты из `ui/components/ui/` (Design_System) для всех элементов: кнопки, поля ввода, карточки, диалоги, таблицы, индикаторы статуса.
3. WHERE параллельная ветка `ui/src` содержит уникальный код, THE команда SHALL мигрировать этот код в `ui/app` или `ui/components` и удалить `ui/src` до релиза.
4. THE Design_System SHALL экспортировать токены цвета, типографики, спейсинга и радиусов из единого источника (`ui/styles/tokens.css` или эквивалент в Tailwind config).
5. THE Design_System SHALL предоставить компоненты состояний: `Loading`, `EmptyState`, `ErrorState`, `Skeleton`, и эти компоненты SHALL использоваться вместо ad-hoc реализаций на всех экранах со списками или загрузкой данных.

### Requirement 11: Адаптивность и доступность UI

**User Story:** Как пользователь, я хочу пользоваться интерфейсом на разных экранах и с клавиатуры, чтобы продукт был удобен в любом окружении.

#### Acceptance Criteria

1. THE UI_Client SHALL корректно отображаться на ширине окна от 1024 пикселей до 2560 пикселей без горизонтального скролла на основных экранах (Chat, Workflow, Dashboard).
2. THE UI_Client SHALL обеспечивать соответствие A11y_Baseline: контраст текста ≥ 4.5:1 для обычного текста и ≥ 3:1 для крупного, согласно WCAG AA.
3. THE UI_Client SHALL поддерживать навигацию по Timeline с клавиатуры: `Tab`/`Shift+Tab` для перехода между Timeline_Step, `Enter` для разворачивания деталей, `Esc` для сворачивания.
4. THE UI_Client SHALL устанавливать корректные ARIA-роли и `aria-live="polite"` для области Timeline, чтобы скринридер озвучивал обновления статусов.
5. WHERE пользователь активировал режим «уменьшить движение» в системе (`prefers-reduced-motion`), THE UI_Client SHALL отключить декоративные анимации Timeline.

### Requirement 12: Парсер и сериализатор Run/Event-схемы

**User Story:** Как разработчик, я хочу иметь явный парсер и принтер схем Run и Event с round-trip гарантией, чтобы можно было автоматически валидировать совместимость и не ломать клиентов при изменении формата.

#### Acceptance Criteria

1. THE Agent_Core SHALL предоставить модуль `core/schemas/run.py` с функциями `parse_run(json: str) -> Run` и `print_run(run: Run) -> str`.
2. THE Agent_Core SHALL предоставить модуль `core/schemas/event.py` с функциями `parse_event(json: str) -> Event` и `print_event(event: Event) -> str`.
3. WHEN `parse_run` или `parse_event` встречает невалидный JSON или нарушение схемы, THE парсер SHALL вернуть структурированную ошибку с указанием поля и причины (например, `missing_field: seq`).
4. FOR ALL валидных Run R, `parse_run(print_run(R))` SHALL быть эквивалентным R (round-trip property).
5. FOR ALL валидных Events E, `parse_event(print_event(E))` SHALL быть эквивалентным E (round-trip property).
6. FOR ALL валидных JSON-строк s, описывающих Run или Event, `print(parse(s))` SHALL быть валидным входом для повторного парсинга и `parse(print(parse(s)))` SHALL давать тот же объект, что и `parse(s)` (round-trip parse → print → parse).

### Requirement 13: Очистка ресурсов и завершение Run

**User Story:** Как пользователь, я хочу, чтобы после завершения Run все временные процессы, файловые дескрипторы и подписки освобождались, чтобы система не накапливала «висящие» ресурсы.

#### Acceptance Criteria

1. WHEN Run переходит в любое терминальное состояние (`succeeded`, `failed`, `cancelled`), THE Agent_Core SHALL завершить все дочерние процессы Tool_Call, остановить файловые watchers и закрыть LLM-клиенты.
2. THE Agent_Core SHALL вести реестр активных Run и SHALL не превышать конфигурируемый лимит `max_concurrent_runs` (по умолчанию 4).
3. IF новый запрос на запуск Run приходит при достижении `max_concurrent_runs`, THEN THE Agent_Core SHALL поставить Run в очередь со статусом `pending` или вернуть `429 Too Many Requests` согласно конфигурации.
4. WHEN WebSocket-соединение клиента закрывается, THE Agent_Core SHALL продолжать исполнение Run в фоне и SHALL сохранить все Events на диск для последующего переподключения.
5. THE Agent_Core SHALL очищать события и чекпоинты завершённых Run старше 30 дней при старте процесса.

### Requirement 14: Наблюдаемость стабильности агента

**User Story:** Как разработчик, я хочу видеть метрики устойчивости агента, чтобы понимать, ухудшается ли стабильность и где узкие места.

#### Acceptance Criteria

1. THE Agent_Core SHALL экспонировать метрики через эндпоинт `GET /api/agent/metrics`: `runs_total`, `runs_succeeded`, `runs_failed`, `runs_interrupted`, `runs_resumed`, `tool_call_retries_total`, `phase_timeouts_total`.
2. THE Agent_Core SHALL логировать каждый переход Run между состояниями со структурой `{run_id, from_state, to_state, reason, timestamp}` в `monitoring/logs/`.
3. WHEN метрика `runs_failed / runs_total` превышает 0.2 за последний час, THE Agent_Core SHALL эмитировать предупреждение в лог уровня `warning` с трассой последних 10 ошибок.
4. THE Agent_Core SHALL ассоциировать каждую трассу OpenTelemetry-спана с `run_id` и `phase`, чтобы трассы можно было фильтровать по Run в инструментах наблюдаемости.

### Requirement 15: Производительность UI и рендера Timeline

**User Story:** Как пользователь, я хочу, чтобы UI оставался отзывчивым даже при длинных таймпланах в сотни шагов, без подвисаний при поступлении событий.

#### Acceptance Criteria

1. THE UI_Client SHALL отображать первый кадр экрана Workflow за ≤ 1500 миллисекунд от запроса страницы при нормальной нагрузке (LCP).
2. WHEN Timeline содержит 500 или более Timeline_Step, THE UI_Client SHALL применять виртуализацию списка и SHALL поддерживать прокрутку с частотой ≥ 50 кадров в секунду на референсной машине (M1 / Ryzen 5 5600 / 16 ГБ ОЗУ).
3. WHEN UI_Client получает Event, THE обновление DOM SHALL занимать не более 16 миллисекунд (один кадр) на референсной машине.
4. THE UI_Client SHALL батчить применение Events в окне 50 миллисекунд при поступлении более 20 Events в секунду, чтобы избежать каскадных ререндеров.
5. THE UI_Client SHALL не превышать 200 МБ резидентной памяти JavaScript при Run длительностью 1 час и Timeline в 1000 шагов.
