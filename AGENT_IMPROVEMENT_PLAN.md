# Agent Improvement Plan - Path to Ideal State

**Goal**: Довести агента до состояния, где достаточно одного промпта для реализации любого проекта или идеи

**Date**: 2026-05-23 18:23 UTC

---

## 🔍 Текущие проблемы (Root Cause Analysis)

### 1. **Системы памяти используются неправильно**
**Проблема**: DSM, RLD, MemoryField, TraceMemory инициализируются, но слабо интегрированы в reasoning loop

**Текущее состояние**:
- ✅ DSM и RLD вызываются в Phase 2 (Recall) через `memory.recall()`
- ✅ MemoryField обновляется в Phase 5 (Commit) через `update_symbolic()`
- ✅ TraceMemory сохраняет траектории в `learn_success()`
- ❌ **НО**: Phase 3 (Reason) не использует активированные гены RLD для генерации кода
- ❌ **НО**: Semantic graph из DSM не передается в LLM промпт
- ❌ **НО**: TraceMemory не предлагает похожие решения перед генерацией

**Код**:
```python
# agent/core.py:1063 - Phase 2 (Recall)
state.memory_context = await asyncio.to_thread(memory.recall, state.task)

# agent/core.py:1081-1386 - Phase 3 (Reason)
# ❌ memory_context загружен, но НЕ используется в LLM промпте!
# ❌ Activated RLD genes не влияют на генерацию
# ❌ Semantic graph не анализируется
```

**Impact**: Агент не учится на прошлых решениях, каждый раз начинает с нуля

---

### 2. **Phase 3 (Reason) генерирует код без достаточного контекста**
**Проблема**: LLM получает только workspace summary, но не получает:
- Активированные reasoning genes из RLD
- Semantic graph связей между файлами
- Dependency analysis (circular deps, complexity)
- Похожие решения из TraceMemory

**Текущий промпт** (agent/core.py:1200-1250):
```python
prompt = f"""TASK: {state.task}

WORKSPACE:
{state.workspace_summary[:8000]}

MEMORY CONTEXT:
{state.memory_context[:4000]}  # ❌ Обрезается до 4000 символов!

Generate files to solve this task."""
```

**Что не хватает**:
1. RLD genes с примерами успешных решений
2. Semantic graph для понимания архитектуры
3. Dependency analysis для избежания circular deps
4. TraceMemory с похожими задачами

**Impact**: Агент генерирует код "вслепую", без понимания архитектуры проекта

---

### 3. **Нет self-correction loop**
**Проблема**: Если Phase 4 (Stabilize) находит ошибки, агент просто логирует их и завершается

**Текущее поведение** (agent/core.py:1389-1532):
```python
async def _stabilize(...):
    test_result = await run_pytest(state.workspace)
    if test_result.failed > 0:
        yield self._log("error", f"{test_result.failed} tests failed")
        # ❌ Агент НЕ пытается исправить ошибки!
        # ❌ Просто переходит к Phase 5 (Commit)
```

**Что должно быть**:
1. Анализ ошибок через FailureAnalyzer
2. Автоматический retry Phase 3 с контекстом ошибки
3. Максимум 3 попытки исправления
4. Обучение на ошибках (сохранение в RLD как negative examples)

**Impact**: Агент не исправляет свои ошибки, требует ручного вмешательства

---

### 4. **Планирование задач не используется эффективно**
**Проблема**: HierarchicalPlanner генерирует план, но агент не следует ему

**Текущее поведение** (agent/core.py:1098-1132):
```python
# Генерируется план с task_graph
task_graph = await asyncio.to_thread(planner.plan, state.task, context)

# ❌ План отправляется на frontend, но НЕ используется для execution!
yield {"type": "task_plan", "plan": plan_data}

# Агент сразу переходит к генерации всех файлов одним промптом
```

**Что должно быть**:
1. Разбить задачу на подзадачи через HierarchicalPlanner
2. Выполнять подзадачи последовательно (одна за другой)
3. Каждая подзадача = отдельная итерация Phase 3 → Phase 4
4. Прогресс-трекинг через ProgressTracker
5. Адаптивное переplanирование при ошибках

**Impact**: Агент пытается решить всю задачу за один раз, что приводит к ошибкам

---

### 5. **Semantic Graph и Dependency Analysis не используются**
**Проблема**: Код анализируется (semantic_graph.py, dependency.py), но результаты не передаются в LLM

**Текущее состояние**:
- ✅ SemanticGraph строится в Phase 1 (Observe)
- ✅ DependencyAnalyzer находит circular deps
- ❌ **НО**: Эта информация НЕ используется в Phase 3 (Reason)

**Что должно быть**:
```python
# В Phase 3 (Reason) промпт должен включать:
SEMANTIC GRAPH:
- Module: agent/core.py
  - Class: SharrowkinAgent
    - Method: run() [complexity: 45]
    - Method: _observe() [complexity: 12]
  - Dependencies: memory.bridge, core.tools, analysis.code.semantic_graph

CIRCULAR DEPENDENCIES DETECTED:
- memory.rld.core → memory.dsm.core.memory → memory.rld.core

COMPLEXITY HOTSPOTS:
- agent/core.py:run() - cyclomatic complexity 45 (high risk)
```

**Impact**: Агент не понимает архитектуру проекта, генерирует код с конфликтами

---

## 🎯 План улучшений (Priority Order)

### **Phase 1: Исправить интеграцию памяти** (2-3 часа)
**Цель**: DSM, RLD, MemoryField, TraceMemory должны активно влиять на генерацию кода

**Задачи**:
1. ✅ Добавить RLD genes в LLM промпт (Phase 3)
2. ✅ Добавить TraceMemory похожие решения в промпт
3. ✅ Увеличить лимит memory_context с 4000 до 12000 символов
4. ✅ Добавить MemoryField attractors в промпт для выбора стратегии

**Изменения**:
- `agent/core.py:_reason()` - расширить промпт
- `memory/bridge.py:recall()` - вернуть structured context вместо plain text

**Критерий успеха**: Агент использует прошлые решения для генерации кода

---

### **Phase 2: Добавить self-correction loop** (3-4 часа)
**Цель**: Агент автоматически исправляет ошибки без ручного вмешательства

**Задачи**:
1. ✅ Добавить retry logic в Phase 4 (Stabilize)
2. ✅ Интегрировать FailureAnalyzer для анализа ошибок
3. ✅ Передавать контекст ошибки в Phase 3 для исправления
4. ✅ Ограничить максимум 3 попытки
5. ✅ Сохранять failed attempts в RLD как negative examples

**Изменения**:
- `agent/core.py:_stabilize()` - добавить retry loop
- `agent/core.py:_reason()` - принимать error_context параметр
- `agent/failure_analyzer.py` - расширить анализ ошибок

**Критерий успеха**: Агент исправляет 80%+ ошибок автоматически

---

### **Phase 3: Улучшить планирование задач** (4-5 часов)
**Цель**: Агент разбивает сложные задачи на подзадачи и выполняет их последовательно

**Задачи**:
1. ✅ Интегрировать HierarchicalPlanner в execution loop
2. ✅ Выполнять подзадачи последовательно (одна за другой)
3. ✅ Добавить ProgressTracker для отслеживания прогресса
4. ✅ Адаптивное переplanирование при ошибках
5. ✅ Сохранять успешные планы в RLD

**Изменения**:
- `agent/core.py:run()` - добавить task decomposition loop
- `planning/planner.py` - улучшить декомпозицию
- `planning/tracker.py` - добавить real-time tracking

**Критерий успеха**: Агент успешно выполняет задачи из 5+ шагов

---

### **Phase 4: Интегрировать Semantic Graph в генерацию** (2-3 часа)
**Цель**: Агент понимает архитектуру проекта перед генерацией кода

**Задачи**:
1. ✅ Передавать SemanticGraph в LLM промпт
2. ✅ Передавать DependencyAnalysis (circular deps, complexity)
3. ✅ Добавить code hotspots (high complexity functions)
4. ✅ Добавить architectural patterns (Singleton, Factory, etc.)

**Изменения**:
- `agent/core.py:_reason()` - добавить semantic context в промпт
- `analysis/code/semantic_graph.py` - добавить метод `to_prompt_context()`

**Критерий успеха**: Агент избегает circular deps и architectural conflicts

---

### **Phase 5: Добавить multi-step reasoning** (3-4 часа)
**Цель**: Агент рассуждает пошагово, а не генерирует весь код сразу

**Задачи**:
1. ✅ Добавить "thinking" фазу перед генерацией
2. ✅ LLM сначала генерирует план действий
3. ✅ Затем генерирует код по частям (файл за файлом)
4. ✅ Проверяет каждый файл перед переходом к следующему

**Изменения**:
- `agent/core.py:_reason()` - разбить на sub-phases: Think → Plan → Generate → Verify
- `core/llm/client.py` - добавить streaming generation

**Критерий успеха**: Агент генерирует код пошагово с промежуточной валидацией

---

### **Phase 6: Улучшить LLM промпты** (2-3 часа)
**Цель**: Промпты должны быть структурированными и информативными

**Задачи**:
1. ✅ Добавить few-shot examples из TraceMemory
2. ✅ Добавить architectural constraints
3. ✅ Добавить code style guidelines из проекта
4. ✅ Добавить error prevention hints

**Изменения**:
- `agent/core.py:_reason()` - улучшить структуру промпта
- `memory/bridge.py:recall()` - вернуть structured examples

**Критерий успеха**: Качество генерируемого кода улучшается на 50%+

---

## 📊 Метрики успеха

**Текущее состояние** (baseline):
- ✅ Phase 1-2 работают (Observe, Recall)
- ⚠️ Phase 3 генерирует код, но без контекста
- ❌ Phase 4 не исправляет ошибки
- ❌ Phase 5 сохраняет в память, но не учится

**Целевое состояние** (ideal):
- ✅ Агент разбивает задачу на подзадачи
- ✅ Выполняет подзадачи последовательно
- ✅ Использует прошлые решения из памяти
- ✅ Автоматически исправляет ошибки (3 попытки)
- ✅ Понимает архитектуру проекта
- ✅ Генерирует код пошагово с валидацией
- ✅ Учится на успехах и ошибках

**KPI**:
- Success rate: 30% → 85%+
- Self-correction rate: 0% → 80%+
- Memory utilization: 20% → 90%+
- Task completion time: -40% (за счет планирования)

---

## 🚀 Начинаем с Phase 1

**Следующий шаг**: Исправить интеграцию памяти в Phase 3 (Reason)

**Файлы для изменения**:
1. `agent/core.py:_reason()` - расширить LLM промпт
2. `memory/bridge.py:recall()` - вернуть structured context

**Время**: ~2-3 часа  
**Приоритет**: CRITICAL
