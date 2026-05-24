"""Calculator module with basic arithmetic operations.

This module provides simple arithmetic functions for addition, subtraction,
multiplication, and division with proper type hints and error handling.
"""


def add(a: float, b: float) -> float:
    """Add two numbers together.
    
    Args:
        a: The first number to add.
        b: The second number to add.
    
    Returns:
        The sum of a and b.
    
    Examples:
        >>> add(2, 3)
        5
        >>> add(-1, 1)
        0
        >>> add(2.5, 3.7)
        6.2
    """
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract the second number from the first.
    
    Args:
        a: The number to subtract from.
        b: The number to subtract.
    
    Returns:
        The difference of a and b (a - b).
    
    Examples:
        >>> subtract(5, 3)
        2
        >>> subtract(3, 5)
        -2
        >>> subtract(10.5, 2.5)
        8.0
    """
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers together.
    
    Args:
        a: The first number to multiply.
        b: The second number to multiply.
    
    Returns:
        The product of a and b.
    
    Examples:
        >>> multiply(2, 3)
        6
        >>> multiply(-2, 3)
        -6
        >>> multiply(2.5, 4)
        10.0
    """
    return a * b


def divide(a: float, b: float) -> float:
    """Divide the first number by the second.
    
    Args:
        a: The dividend (number to be divided).
        b: The divisor (number to divide by).
    
    Returns:
        The quotient of a and b (a / b).
    
    Raises:
        ValueError: If b is zero (division by zero is not allowed).
    
    Examples:
        >>> divide(6, 3)
        2.0
        >>> divide(5, 2)
        2.5
        >>> divide(10, -2)
        -5.0
        >>> divide(5, 0)
        Traceback (most recent call last):
            ...
        ValueError: Cannot divide by zero
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
