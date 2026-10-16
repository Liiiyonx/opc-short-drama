"""Storage 抽象单元测试（W3）。"""
import pytest

from app.services.storage.base import (
    StorageError,
    generate_key,
    validate_key,
)
from app.services.storage.local import LocalStorage


def test_generate_key_format():
    key = generate_key("works/1/json", "output.json")
    assert key.startswith("works/1/json/")
    assert key.endswith(".json")
    assert "/" in key


@pytest.mark.parametrize(
    "bad_key",
    ["", "/abs/path", "../escape", "a/../../b", "a\\b", "key with space", "key?x=1"],
)
def test_validate_key_rejects(bad_key):
    with pytest.raises(StorageError):
        validate_key(bad_key)


def test_local_put_get_roundtrip(tmp_path):
    storage = LocalStorage(str(tmp_path / "root"))
    key = "works/1/json/abc123.json"
    storage.put(key, b"hello-opc", "application/json")

    assert storage.get_bytes(key) == b"hello-opc"
    assert storage.get_url(key) == "/api/v1/files/works/1/json/abc123.json"
    assert (tmp_path / "root" / "works/1/json/abc123.json").is_file()

    storage.delete(key)
    with pytest.raises(StorageError):
        storage.get_bytes(key)
