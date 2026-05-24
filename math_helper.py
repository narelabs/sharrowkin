"""Модуль математических вспомогательных функций."""


def add(a: float, b: float) -> float:
    """Складывает два числа.
    
    Args:
        a: Первое число
        b: Второе число
    
    Returns:
        Сумма чисел a и b
    
    Examples:
        >>> add(2, 3)
        5
        >>> add(-1, 1)
        0
    """
    return a + b


def multiply(a: float, b: float) -> float:
    """Умножает два числа.
    
    Args:
        a: Первый множитель
        b: Второй множитель
    
    Returns:
        Произведение чисел a и b
    
    Examples:
        >>> multiply(3, 4)
        12
        >>> multiply(-2, 5)
        -10
    """
    return a * b


def power(a: float, b: float) -> float:
    """Возводит число в степень.
    
    Args:
        a: Основание степени
        b: Показатель степени
    
    Returns:
        Результат возведения a в степень b
    
    Examples:
        >>> power(2, 3)
        8
        >>> power(5, 2)
        25
        >>> power(10, 0)
        1
    """
    return a ** b
