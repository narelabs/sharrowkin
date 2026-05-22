import time
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH для импортов
sys.path.append(str(Path(__file__).parent.parent / "src"))

from dsm.core import DynamicSegmentedMemory

def run_tests():
    print("Start Testing DSM 3.0 Thermodynamics & Search...\n")
    
    # Инициализируем DSM с агрессивным затуханием (быстрое остывание)
    # eviction_threshold = 0.5 для быстрого вытеснения в тесте
    dsm = DynamicSegmentedMemory(rrf_k=60, decay_rate=0.5, eviction_threshold=0.5)
    
    # 1. Добавление сегментов
    print("[1] Добавляем сегменты в Hot Memory...")
    id1 = dsm.add_memory(content="def calculate_orbit(): pass", metadata={"name": "orbit"})
    id2 = dsm.add_memory(content="class spaceship:", metadata={"name": "ship"})
    
    print(f"  -> Сегмент 1 (orbit) ID: {id1}")
    print(f"  -> Сегмент 2 (ship) ID: {id2}")
    print(f"  -> Hot Memory size: {len(dsm.hot_memory)}\n")
    
    # Проверяем начальный Heat
    print(f"[2] Начальный Heat:")
    print(f"  -> orbit heat: {dsm.hot_memory[id1].heat}")
    print(f"  -> ship heat: {dsm.hot_memory[id2].heat}\n")
    
    # 2. Симуляция времени (Машина времени)
    print("[3] Симулируем прохождение 2 часов...")
    # Искусственно стареем сегмент 1 на 2 часа (7200 секунд)
    dsm.hot_memory[id1].last_accessed -= 7200 
    
    # 3. Применяем термодинамику (Maintenance Loop)
    print("[4] Запускаем Maintenance Loop...")
    evicted_count = dsm.maintenance_loop()
    print(f"  -> Вытеснено сегментов в Cold Storage: {evicted_count}")
    print(f"  -> Hot Memory size: {len(dsm.hot_memory)}")
    print(f"  -> Cold Memory size: {len(dsm.cold_memory)}\n")
    
    # 4. Проверяем результаты остывания
    print("[5] Проверка состояний после остывания:")
    if id1 in dsm.cold_memory:
        print(f"  -> УСПЕХ: Сегмент 1 (orbit) остыл и улетел в Cold Storage. Heat: {dsm.cold_memory[id1].heat:.4f}")
    if id2 in dsm.hot_memory:
        print(f"  -> УСПЕХ: Сегмент 2 (ship) остался горячим в Hot Memory. Heat: {dsm.hot_memory[id2].heat:.4f}\n")
        
    # 5. Тестируем Поиск и Разогрев (Reheating)
    print("[6] Тестируем реальный Гибридный Поиск (BM25 + Heat)...")
    # Добавим новый сегмент с уникальным словом
    id3 = dsm.add_memory(content="import tensorflow as tf # deep learning", metadata={"name": "ai"})
    dsm.hot_memory[id3].last_accessed -= 3600 # состарили на 1 час
    
    # Применяем остывание вручную
    dsm.thermodynamics.apply_decay(dsm.hot_memory)
    heat_before_search = dsm.hot_memory[id3].heat
    print(f"  -> Перед поиском по слову 'tensorflow' heat: {heat_before_search:.4f}")
    
    # Имитируем реальный поиск по слову 'tensorflow'
    results = dsm.search(query="tensorflow", top_k=5)
    
    if results and results[0][0].id == id3:
        print(f"  -> УСПЕХ: Сегмент найден по ключевому слову 'tensorflow'!")
    else:
        print(f"  -> ERROR: Сегмент НЕ НАЙДЕН по ключевому слову.")
        sys.exit(1)
        
    heat_after_search = dsm.hot_memory[id3].heat
    print(f"  -> После извлечения heat: {heat_after_search:.4f}")
    
    if heat_after_search == 1.0:
         print("  -> SUCCESS: Сегмент успешно РАЗОГРЕТ после реального поиска!\n")
    else:
         print("  -> ERROR: Сегмент НЕ БЫЛ разогрет.\n")
         sys.exit(1)
         
    print("FINAL SUCCESS: Реальный поиск и термодинамика DSM 3.0 работают идеально!")

if __name__ == "__main__":
    run_tests()
