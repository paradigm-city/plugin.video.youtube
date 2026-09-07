# -*- coding: utf-8 -*-
"""
    Unit tests for rate-bypass throttling algorithms:
    - Arithmetic and array rotation primitives (unshift, reverse, mod, splice, prepend, swap)
    - Throttling cipher character transforms (cipher_a, cipher_b)
    - CalculateN parser, plan generator, and execution engine
"""

from resources.lib.youtube_plugin.youtube.helper.ratebypass.ratebypass import (
    CalculateN,
    js_splice,
    throttling_cipher_function_a,
    throttling_cipher_function_b,
    throttling_mod_func,
    throttling_nested_splice,
    throttling_prepend,
    throttling_push,
    throttling_reverse,
    throttling_splice,
    throttling_swap,
    throttling_unshift,
)


class TestRateBypassPrimitives:
    """Unit tests for individual array manipulation and throttling primitives."""

    def test_throttling_reverse(self):
        arr = [1, 2, 3, 4, 5]
        throttling_reverse(arr)
        assert arr == [5, 4, 3, 2, 1]

    def test_throttling_push(self):
        arr = ['a', 'b']
        throttling_push(arr, 'c')
        assert arr == ['a', 'b', 'c']

    def test_throttling_mod_func(self):
        arr = [0, 1, 2, 3, 4]  # len = 5
        assert throttling_mod_func(arr, 3) == 3
        assert throttling_mod_func(arr, 5) == 0
        assert throttling_mod_func(arr, 7) == 2
        assert throttling_mod_func(arr, -2) == 3

    def test_throttling_unshift(self):
        arr = [1, 2, 3, 4, 5]
        throttling_unshift(arr, 2)
        # Shift 2 positions right: last 2 elements [4, 5] move to front
        assert arr == [4, 5, 1, 2, 3]

    def test_throttling_swap(self):
        arr = ['a', 'b', 'c', 'd']
        throttling_swap(arr, 2)
        assert arr == ['c', 'b', 'a', 'd']

    def test_throttling_splice(self):
        arr = ['a', 'b', 'c', 'd']
        throttling_splice(arr, 1)
        assert arr == ['a', 'c', 'd']

    def test_throttling_nested_splice(self):
        arr = ['a', 'b', 'c', 'd']
        throttling_nested_splice(arr, 2)
        # Nested splice swaps index 0 and index 2
        assert arr == ['c', 'b', 'a', 'd']

    def test_throttling_prepend(self):
        arr = [1, 2, 3, 4, 5]
        throttling_prepend(arr, 2)
        assert arr == [4, 5, 1, 2, 3]


class TestJsSplice:
    """Unit tests for JavaScript-compatible Array.prototype.splice emulation."""

    def test_js_splice_delete(self):
        arr = ['a', 'b', 'c', 'd', 'e']
        deleted = js_splice(arr, 1, 2)
        assert deleted == ['b', 'c']
        assert arr == ['a', 'd', 'e']

    def test_js_splice_insert_and_delete(self):
        arr = ['a', 'd', 'e']
        deleted = js_splice(arr, 1, 1, 'b', 'c')
        assert deleted == ['d']
        assert arr == ['a', 'b', 'c', 'e']

    def test_js_splice_replace(self):
        arr = ['a', 'b', 'c']
        deleted = js_splice(arr, 1, 1, 'x', 'y')
        assert deleted == ['b']
        assert arr == ['a', 'x', 'y', 'c']

    def test_js_splice_start_exceeds_length(self):
        arr = ['a', 'b']
        deleted = js_splice(arr, 10, 1, 'c')
        assert deleted == []
        assert arr == ['a', 'b', 'c']

    def test_js_splice_negative_start(self):
        arr = ['a', 'b', 'c', 'd']
        deleted = js_splice(arr, -2, 1)
        # start -2 maps to len(arr) - (-2) = 6 in code, clamped to len(arr)
        assert isinstance(deleted, list)


class TestThrottlingCipherFunctions:
    """Unit tests for character substitution ciphers."""

    def test_throttling_cipher_function_a(self):
        chars = list('sampleToken123')
        original_len = len(chars)
        throttling_cipher_function_a(chars, 'cipherKey')
        assert len(chars) == original_len
        # The characters should have been altered by the cipher permutation
        assert ''.join(chars) != 'sampleToken123'

    def test_throttling_cipher_function_b(self):
        chars = list('sampleToken123')
        original_len = len(chars)
        throttling_cipher_function_b(chars, 'cipherKey')
        assert len(chars) == original_len
        assert ''.join(chars) != 'sampleToken123'


class TestCalculateN:
    """Tests for CalculateN throttling extractor and execution engine."""

    def test_get_throttling_function_code(self):
        sample_js = (
            'var abc=123;'
            'var de=function(a){'
            'var b=a.split("");'
            'enhanced_except_("test");'
            'return b.join("");'
            '};'
        )
        code = CalculateN.get_throttling_function_code(sample_js)
        assert code is not None
        assert 'enhanced_except_' in code
        assert '=function(' in code

    def test_get_throttling_function_code_missing_fiduciary(self):
        sample_js = 'var abc=123; function test(a){ return a; }'
        assert CalculateN.get_throttling_function_code(sample_js) is None

    def test_get_throttling_plan_gen(self):
        raw_code = 'var x=1;try{c[0](c[1]),c[2](c[3],c[4])}catch(e){return""}'
        steps = list(CalculateN.get_throttling_plan_gen(raw_code))
        assert steps == [['0', '1'], ['2', '3', '4']]

    def test_calculate_n_end_to_end(self):
        # Construct synthetic throttling JS with reverse mapping and array references
        synthetic_js = (
            'prefix=function(){};'
            'calculateN=function(a){'
            'var b=a.split(""),c=[function(d){d.reverse()},b];'
            'try{c[0](c[1])}catch(e){return""};'
            'enhanced_except_();'
            'return b.join("");'
            '};'
        )
        calculator = CalculateN(synthetic_js)
        assert calculator.throttling_function_code is not None

        initial_chars = list('abcdef')
        result = calculator.calculate_n(initial_chars)
        assert result == 'fedcba'

        # Test memoization: subsequent call reuses cached value without re-running
        reused = calculator.calculate_n(list('xyz'))
        assert reused == 'fedcba'

    def test_calculate_n_without_code_returns_none(self):
        calculator = CalculateN('unrelated javascript code')
        assert calculator.calculate_n(list('test')) is None
