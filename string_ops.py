"""Модуль операций со строками."""


def concat(s1: str, s2: str) -> str:
    """Конкатенирует две строки.
    
    Args:
        s1: Первая строка
        s2: Вторая строка
    
    Returns:
        Результат конкатенации s1 и s2
    
    Examples:
        >>> concat('Hello', 'World')
        'HelloWorld'
        >>> concat('Привет', ' мир')
        'Привет мир'
    """
    return s1 + s2


def repeat(s: str, n: int) -> str:
    """Повторяет строку n раз.
    
    Args:
        s: Строка для повторения
        n: Количество повторений
    
    Returns:
        Строка s, повторенная n раз
    
    Examples:
        >>> repeat('abc', 3)
        'abcabcabc'
        >>> repeat('Hi', 2)
        'HiHi'
        >>> repeat('test', 0)
        ''
    """
    return s * n


def reverse(s: str) -> str:
    """Переворачивает строку.
    
    Args:
        s: Строка для переворачивания
    
    Returns:
        Перевернутая строка s
    
    Examples:
        >>> reverse('hello')
        'olleh'
        >>> reverse('Python')
        'nohtyP'
        >>> reverse('12345')
        '54321'
    """
    return s[::-1]
