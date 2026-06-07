import json
from pathlib import Path
from typing import Self

import pytest
from pydantic import BaseModel

from pazufa_scraper_be.cache_lib.types import Key


class SubKeyForTests(Key):
    """To test usage of SubKeys."""

    UPPER = "UPPER"
    lower = "lower"


class TestKeyUsage:
    """End-to-end tests for Key in cache operations."""

    @pytest.mark.parametrize(
        "key_type",
        [Key, SubKeyForTests],
    )
    def test_string_key_creates_key(self: Self, key_type: type[Key]) -> None:
        """Verify string input creates Key via metaclass."""
        key = key_type("test")
        assert isinstance(key, Key)
        assert key == "test"

    @pytest.mark.parametrize(
        "key_type",
        [Key, SubKeyForTests],
    )
    def test_same_string_returns_equal_keys(self: Self, key_type: type[Key]) -> None:
        """Verify creating Key with same string returns equal keys."""
        key1 = key_type("test")
        key2 = key_type("test")
        assert key1 == key2

    @pytest.mark.parametrize(
        "invalid_key",
        [123, None, [], {}, b"bytes"],
    )
    def test_non_string_raises(self: Self, invalid_key: object) -> None:
        """Verify non-string input raises TypeError."""
        with pytest.raises(TypeError, match=r"Only str allowed."):
            Key(invalid_key)


class TestSubKeyForTests:
    """Tests for SubKeyForTests enum."""

    def test_attribute_string_and_dot_access(self: Self) -> None:
        """Verify attribute access and string input return same key."""
        attr_key = SubKeyForTests["UPPER"]
        dot_key = SubKeyForTests.UPPER
        str_key = SubKeyForTests("UPPER")
        assert attr_key == str_key == dot_key
        assert isinstance(attr_key, SubKeyForTests)
        assert isinstance(dot_key, SubKeyForTests)
        assert isinstance(str_key, SubKeyForTests)
        assert str(attr_key) == "UPPER" == str(dot_key)


class TestKeyPydanticSchema:
    """Tests for Key pydantic schema support."""

    @pytest.mark.parametrize(
        "key_type",
        [Key, SubKeyForTests],
    )
    def test_pydantic_roundtrip_to_file(self: Self, key_type: type[Key], tmp_path: Path) -> None:
        """Verify Key can be serialized to file and deserialized back."""

        class TestModel(BaseModel):
            key: Key

        model = TestModel(key="test_key")
        json_file = tmp_path / "test.json"
        json_file.write_text(model.model_dump_json())

        loaded_model = TestModel.model_validate_json(json_file.read_text())
        assert loaded_model.key == key_type("test_key")

    @pytest.mark.parametrize(
        "key_type",
        [Key, SubKeyForTests],
    )
    def test_str_enum_is_json_serializable(self: Self, key_type: type[Key]) -> None:
        """Verify Key serializes to JSON string correctly."""
        key = key_type("json_test")
        assert json.dumps(key) == '"json_test"'
