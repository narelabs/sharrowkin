"""Тесты для модуля math_helper."""

import pytest
from math_helper import add, multiply, power


class TestAdd:
    """Тесты для функции add."""

    def test_add_positive_numbers(self):
        """Тест сложения положительных чисел."""
        assert add(2, 3) == 5
        assert add(10, 20) == 30

    def test_add_negative_numbers(self):
        """Тест сложения отрицательных чисел."""
        assert add(-1, 1) == 0
        assert add(-5, -3) == -8

    def test_add_floats(self):
        """Тест сложения дробных чисел."""
        assert add(2.5, 3.5) == pytest.approx(6.0)
        assert add(0.1, 0.2) == pytest.approx(0.3)

    def test_add_zero(self):
        """Тест сложения с нулем."""
        assert add(0, 0) == 0
        assert add(5, 0) == 5
        assert add(0, 7) == 7


class TestMultiply:
    """Тесты для функции multiply."""

    def test_multiply_positive_numbers(self):
        """Тест умножения положительных чисел."""
        assert multiply(3, 4) == 12
        assert multiply(5, 6) == 30

    def test_multiply_negative_numbers(self):
        """Тест умножения отрицательных чисел."""
        assert multiply(-2, 5) == -10
        assert multiply(-3, -4) == 12
        assert multiply(6, -2) == -12

    def test_multiply_floats(self):
        """Тест умножения дробных чисел."""
        assert multiply(2.5, 4.0) == pytest.approx(10.0)
        assert multiply(1.5, 3.0) == pytest.approx(4.5)

    def test_multiply_by_zero(self):
        """Тест умножения на ноль."""
        assert multiply(5, 0) == 0
        assert multiply(0, 10) == 0
        assert multiply(0, 0) == 0

    def test_multiply_by_one(self):
        """Тест умножения на единицу."""
        assert multiply(7, 1) == 7
        assert multiply(1, 9) == 9


class TestPower:
    """Тесты для функции power."""

    def test_power_positive_exponent(self):
        """Тест возведения в положительную степень."""
        assert power(2, 3) == 8
        assert power(5, 2) == 25
        assert power(3, 4) == 81

    def test_power_zero_exponent(self):
        """Тест возведения в нулевую степень."""
        assert power(10, 0) == 1
        assert power(5, 0) == 1
        assert power(100, 0) == 1

    def test_power_one_exponent(self):
        """Тест возведения в первую степень."""
        assert power(7, 1) == 7
        assert power(15, 1) == 15

    def test_power_negative_exponent(self):
        """Тест возведения в отрицательную степень."""
        assert power(2, -1) == pytest.approx(0.5)
        assert power(10, -2) == pytest.approx(0.01)
        assert power(4, -2) == pytest.approx(0.0625)

    def test_power_fractional_exponent(self):
        """Тест возведения в дробную степень."""
        assert power(4, 0.5) == pytest.approx(2.0)
        assert power(9, 0.5) == pytest.approx(3.0)
        assert power(8, 1/3) == pytest.approx(2.0)

    def test_power_negative_base(self):
        """Тест возведения отрицательного числа в степень."""
        assert power(-2, 2) == 4
        assert power(-2, 3) == -8
        assert power(-3, 2) == 9

    def test_power_zero_base(self):
        """Тест возведения нуля в степень."""
        assert power(0, 1) == 0
        assert power(0, 5) == 0
        assert power(0, 100) == 0
