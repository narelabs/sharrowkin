"""Example demonstrating Phase 1 capabilities: Hierarchical Planning and Code Analysis.

This example shows how to use the new planning and code analysis modules
to decompose tasks and understand codebase structure.
"""

from pathlib import Path

from planning import HierarchicalPlanner, PlanningContext, ProgressTracker
from analysis import DependencyAnalyzer, SemanticGraph, SemanticGraphBuilder


def demo_hierarchical_planning():
    """Demonstrate hierarchical task planning."""
    print("=" * 60)
    print("DEMO: Hierarchical Task Planning")
    print("=" * 60)

    # Create planner
    planner = HierarchicalPlanner()

    # Define a complex goal
    goal = "Implement user authentication system"
    context = PlanningContext(
        goal=goal,
        workspace_path=Path("."),
        available_tools=["read_file", "write_file", "run_tests"],
        constraints={"max_duration_hours": 8},
    )

    # Create plan
    print(f"\nGoal: {goal}")
    print("\nGenerating hierarchical plan...")
    task_graph = planner.plan(goal, context)

    # Visualize the plan
    print("\n" + task_graph.visualize())

    # Show execution order
    print("\nExecution Order (by level):")
    for level_idx, level in enumerate(task_graph.get_execution_order()):
        print(f"\nLevel {level_idx + 1} (can run in parallel):")
        for task_id in level:
            task = task_graph.get_task(task_id)
            if task:
                print(f"  - {task.title}")

    # Show critical path
    print("\nCritical Path:")
    for task_id in task_graph.get_critical_path():
        task = task_graph.get_task(task_id)
        if task:
            est = task.estimated_duration_seconds or 0
            print(f"  → {task.title} ({est/60:.1f} min)")

    # Show statistics
    print("\nPlan Statistics:")
    stats = task_graph.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")


def demo_progress_tracking():
    """Demonstrate progress tracking."""
    print("\n" + "=" * 60)
    print("DEMO: Progress Tracking")
    print("=" * 60)

    # Create a simple task graph
    from planning import TaskGraph, Task, TaskStatus, TaskPriority

    graph = TaskGraph()

    # Add some tasks
    task1 = Task(title="Task 1", priority=TaskPriority.HIGH, estimated_duration_seconds=300)
    task2 = Task(title="Task 2", priority=TaskPriority.NORMAL, estimated_duration_seconds=600)
    task3 = Task(title="Task 3", priority=TaskPriority.NORMAL, estimated_duration_seconds=450)

    graph.add_task(task1)
    graph.add_task(task2)
    graph.add_task(task3)

    # Add dependencies
    graph.add_dependency(task2.id, task1.id)
    graph.add_dependency(task3.id, task1.id)

    # Create progress tracker
    tracker = ProgressTracker(graph)
    tracker.start()

    # Simulate task execution
    print("\nSimulating task execution...")

    # Complete task 1
    task1.mark_started()
    task1.mark_completed()
    tracker.on_task_completed(task1.id)
    print("\n" + tracker.get_progress_summary())

    # Start task 2 and 3 in parallel
    task2.mark_started()
    task3.mark_started()
    print("\n" + tracker.get_progress_bar())

    # Complete task 2
    task2.mark_completed()
    tracker.on_task_completed(task2.id)
    print("\n" + tracker.get_progress_summary())


def demo_dependency_analysis():
    """Demonstrate dependency analysis."""
    print("\n" + "=" * 60)
    print("DEMO: Dependency Analysis")
    print("=" * 60)

    # Analyze the planning module itself
    analyzer = DependencyAnalyzer()

    planning_dir = Path(__file__).parent.parent / "backend" / "planning"
    if planning_dir.exists():
        print(f"\nAnalyzing directory: {planning_dir}")
        analyzer.analyze_directory(planning_dir, recursive=False)

        graph = analyzer.get_graph()
        print(f"\nFound {len(graph.nodes)} code entities")
        print(f"Found {len(graph.dependencies)} dependencies")

        # Show module dependencies
        print("\nModule Dependencies:")
        print(graph.visualize())

        # Check for circular dependencies
        cycles = graph.get_circular_dependencies()
        if cycles:
            print("\n⚠️  Circular dependencies detected:")
            for cycle in cycles:
                print(f"  {' → '.join(cycle)}")
        else:
            print("\n✓ No circular dependencies found")


def demo_semantic_graph():
    """Demonstrate semantic graph building."""
    print("\n" + "=" * 60)
    print("DEMO: Semantic Code Graph")
    print("=" * 60)

    # Build semantic graph
    semantic_graph = SemanticGraph()
    builder = SemanticGraphBuilder(semantic_graph)

    planning_dir = Path(__file__).parent.parent / "backend" / "planning"
    if planning_dir.exists():
        print(f"\nBuilding semantic graph from: {planning_dir}")
        builder.build_from_directory(planning_dir, recursive=False)

        print(f"\nFound {len(semantic_graph.nodes)} code entities")

        # Show modules
        print("\nModules:")
        for module in semantic_graph.get_modules():
            print(f"  📦 {module.name}")

        # Show classes
        print("\nClasses:")
        for cls in semantic_graph.get_classes():
            print(f"  🏛️  {cls.name} (in {cls.parent_id})")

        # Show functions
        print("\nFunctions:")
        for func in semantic_graph.get_functions()[:10]:  # First 10
            complexity_info = f" [complexity: {func.complexity}]" if func.complexity > 0 else ""
            print(f"  🔧 {func.name}{complexity_info}")

        # Calculate complexity metrics
        print("\nComplexity Metrics:")
        metrics = semantic_graph.calculate_complexity_metrics()
        print(f"  Total nodes: {metrics['total_nodes']}")
        print(f"  Total functions: {metrics['total_functions']}")
        print(f"  Average complexity: {metrics['average_complexity']:.2f}")

        if metrics['most_complex']:
            print("\n  Most complex functions:")
            for func in metrics['most_complex'][:5]:
                print(f"    - {func['id']} (complexity: {func['complexity']})")

        # Visualize a module
        modules = semantic_graph.get_modules()
        if modules:
            print(f"\nVisualization of {modules[0].name}:")
            print(semantic_graph.visualize(modules[0].id, max_depth=2))


def main():
    """Run all demos."""
    print("\n🚀 Phase 1 Implementation Demo")
    print("Sharrowkin → Devin Level Agent")
    print("\n")

    try:
        demo_hierarchical_planning()
    except Exception as e:
        print(f"\n❌ Hierarchical planning demo failed: {e}")

    try:
        demo_progress_tracking()
    except Exception as e:
        print(f"\n❌ Progress tracking demo failed: {e}")

    try:
        demo_dependency_analysis()
    except Exception as e:
        print(f"\n❌ Dependency analysis demo failed: {e}")

    try:
        demo_semantic_graph()
    except Exception as e:
        print(f"\n❌ Semantic graph demo failed: {e}")

    print("\n" + "=" * 60)
    print("✅ Phase 1 Demo Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Integrate with existing Sharrowkin agent")
    print("  2. Connect to RLD for pattern storage")
    print("  3. Connect to DSM for semantic graph storage")
    print("  4. Begin Phase 2: Debugging capabilities")


if __name__ == "__main__":
    main()
