import sys
import time
from pathlib import Path

# Подключаем src
sys.path.append(str(Path(__file__).parent.parent / "src"))

from dsm.core import DynamicSegmentedMemory

def run_demo():
    # Создаем DSM с быстрой физикой для демо
    dsm = DynamicSegmentedMemory(decay_rate=0.5) 
    
    print("=== ДЕМОНСТРАЦИЯ DSM 3.0: ИНТЕЛЛЕКТУАЛЬНАЯ ПАМЯТЬ ===\n")

    # 1. Заполнение памяти
    print("[+] ШАГ 1: Заполняем память знаниями...")
    dsm.add_memory("def login(): print('access granted')", metadata={"tag": "auth"})
    dsm.add_memory("def logout(): print('goodbye')", metadata={"tag": "auth"})
    secret_id = dsm.add_memory("def execute_order_66(): print('order executed')", metadata={"tag": "hidden"})
    dsm.add_memory("def print_hello(): print('hello world')", metadata={"tag": "ui"})
    
    print(f"    В памяти {len(dsm.hot_memory)} сегментов. Все они 'горячие' (heat=1.0).\n")

    # 2. Симуляция времени
    print("[+] ШАГ 2: Проходит время... Память остывает.")
    # Искусственно состариваем секретный сегмент на 3 часа
    dsm.hot_memory[secret_id].last_accessed -= (3 * 3600)
    dsm.maintenance_loop() # Запускаем остывание
    
    current_heat = dsm.hot_memory[secret_id].heat
    print(f"    Секретный код остыл. Текущий Heat: {current_heat:.4f}")
    print("    (Теперь он имеет низкий приоритет в выдаче)\n")

    # 3. Поиск по слову
    print("[+] ШАГ 3: Ищем 'order'.")
    results = dsm.search(query="order", top_k=1)
    
    if results:
        seg, score = results[0]
        print(f"    НАЙДЕНО: {seg.content}")
        print(f"    Скор (с учетом Heat): {score:.4f}")
        print(f"    НОВЫЙ HEAT ПОСЛЕ ПОИСКА: {seg.heat:.1f}")
        print("    (Система вспомнила этот код и разогрела его!)\n")

    # 4. Проверка на вытеснение
    print("[+] ШАГ 4: Экстремальное остывание (забывание).")
    # Состариваем один из сегментов на 20 часов
    dsm.hot_memory[list(dsm.hot_memory.keys())[0]].last_accessed -= (20 * 3600)
    evicted = dsm.maintenance_loop()
    
    print(f"    Вытеснено в архив (Cold Storage) из-за неактуальности: {evicted} сегментов.")
    print(f"    Размер активной (Hot) памяти: {len(dsm.hot_memory)}")
    print(f"    Размер архива (Cold): {len(dsm.cold_memory)}\n")

    print("=== ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА: ПАМЯТЬ АДАПТИРОВАНА ===")

if __name__ == "__main__":
    run_demo()
