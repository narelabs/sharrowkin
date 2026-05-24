"""Tests for calculator module."""

import pytest
from calculator import add, subtract, multiply, divide


class TestAdd:
    """Tests for the add function."""

    def test_add_positive_numbers(self):
        """Test adding two positive numbers."""
        assert add(2, 3) == 5
        assert add(10, 20) == 30

    def test_add_negative_numbers(self):
        """Test adding negative numbers."""
        assert add(-1, -1) == -2
        assert add(-5, -10) == -15

    def test_add_mixed_signs(self):
        """Test adding numbers with different signs."""
        assert add(-1, 1) == 0
        assert add(5, -3) == 2
        assert add(-10, 15) == 5

    def test_add_floats(self):
        """Test adding floating point numbers."""
        assert add(2.5, 3.7) == pytest.approx(6.2)
        assert add(0.1, 0.2) == pytest.approx(0.3)

    def test_add_zero(self):
        """Test adding zero."""
        assert add(0, 0) == 0
        assert add(5, 0) == 5
        assert add(0, 5) == 5


class TestSubtract:
    """Tests for the subtract function."""

    def test_subtract_positive_numbers(self):
        """Test subtracting positive numbers."""
        assert subtract(5, 3) == 2
        assert subtract(10, 5) == 5

    def test_subtract_result_negative(self):
        """Test subtraction resulting in negative number."""
        assert subtract(3, 5) == -2
        assert subtract(1, 10) == -9

    def test_subtract_floats(self):
        """Test subtracting floating point numbers."""
        assert subtract(10.5, 2.5) == pytest.approx(8.0)
        assert subtract(5.7, 2.3) == pytest.approx(3.4)

    def test_subtract_zero(self):
        """Test subtracting zero."""
        assert subtract(5, 0) == 5
        assert subtract(0, 5) == -5

    def test_subtract_same_number(self):
        """Test subtracting a number from itself."""
        assert subtract(5, 5) == 0
        assert subtract(-3, -3) == 0


class TestMultiply:
    """Tests for the multiply function."""

    def test_multiply_positive_numbers(self):
        """Test multiplying positive numbers."""
        assert multiply(2, 3) == 6
        assert multiply(5, 4) == 20

    def test_multiply_negative_numbers(self):
        """Test multiplying negative numbers."""
        assert multiply(-2, 3) == -6
        assert multiply(-2, -3) == 6
        assert multiply(4, -5) == -20

    def test_multiply_floats(self):
        """Test multiplying floating point numbers."""
        assert multiply(2.5, 4) == pytest.approx(10.0)
        assert multiply(1.5, 2.5) == pytest.approx(3.75)

    def test_multiply_by_zero(self):
        """Test multiplying by zero."""
        assert multiply(5, 0) == 0
        assert multiply(0, 5) == 0
        assert multiply(0, 0) == 0

    def test_multiply_by_one(self):
        """Test multiplying by one."""
        assert multiply(5, 1) == 5
        assert multiply(1, 5) == 5


class TestDivide:
    """Tests for the divide function."""

    def test_divide_positive_numbers(self):
        """Test dividing positive numbers."""
        assert divide(6, 3) == pytest.approx(2.0)
        assert divide(10, 2) == pytest.approx(5.0)

    def test_divide_with_remainder(self):
        """Test division with remainder."""
        assert divide(5, 2) == pytest.approx(2.5)
        assert divide(7, 3) == pytest.approx(2.333333, rel=1e-5)

    def test_divide_negative_numbers(self):
        """Test dividing negative numbers."""
        assert divide(10, -2) == pytest.approx(-5.0)
        assert divide(-10, 2) == pytest.approx(-5.0)
        assert divide(-10, -2) == pytest.approx(5.0)

    def test_divide_by_zero(self):
        """Test that dividing by zero raises ValueError."""
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            divide(5, 0)
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            divide(0, 0)

    def test_divide_zero_by_number(self):
        """Test dividing zero by a non-zero number."""
        assert divide(0, 5) == pytest.approx(0.0)
        assert divide(0, -3) == pytest.approx(0.0)

    def test_divide_floats(self):
        """Test dividing floating point numbers."""
        assert divide(7.5, 2.5) == pytest.approx(3.0)
        assert divide(10.0, 4.0) == pytest.approx(2.5)
