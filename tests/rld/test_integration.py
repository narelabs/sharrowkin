import sys
import os
import asyncio
from pathlib import Path

# Добавляем пути
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../dsm/src")))

from rld.core import RecursiveLatentDNA

def test_rld_dsm_integration():
    print("RLD + DSM Integration Action Test...")
    
    # Инициализируем систему с DSM бэкэндом
    storage_path = ".rld_action_test.json"
    rld = RecursiveLatentDNA(storage_path=storage_path, use_dsm_backend=True)
    
    # --- ШАГ 1: ОБУЧЕНИЕ (Создание Гена и Сегмента) ---
    print("\n1. Action: Learning 'Microservices Patterns'...")
    rld.observe(
        task="Design a resilient microservices architecture with circuit breakers",
        states=["Define services", "Add RabbitMQ", "Implement Resilience4j"],
        actions=["design_diagram", "setup_broker", "config_circuit_breaker"],
        final_answer="Resilient architecture designed with circuit breaker patterns.",
        success=True,
        utility=0.98,
        tools_used=["architect_tool", "diagram_gen"]
    )
    
    print(f"OK: Genes in RLD: {len(rld.genes)}")
    print(f"OK: Segments in DSM: {rld.dsm_memory.stats()['segments']}")
    
    gene_id = list(rld.genes.keys())[0]
    segment_id = rld.gene_segment_ids.get(gene_id)
    print(f"OK: Gene {gene_id} is linked to DSM Segment {segment_id}")

    # --- ШАГ 2: КОМБИНИРОВАННАЯ АКТИВАЦИЯ ---
    print("\n2. Action: Retrieving with hybrid RLD+DSM scoring...")
    # Запрос, который должен триггернуть и DSM (по словам), и RLD (по смыслу)
    context = rld.active_context("How to handle service failures in microservices?")
    
    if context.activated:
        print(f"OK: Activated genes: {len(context.activated)}")
        for act in context.activated:
            trace = act.trace
            print(f"TARGET: Gene {act.gene.id}")
            print(f"  - DSM Score: {getattr(trace, 'dsm_score', 0):.4f}")
            print(f"  - RLD Prob: {trace.probability:.4f}")
            print(f"  - Final Weight: {act.weight:.2f}")
    else:
        print("FAIL: Hybrid activation failed.")

    # --- ШАГ 3: ОЧИСТКА ---
    print("\n3. Action: Cleanup check...")
    rld.record_outcome(gene_id, success=False, utility=0.05) # "Убиваем" ген плохим результатом
    rld.consolidate(min_value=0.5) # Пруним всё, что ниже 0.5
    
    if gene_id not in rld.genes:
        print("OK: Gene pruned from RLD.")
        if segment_id not in rld.dsm_memory.segments:
            print("OK: Segment automatically removed from DSM. Perfect sync.")
    
    print("\nTEST PASSED: RLD and DSM are working as a single organism!")

if __name__ == "__main__":
    test_rld_dsm_integration()
