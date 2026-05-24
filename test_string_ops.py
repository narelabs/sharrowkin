"""Тесты для модуля string_ops."""

import pytest
from string_ops import concat, repeat, reverse


class TestConcat:
    """Тесты для функции concat."""

    def test_concat_simple_strings(self):
        """Тест конкатенации простых строк."""
        assert concat('Hello', 'World') == 'HelloWorld'
        assert concat('Python', 'Test') == 'PythonTest'

    def test_concat_with_space(self):
        """Тест конкатенации строк с пробелом."""
        assert concat('Привет', ' мир') == 'Привет мир'
        assert concat('Hello ', 'World') == 'Hello World'

    def test_concat_empty_strings(self):
        """Тест конкатенации пустых строк."""
        assert concat('', '') == ''
        assert concat('Hello', '') == 'Hello'
        assert concat('', 'World') == 'World'

    def test_concat_special_characters(self):
        """Тест конкатенации строк со специальными символами."""
        assert concat('Hello!', '?') == 'Hello!?'
        assert concat('Test', '123') == 'Test123'
        assert concat('@#$', '%^&') == '@#$%^&'

    def test_concat_unicode(self):
        """Тест конкатенации Unicode строк."""
        assert concat('Привет', 'Мир') == 'ПриветМир'
        assert concat('你好', '世界') == '你好世界'
        assert concat('🎉', '🎊') == '🎉🎊'


class TestRepeat:
    """Тесты для функции repeat."""

    def test_repeat_positive_times(self):
        """Тест повторения строки положительное количество раз."""
        assert repeat('abc', 3) == 'abcabcabc'
        assert repeat('Hi', 2) == 'HiHi'
        assert repeat('x', 5) == 'xxxxx'

    def test_repeat_zero_times(self):
        """Тест повторения строки ноль раз."""
        assert repeat('test', 0) == ''
        assert repeat('Hello', 0) == ''

    def test_repeat_one_time(self):
        """Тест повторения строки один раз."""
        assert repeat('test', 1) == 'test'
        assert repeat('Python', 1) == 'Python'

    def test_repeat_empty_string(self):
        """Тест повторения пустой строки."""
        assert repeat('', 5) == ''
        assert repeat('', 0) == ''

    def test_repeat_unicode(self):
        """Тест повторения Unicode строк."""
        assert repeat('Привет', 2) == 'ПриветПривет'
        assert repeat('🎉', 3) == '🎉🎉🎉'

    def test_repeat_large_number(self):
        """Тест повторения строки большое количество раз."""
        result = repeat('a', 100)
        assert len(result) == 100
        assert result == 'a' * 100


class TestReverse:
    """Тесты для функции reverse."""

    def test_reverse_simple_string(self):
        """Тест переворачивания простой строки."""
        assert reverse('hello') == 'olleh'
        assert reverse('Python') == 'nohtyP'

    def test_reverse_numbers(self):
        """Тест переворачивания строки с числами."""
        assert reverse('12345') == '54321'
        assert reverse('9876') == '6789'

    def test_reverse_empty_string(self):
        """Тест переворачивания пустой строки."""
        assert reverse('') == ''

    def test_reverse_single_character(self):
        """Тест переворачивания строки из одного символа."""
        assert reverse('a') == 'a'
        assert reverse('Z') == 'Z'

    def test_reverse_palindrome(self):
        """Тест переворачивания палиндрома."""
        assert reverse('radar') == 'radar'
        assert reverse('level') == 'level'

    def test_reverse_with_spaces(self):
        """Тест переворачивания строки с пробелами."""
        assert reverse('hello world') == 'dlrow olleh'
        assert reverse('a b c') == 'c b a'

    def test_reverse_unicode(self):
        """Тест переворачивания Unicode строк."""
        assert reverse('Привет') == 'тевирП'
        assert reverse('你好') == '好你'

    def test_reverse_special_characters(self):
        """Тест переворачивания строки со специальными символами."""
        assert reverse('Hello!') == '!olleH'
        assert reverse('@#$%') == '%$#@'
