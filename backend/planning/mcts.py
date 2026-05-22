"""Monte Carlo Tree Search for task planning.

MCTS explores possible task decompositions and selects the most promising path.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MCTSNode:
    """Node in the MCTS tree representing a task state."""

    task: str
    parent: Optional[MCTSNode] = None
    children: List[MCTSNode] = field(default_factory=list)

    # MCTS statistics
    visits: int = 0
    value: float = 0.0

    # Task metadata
    is_terminal: bool = False
    is_expanded: bool = False
    subtasks: List[str] = field(default_factory=list)

    def ucb1(self, exploration_weight: float = 1.414) -> float:
        """Upper Confidence Bound for Trees (UCB1) score.

        Balances exploitation (high value) vs exploration (low visits).
        """
        if self.visits == 0:
            return float('inf')

        if self.parent is None:
            return self.value / self.visits

        exploitation = self.value / self.visits
        exploration = exploration_weight * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )
        return exploitation + exploration

    def best_child(self, exploration_weight: float = 1.414) -> MCTSNode:
        """Select child with highest UCB1 score."""
        return max(self.children, key=lambda c: c.ucb1(exploration_weight))

    def add_child(self, task: str) -> MCTSNode:
        """Add a child node for a subtask."""
        child = MCTSNode(task=task, parent=self)
        self.children.append(child)
        return child


class MCTSPlanner:
    """Monte Carlo Tree Search planner for task decomposition."""

    def __init__(
        self,
        max_iterations: int = 100,
        exploration_weight: float = 1.414,
        max_depth: int = 5,
    ):
        self.max_iterations = max_iterations
        self.exploration_weight = exploration_weight
        self.max_depth = max_depth

    def plan(self, root_task: str, decompose_fn, evaluate_fn) -> List[str]:
        """Run MCTS to find optimal task decomposition.

        Args:
            root_task: The main task to decompose
            decompose_fn: Function that takes a task and returns list of subtasks
            evaluate_fn: Function that takes a task path and returns quality score (0-1)

        Returns:
            List of subtasks in optimal order
        """
        root = MCTSNode(task=root_task)

        for iteration in range(self.max_iterations):
            # 1. Selection: traverse tree using UCB1
            node = self._select(root)

            # 2. Expansion: add children if not terminal
            if not node.is_terminal and not node.is_expanded:
                node = self._expand(node, decompose_fn)

            # 3. Simulation: rollout to terminal state
            reward = self._simulate(node, decompose_fn, evaluate_fn)

            # 4. Backpropagation: update statistics
            self._backpropagate(node, reward)

        # Extract best path from root to leaf
        return self._extract_best_path(root)

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Select a leaf node using UCB1."""
        current = node
        depth = 0

        while current.children and depth < self.max_depth:
            current = current.best_child(self.exploration_weight)
            depth += 1

        return current

    def _expand(self, node: MCTSNode, decompose_fn) -> MCTSNode:
        """Expand node by generating subtasks."""
        subtasks = decompose_fn(node.task)

        if not subtasks:
            node.is_terminal = True
            return node

        node.subtasks = subtasks
        node.is_expanded = True

        # Add children for each subtask
        for subtask in subtasks:
            node.add_child(subtask)

        # Return random child for simulation
        return random.choice(node.children) if node.children else node

    def _simulate(self, node: MCTSNode, decompose_fn, evaluate_fn) -> float:
        """Simulate random rollout from node to terminal state."""
        path = self._get_path_to_root(node)

        # Random rollout
        current_task = node.task
        depth = 0

        while depth < self.max_depth:
            subtasks = decompose_fn(current_task)
            if not subtasks:
                break

            current_task = random.choice(subtasks)
            path.append(current_task)
            depth += 1

        # Evaluate the path
        return evaluate_fn(path)

    def _backpropagate(self, node: MCTSNode, reward: float):
        """Update statistics from node to root."""
        current = node

        while current is not None:
            current.visits += 1
            current.value += reward
            current = current.parent

    def _get_path_to_root(self, node: MCTSNode) -> List[str]:
        """Get path from root to node."""
        path = []
        current = node

        while current is not None:
            path.insert(0, current.task)
            current = current.parent

        return path

    def _extract_best_path(self, root: MCTSNode) -> List[str]:
        """Extract best path from root using visit counts."""
        path = []
        current = root

        while current.children:
            # Select child with most visits (most promising)
            current = max(current.children, key=lambda c: c.visits)
            path.append(current.task)

        return path


def simple_decompose(task: str) -> List[str]:
    """Simple task decomposition for testing.

    In production, this would use LLM to decompose tasks.
    """
    task_lower = task.lower()

    if "create" in task_lower or "add" in task_lower:
        return [
            f"Design {task}",
            f"Implement {task}",
            f"Test {task}",
        ]
    elif "fix" in task_lower or "bug" in task_lower:
        return [
            f"Reproduce {task}",
            f"Diagnose {task}",
            f"Fix {task}",
            f"Verify {task}",
        ]
    elif "refactor" in task_lower:
        return [
            f"Analyze {task}",
            f"Plan {task}",
            f"Execute {task}",
            f"Validate {task}",
        ]

    # Terminal task
    return []


def simple_evaluate(path: List[str]) -> float:
    """Simple path evaluation for testing.

    In production, this would use heuristics or learned model.
    """
    # Prefer shorter paths
    length_score = 1.0 / (1.0 + len(path) * 0.1)

    # Prefer paths with test/verify steps
    has_test = any("test" in task.lower() or "verify" in task.lower() for task in path)
    test_score = 0.2 if has_test else 0.0

    return length_score + test_score


if __name__ == "__main__":
    # Test MCTS planner
    planner = MCTSPlanner(max_iterations=50)

    task = "Add user authentication"
    plan = planner.plan(task, simple_decompose, simple_evaluate)

    print(f"Task: {task}")
    print(f"Plan: {plan}")
