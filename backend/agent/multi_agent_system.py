"""Hierarchical Swarm Multi-Agent System - лучше чем у Devin."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Any

from backend.memory import MemoryBridge


class AgentRole(Enum):
    """Роли агентов в системе."""
    COORDINATOR = "coordinator"  # Планирует и координирует
    ARCHITECT = "architect"      # Проектирует архитектуру
    BACKEND = "backend"          # Backend код
    FRONTEND = "frontend"        # Frontend код
    QA = "qa"                    # Тестирование
    DEVOPS = "devops"           # CI/CD, deployment
    SECURITY = "security"        # Security audit


@dataclass
class AgentTask:
    """Задача для агента."""
    id: str
    role: AgentRole
    description: str
    dependencies: list[str] = field(default_factory=list)  # ID задач от которых зависит
    priority: int = 0  # 0 = highest
    status: str = "pending"  # pending, running, done, failed
    result: Any = None
    agent_id: str | None = None


@dataclass
class SwarmMessage:
    """Сообщение между агентами в рое."""
    from_agent: str
    to_agent: str | None  # None = broadcast
    message_type: str  # discovery, warning, solution, question
    content: str
    metadata: dict = field(default_factory=dict)


class SpecialistAgent:
    """Специализированный агент."""

    def __init__(self, role: AgentRole, agent_id: str, memory: MemoryBridge):
        self.role = role
        self.agent_id = agent_id
        self.memory = memory
        self.inbox: list[SwarmMessage] = []
        self.discoveries: list[str] = []  # Что нашёл агент

    async def execute_task(self, task: AgentTask) -> AsyncIterator[dict]:
        """Выполнить задачу."""
        yield {
            "type": "agent_start",
            "agent_id": self.agent_id,
            "role": self.role.value,
            "task_id": task.id,
            "description": task.description
        }

        # Специализированная логика в зависимости от роли
        if self.role == AgentRole.ARCHITECT:
            async for event in self._architect_work(task):
                yield event
        elif self.role == AgentRole.BACKEND:
            async for event in self._backend_work(task):
                yield event
        elif self.role == AgentRole.FRONTEND:
            async for event in self._frontend_work(task):
                yield event
        elif self.role == AgentRole.QA:
            async for event in self._qa_work(task):
                yield event
        elif self.role == AgentRole.DEVOPS:
            async for event in self._devops_work(task):
                yield event
        elif self.role == AgentRole.SECURITY:
            async for event in self._security_work(task):
                yield event

        yield {
            "type": "agent_complete",
            "agent_id": self.agent_id,
            "task_id": task.id,
            "discoveries": self.discoveries
        }

    async def _architect_work(self, task: AgentTask) -> AsyncIterator[dict]:
        """Работа архитектора - проектирование системы."""
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Analyzing architecture..."}

        # 1. Анализ существующей архитектуры
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Reading codebase structure..."}

        # 2. Проектирование новой архитектуры
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Designing solution architecture..."}

        # 3. Создание плана для других агентов
        architecture_plan = {
            "backend_tasks": ["Create API endpoints", "Add database models"],
            "frontend_tasks": ["Create UI components", "Add routing"],
            "qa_tasks": ["Write unit tests", "Write integration tests"]
        }

        self.discoveries.append(f"Architecture plan created: {len(architecture_plan)} task groups")
        task.result = architecture_plan

    async def _backend_work(self, task: AgentTask) -> AsyncIterator[dict]:
        """Работа backend разработчика."""
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Working on backend task: {task.description}"}

        # Broadcast находку другим агентам
        discovery = f"Found API endpoint pattern in {task.description}"
        self.discoveries.append(discovery)

        yield {
            "type": "swarm_message",
            "from_agent": self.agent_id,
            "message_type": "discovery",
            "content": discovery
        }

    async def _frontend_work(self, task: AgentTask) -> AsyncIterator[dict]:
        """Работа frontend разработчика."""
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Working on frontend task: {task.description}"}

    async def _qa_work(self, task: AgentTask) -> AsyncIterator[dict]:
        """Работа QA инженера."""
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Writing tests for: {task.description}"}

    async def _devops_work(self, task: AgentTask) -> AsyncIterator[dict]:
        """Работа DevOps инженера."""
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Setting up CI/CD for: {task.description}"}

    async def _security_work(self, task: AgentTask) -> AsyncIterator[dict]:
        """Работа Security специалиста."""
        yield {"type": "log", "level": "info", "message": f"[{self.agent_id}] Security audit: {task.description}"}

        # Проверка на уязвимости
        vulnerabilities = []
        if "password" in task.description.lower() and "hash" not in task.description.lower():
            vulnerabilities.append("WARNING: Password should be hashed")

        if vulnerabilities:
            yield {
                "type": "swarm_message",
                "from_agent": self.agent_id,
                "message_type": "warning",
                "content": f"Security issues found: {', '.join(vulnerabilities)}"
            }


class CoordinatorAgent:
    """Координатор - главный агент который управляет роем."""

    def __init__(self, workspace: Path, memory: MemoryBridge):
        self.workspace = workspace
        self.memory = memory
        self.specialists: dict[AgentRole, SpecialistAgent] = {}
        self.tasks: dict[str, AgentTask] = {}
        self.swarm_messages: list[SwarmMessage] = []

        # Создаём специалистов
        for role in [AgentRole.ARCHITECT, AgentRole.BACKEND, AgentRole.FRONTEND,
                     AgentRole.QA, AgentRole.DEVOPS, AgentRole.SECURITY]:
            agent_id = f"{role.value}_agent"
            self.specialists[role] = SpecialistAgent(role, agent_id, memory)

    async def execute(self, user_task: str) -> AsyncIterator[dict]:
        """Главный метод - координация всей работы."""

        yield {
            "type": "coordinator_start",
            "message": "Coordinator analyzing task and creating execution plan..."
        }

        # 1. Декомпозиция задачи на подзадачи
        subtasks = await self._decompose_task(user_task)

        yield {
            "type": "task_decomposition",
            "total_tasks": len(subtasks),
            "tasks": [{"id": t.id, "role": t.role.value, "description": t.description} for t in subtasks]
        }

        # 2. Построение графа зависимостей
        task_graph = self._build_dependency_graph(subtasks)

        yield {
            "type": "dependency_graph",
            "graph": task_graph
        }

        # 3. Параллельное выполнение задач с учётом зависимостей
        async for event in self._execute_parallel(subtasks):
            yield event

        # 4. Сбор результатов и финальная интеграция
        yield {
            "type": "coordinator_complete",
            "message": "All agents completed their tasks. Integrating results..."
        }

    async def _decompose_task(self, user_task: str) -> list[AgentTask]:
        """Декомпозиция задачи на подзадачи для специалистов."""

        # Простая эвристика (в реальности - через LLM)
        subtasks = []

        # Всегда начинаем с архитектора
        subtasks.append(AgentTask(
            id="task_1",
            role=AgentRole.ARCHITECT,
            description=f"Design architecture for: {user_task}",
            priority=0
        ))

        # Определяем какие специалисты нужны
        if "api" in user_task.lower() or "backend" in user_task.lower():
            subtasks.append(AgentTask(
                id="task_2",
                role=AgentRole.BACKEND,
                description=f"Implement backend for: {user_task}",
                dependencies=["task_1"],
                priority=1
            ))

        if "ui" in user_task.lower() or "frontend" in user_task.lower():
            subtasks.append(AgentTask(
                id="task_3",
                role=AgentRole.FRONTEND,
                description=f"Implement frontend for: {user_task}",
                dependencies=["task_1"],
                priority=1
            ))

        # QA всегда нужен
        subtasks.append(AgentTask(
            id="task_4",
            role=AgentRole.QA,
            description=f"Write tests for: {user_task}",
            dependencies=["task_2", "task_3"] if len(subtasks) > 1 else ["task_1"],
            priority=2
        ))

        # Security audit
        subtasks.append(AgentTask(
            id="task_5",
            role=AgentRole.SECURITY,
            description=f"Security audit for: {user_task}",
            dependencies=["task_2", "task_3"] if len(subtasks) > 2 else ["task_1"],
            priority=2
        ))

        return subtasks

    def _build_dependency_graph(self, tasks: list[AgentTask]) -> dict:
        """Построение графа зависимостей."""
        graph = {}
        for task in tasks:
            graph[task.id] = {
                "role": task.role.value,
                "dependencies": task.dependencies,
                "priority": task.priority
            }
        return graph

    async def _execute_parallel(self, tasks: list[AgentTask]) -> AsyncIterator[dict]:
        """Параллельное выполнение задач с учётом зависимостей."""

        completed_tasks = set()
        running_tasks = {}

        while len(completed_tasks) < len(tasks):
            # Найти задачи готовые к выполнению
            ready_tasks = [
                t for t in tasks
                if t.id not in completed_tasks
                and t.id not in running_tasks
                and all(dep in completed_tasks for dep in t.dependencies)
            ]

            # Запустить готовые задачи параллельно
            for task in ready_tasks:
                specialist = self.specialists[task.role]
                task.status = "running"
                task.agent_id = specialist.agent_id

                # Запускаем в фоне
                running_tasks[task.id] = asyncio.create_task(
                    self._run_task(specialist, task)
                )

                yield {
                    "type": "task_started",
                    "task_id": task.id,
                    "agent_id": specialist.agent_id,
                    "role": task.role.value
                }

            # Ждём завершения хотя бы одной задачи
            if running_tasks:
                done, pending = await asyncio.wait(
                    running_tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED
                )

                for task_future in done:
                    task_id = [tid for tid, fut in running_tasks.items() if fut == task_future][0]
                    completed_tasks.add(task_id)
                    del running_tasks[task_id]

                    yield {
                        "type": "task_completed",
                        "task_id": task_id
                    }
            else:
                # Нет готовых задач - ждём
                await asyncio.sleep(0.1)

    async def _run_task(self, specialist: SpecialistAgent, task: AgentTask):
        """Запустить задачу у специалиста."""
        async for event in specialist.execute_task(task):
            # События от агента (можно обрабатывать)
            pass
        task.status = "done"


# Главная функция для использования
async def run_multi_agent_system(user_task: str, workspace: Path, memory: MemoryBridge) -> AsyncIterator[dict]:
    """Запустить мульти-агентную систему."""

    coordinator = CoordinatorAgent(workspace, memory)

    async for event in coordinator.execute(user_task):
        yield event
