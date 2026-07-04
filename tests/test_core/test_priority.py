"""Tests for lighterbird.core.priority — safe expression evaluator.

Covers: eval_safe, validate_safe, _assert_safe_expr edge cases.
"""

from __future__ import annotations

import pytest

from lighterbird.core.priority import eval_safe, validate_safe


class TestEvalSafe:
    def test_literal_number(self):
        assert eval_safe("42") == 42.0

    def test_float_literal(self):
        assert eval_safe("3.14") == 3.14

    def test_empty_expression_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            eval_safe("")

    def test_none_expression_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            eval_safe(None)  # type: ignore[arg-type]

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            eval_safe("   ")

    def test_simple_addition(self):
        assert eval_safe("1 + 2") == 3.0

    def test_subtraction(self):
        assert eval_safe("10 - 3") == 7.0

    def test_multiplication(self):
        assert eval_safe("4 * 5") == 20.0

    def test_division(self):
        assert eval_safe("10 / 4") == 2.5

    def test_floor_division(self):
        assert eval_safe("10 // 4") == 2.0

    def test_modulo(self):
        assert eval_safe("10 % 3") == 1.0

    def test_power(self):
        assert eval_safe("2 ** 3") == 8.0

    def test_unary_minus(self):
        assert eval_safe("-5") == -5.0

    def test_unary_plus(self):
        assert eval_safe("+3") == 3.0

    def test_with_variables(self):
        assert eval_safe("D * 2", variables={"D": 3.0}) == 6.0

    def test_with_custom_function(self):
        assert eval_safe("min(10, 5)") == 5.0

    def test_with_custom_functions_dict(self):
        assert eval_safe("max(3, 7)", functions={"max": max}) == 7.0

    def test_round_function(self):
        assert eval_safe("round(3.7)") == 4.0

    def test_int_function(self):
        assert eval_safe("int(3.9)") == 3.0

    def test_float_function(self):
        assert eval_safe("float('3.14')") == 3.14

    def test_abs_function(self):
        assert eval_safe("abs(-5)") == 5.0

    def test_complex_expression(self):
        result = eval_safe("min(20 + 2 * D, 70)", variables={"D": 10.0})
        assert result == 40.0

    def test_complex_capped(self):
        result = eval_safe("min(20 + 2 * D, 70)", variables={"D": 100.0})
        assert result == 70.0

    def test_zero_division_raises(self):
        with pytest.raises(ValueError, match="Expression error"):
            eval_safe("1 / 0")

    def test_inf_result_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            eval_safe("1e999", functions={"float": float})

    def test_nan_result_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            eval_safe("float('nan')")

    def test_syntax_error_raises(self):
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            eval_safe("1 + ")

    def test_non_numeric_result_raises(self):
        with pytest.raises(ValueError, match="did not return a number"):
            eval_safe("str(5)", functions={"str": str})

    def test_unsafe_ast_node_raises(self):
        with pytest.raises(ValueError, match="not allowed"):
            eval_safe("[1,2,3]")

    def test_unsafe_call_on_attribute_raises(self):
        with pytest.raises(ValueError, match="Only simple function calls"):
            eval_safe("math.sqrt(4)", functions={"math": lambda: None})

    def test_disallowed_function_raises(self):
        with pytest.raises(ValueError, match="Function.*not allowed"):
            eval_safe("exec('pass')")

    def test_disallowed_variable_raises(self):
        with pytest.raises(ValueError, match="Variable.*not allowed"):
            eval_safe("x + 1")

    def test_variable_allowed(self):
        assert eval_safe("D", variables={"D": 99.0}) == 99.0

    def test_pow_negative_base(self):
        assert eval_safe("(-2) ** 3") == -8.0


class TestValidateSafe:
    def test_valid_expression(self):
        assert validate_safe("1 + 2 * D", allowed_vars={"D"}) is True

    def test_invalid_syntax(self):
        assert validate_safe("1 + ") is False

    def test_disallowed_variable(self):
        assert validate_safe("x + 1") is False

    def test_disallowed_function(self):
        assert validate_safe("exec('pass')") is False

    def test_empty_string(self):
        assert validate_safe("") is False

    def test_safe_literal(self):
        assert validate_safe("42") is True

    def test_allowed_function(self):
        assert validate_safe("min(1, 2)") is True

    def test_disallowed_ast_node(self):
        assert validate_safe("[1, 2, 3]") is False
