import sys
import os

# Добавляем путь к модулям, чтобы Python их видел
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from rld.models import ReasoningTrajectory, ReasoningGene, GeneStats, now_ts

def test_rld_foundations():
    print("RLD foundation models test...")
    
    # 1. Test Trajectory
    traj = ReasoningTrajectory(
        task="Solve x + 5 = 10",
        states=["Start", "Move 5", "Result"],
        actions=["subtract_5", "calculate"],
        final_answer="x = 5",
        tools_used=["calculator"]
    )
    print(f"OK: Trajectory created: {traj.id}")
    assert "Task: Solve" in traj.text()
    
    # 2. Test Stats
    stats = GeneStats()
    stats.record_activation(success=True, utility=0.9)
    stats.record_activation(success=True, utility=0.8)
    stats.record_activation(success=False, utility=0.1)
    
    score = stats.activation_score()
    print(f"OK: Stats calculated. Success Rate: {stats.success_rate:.2f}, Activation Score: {score:.4f}")
    assert stats.reuse_count == 3
    assert score > 0
    
    # 3. Test Gene
    gene = ReasoningGene(
        task_context="First-order algebraic equations",
        transformation_delta="Variable isolation via constant movement",
        reasoning_steps=["Find constant", "Change sign", "Move to right side"],
        solution_schema="x = B - A",
        trigger_terms=["equation", "x", "plus", "minus"],
        embedding=[0.1] * 1536,
        stats=stats
    )
    print(f"OK: Gene created: {gene.id}")
    print(f"Memory Text Preview:\n{gene.memory_text()[:100]}...")
    
    # 4. Test serialization
    data = gene.to_dict()
    new_gene = ReasoningGene.from_dict(data)
    assert new_gene.id == gene.id
    print("OK: Serialization/Deserialization: OK")

if __name__ == "__main__":
    try:
        test_rld_foundations()
        print("\nTEST PASSED: RLD data models are stable!")
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()
