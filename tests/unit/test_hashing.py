from __future__ import annotations

from civicproof_common.hashing import content_hash, hash_string, verify_hash


class TestContentHash:
    def test_produces_sha256_hex(self):
        data = b"hello world"
        result = content_hash(data)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        data = b"same input data"
        assert content_hash(data) == content_hash(data)

    def test_different_inputs_produce_different_hashes(self):
        assert content_hash(b"input_a") != content_hash(b"input_b")

    def test_empty_bytes_produces_valid_hash(self):
        result = content_hash(b"")
        assert len(result) == 64

    def test_known_sha256_value(self):
        data = b"abc"
        expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        assert content_hash(data) == expected

    def test_large_input(self):
        data = b"x" * 10_000_000
        result = content_hash(data)
        assert len(result) == 64


class TestVerifyHash:
    def test_correct_hash_returns_true(self):
        data = b"verify me"
        hash_value = content_hash(data)
        assert verify_hash(data, hash_value) is True

    def test_wrong_hash_returns_false(self):
        data = b"verify me"
        assert verify_hash(data, "a" * 64) is False

    def test_tampered_data_returns_false(self):
        data = b"original data"
        hash_value = content_hash(data)
        assert verify_hash(b"tampered data", hash_value) is False

    def test_timing_safe(self):
        data = b"safe comparison"
        correct_hash = content_hash(data)
        wrong_hash = "0" * 64
        result_correct = verify_hash(data, correct_hash)
        result_wrong = verify_hash(data, wrong_hash)
        assert result_correct is True
        assert result_wrong is False


class TestHashString:
    def test_produces_hash_from_string(self):
        result = hash_string("hello")
        assert len(result) == 64

    def test_consistent_with_content_hash(self):
        value = "test string"
        assert hash_string(value) == content_hash(value.encode("utf-8"))

    def test_custom_encoding(self):
        value = "cafe"
        result_utf8 = hash_string(value, encoding="utf-8")
        result_latin1 = hash_string(value, encoding="latin-1")
        assert len(result_utf8) == 64
        assert len(result_latin1) == 64
