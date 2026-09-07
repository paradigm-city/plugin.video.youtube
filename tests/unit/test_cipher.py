# -*- coding: utf-8 -*-
"""
    Unit tests for signature deciphering engine:
    - JsonScriptEngine action primitives and execution pipeline
    - Cipher regex function extractors and signature transformation
"""

import pytest

from resources.lib.youtube_plugin.youtube.helper.signature.cipher import Cipher
from resources.lib.youtube_plugin.youtube.helper.signature.json_script_engine import (
    JsonScriptEngine,
)


class TestJsonScriptEnginePrimitives:
    """Unit tests for individual JsonScriptEngine static helper methods."""

    def test_list(self):
        result = JsonScriptEngine._list('hello')
        assert result == ['h', 'e', 'l', 'l', 'o']

    def test_join(self):
        result = JsonScriptEngine._join(['h', 'e', 'l', 'l', 'o'])
        assert result == 'hello'

    def test_reverse(self):
        chars = ['a', 'b', 'c', 'd']
        result = JsonScriptEngine._reverse(chars)
        assert result == ['d', 'c', 'b', 'a']

    def test_slice(self):
        chars = ['a', 'b', 'c', 'd', 'e']
        result = JsonScriptEngine._slice(chars, 3)
        assert result == ['a', 'b', 'c']

    def test_splice(self):
        chars = ['a', 'b', 'c', 'd', 'e']
        result = JsonScriptEngine._splice(chars, 1, 3)
        assert result == ['a', 'd', 'e']

    def test_swap_standard(self):
        chars = ['a', 'b', 'c', 'd']
        result = JsonScriptEngine._swap(chars, 2)
        assert result == ['c', 'b', 'a', 'd']

    def test_swap_index(self):
        chars = ['a', 'b', 'c', 'd']
        result = JsonScriptEngine._swap(chars, 3)
        assert result == ['d', 'b', 'c', 'a']


class TestJsonScriptEngineExecution:
    """Tests for JsonScriptEngine script execution pipeline."""

    def test_execute_pipeline(self):
        script = {
            'actions': [
                {'func': 'list', 'params': ['%SIG%']},
                {'func': 'swap', 'params': ['%SIG%', 2]},
                {'func': 'reverse', 'params': ['%SIG%']},
                {'func': 'slice', 'params': ['%SIG%', 3]},
                {'func': 'join', 'params': ['%SIG%']},
            ]
        }
        engine = JsonScriptEngine(script)
        # 'abcd' -> ['a','b','c','d'] -> swap 2 -> ['c','b','a','d']
        # -> reverse -> ['d','a','b','c'] -> slice 3 -> ['d','a','b'] -> 'dab'
        assert engine.execute('abcd') == 'dab'

    def test_execute_early_return(self):
        script = {
            'actions': [
                {'func': 'list', 'params': ['%SIG%']},
                {'func': 'reverse', 'params': ['%SIG%']},
                {'func': 'return', 'params': []},
                {'func': 'slice', 'params': ['%SIG%', 1]},
                {'func': 'join', 'params': ['%SIG%']},
            ]
        }
        engine = JsonScriptEngine(script)
        # Returns early after reverse without executing slice/join
        assert engine.execute('abc') == ['c', 'b', 'a']

    def test_execute_unknown_method_raises(self):
        script = {
            'actions': [
                {'func': 'unknown_action', 'params': ['%SIG%']},
            ]
        }
        engine = JsonScriptEngine(script)
        with pytest.raises(AttributeError):
            engine.execute('abc')


class TestCipherRegexExtraction:
    """Tests for Cipher regular expression matching against player JavaScript."""

    def test_find_signature_function_name_patterns(self):
        # Pattern 1: encodeURIComponent(sig(
        js_1 = 'b && a.set("alr", encodeURIComponent(mySigFunc(decodeURIComponent(a.s))))'
        assert Cipher._find_signature_function_name(js_1) == 'mySigFunc'

        # Pattern 2: m=sig(decodeURIComponent(h.s))
        js_2 = 'var m=customSig(decodeURIComponent(h.s));'
        assert Cipher._find_signature_function_name(js_2) == 'customSig'

        # Pattern 3: c&&(c=sig(decodeURIComponent(c))
        js_3 = 'c&&(c=playerDecipher(decodeURIComponent(c))'
        assert Cipher._find_signature_function_name(js_3) == 'playerDecipher'

        # Pattern 4: sig=function(a){a=a.split("")
        js_4 = 'someVar.sigName=function(a){a=a.split("");BC.r(a,3);return a.join("")};'
        assert Cipher._find_signature_function_name(js_4) == 'sigName'

        # Pattern 5: legacy signature keyword
        js_5 = '"signature", legacyDecipher(a);'
        assert Cipher._find_signature_function_name(js_5) == 'legacyDecipher'

    def test_find_signature_function_name_not_found(self):
        js = 'function unrelatedCode(x) { return x * 2; }'
        assert Cipher._find_signature_function_name(js) == ''

    def test_find_function_body(self):
        js = 'testFunc=function(a){a=a.split("");obj.swap(a,2);return a.join("")}'
        param, body = Cipher._find_function_body('testFunc', js)
        assert param == 'a'
        assert 'obj.swap(a,2)' in body

    def test_find_function_body_not_found(self):
        js = 'otherFunc=function(x){return x;}'
        param, body = Cipher._find_function_body('testFunc', js)
        assert param == ''
        assert body == ''

    def test_find_object_body(self):
        js = 'var helperObj={swap:function(a,b){var c=a[0];a[0]=a[b];a[b]=c},rev:function(a){a.reverse()}};'
        body = Cipher._find_object_body('helperObj', js)
        assert 'swap:function' in body
        assert 'rev:function' in body

    def test_get_object_function_caching(self):
        js = 'var helperObj={swap:function(a,b){var c=a[0];a[0]=a[b];a[b]=c},rev:function(a){a.reverse()}};'
        cipher = Cipher(context=None, javascript=js)
        fn_swap = cipher._get_object_function('helperObj', 'swap', js)
        assert fn_swap['name'] == 'swap'
        assert fn_swap['params'] == 'a,b'
        assert 'helperObj' in cipher._object_cache
        # Second call returns from cache
        cached_swap = cipher._get_object_function('helperObj', 'swap', js)
        assert cached_swap is fn_swap


class TestCipherGetSignature:
    """Tests for Cipher.get_signature end-to-end transformation."""

    def test_load_javascript_parses_actions(self, mocker):
        js = (
            'var helper={swap:function(a,b){var c=a[0];a[0]=a[b%a.length];a[b]=c},'
            'rev:function(a){a.reverse()}};'
            'decipher=function(a){a=a.split("");helper.swap(a,2);helper.rev(a);return a.join("")};'
            'c&&(c=decipher(decodeURIComponent(c)));'
        )

        mock_context = mocker.MagicMock()
        mock_cache = mocker.MagicMock()
        mock_context.get_function_cache.return_value = mock_cache
        mock_cache.ONE_DAY = 86400
        # When run is called, call the function directly
        mock_cache.run.side_effect = lambda fn, *args, **kwargs: fn(kwargs.get('javascript', js))

        cipher = Cipher(context=mock_context, javascript=js)
        # 'abcd' -> swap 2 -> 'cbad' -> reverse -> 'dabc'
        result = cipher.get_signature('abcd')
        assert result == 'dabc'

    def test_get_signature_returns_empty_on_missing_script(self, mocker):
        mock_context = mocker.MagicMock()
        mock_cache = mocker.MagicMock()
        mock_context.get_function_cache.return_value = mock_cache
        mock_cache.run.return_value = None

        cipher = Cipher(context=mock_context, javascript='')
        assert cipher.get_signature('signature123') == ''
