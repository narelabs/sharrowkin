import sys
from pathlib import Path

from memory.dsm.core.memory import DynamicSegmentedMemory

def run_lexical_stress_test():
    print("--- СТРЕСС-ТЕСТ ЛЕКСИЧЕСКОГО ПОИСКА DSM 3.0 ---")
    
    # Инициализируем DSM
    dsm = DynamicSegmentedMemory(decay_rate=0.1)
    
    # Добавляем пачку разных сегментов кода
    print("[1] Индексируем базу знаний...")
    dsm.add_memory("def get_user_data(id): return db.fetch(id)", metadata={"type": "db"})
    dsm.add_memory("def calculate_rocket_trajectory(mass, fuel): pass", metadata={"type": "physics"})
    dsm.add_memory("import torch; model = torch.nn.Sequential()", metadata={"type": "ml"})
    target_id = dsm.add_memory("def deep_space_telemetry_decode(packet): return packet.strip()", metadata={"type": "comm"})
    dsm.add_memory("from flask import Flask; app = Flask(__name__)", metadata={"type": "web"})

    print(f"  -> Проиндексировано сегментов: {len(dsm.hot_memory)}")
    
    # Состарим целевой сегмент
    print(f"[2] Состариваем целевой сегмент (telemetry)...")
    dsm.hot_memory[target_id].last_accessed -= 10000 # Остыл
    dsm.thermodynamics.apply_decay(dsm.hot_memory)
    print(f"  -> Heat перед поиском: {dsm.hot_memory[target_id].heat:.4f}")
    
    # Выполняем поиск по уникальному слову
    print(f"[3] Ищем по ключевому слову 'telemetry'...")
    results = dsm.search(query="telemetry", top_k=1)
    
    if results:
        found_seg, score = results[0]
        print(f"  -> НАЙДЕНО: '{found_seg.content}'")
        print(f"  -> Score (RRF * Heat): {score:.6f}")
        
        if found_seg.id == target_id:
            print("  -> УСПЕХ: Лексический поиск BM25 точно определил нужный сегмент!")
        
        print(f"  -> Текущий Heat после поиска: {found_seg.heat}")
        if found_seg.heat == 1.0:
            print("  -> УСПЕХ: Сегмент мгновенно разогрет до 1.0 (Консолидация)!")
    else:
        print("  -> ОШИБКА: Ничего не найдено.")

if __name__ == "__main__":
    run_lexical_stress_test()
