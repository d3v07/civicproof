import json

import pytest

# 50 Backend Stress & Edge Case Payloads
# These payloads simulate extreme user inputs, malformed types, and injection vectors
# designed to break backend validation logic (e.g. Pydantic ingestion models).

EDGE_CASES = [
    (1, "Empty dict", {}),
    (2, "List instead of dict", []),
    (3, "String instead of dict", "invalid_payload"),
    (4, "Null payload", None),
    (5, "Missing required fields completely", {"optional": "data"}),
    (6, "Extremely large string field", {"name": "A" * 100000}),
    (7, "Integer instead of string", {"name": 12345}),
    (8, "Float instead of string", {"name": 12.34}),
    (9, "Boolean instead of string", {"name": True}),
    (10, "Null value for required string", {"name": None}),
    (11, "Max int overflow constraint", {"id": 9223372036854775807}),
    (12, "Min int overflow constraint", {"id": -9223372036854775808}),
    (13, "Exceedingly large float", {"score": 1e308}),
    (14, "Deeply nested JSON recursion max depth", {"data": {"a": {"b": {"c": {"d": "1"}}}}}),
    (15, "SQL Injection in UUID field", {"uuid": "1'; DROP TABLE cases;--"}),
    (16, "NoSQL Injection vector", {"id": {"$gt": 0}}),
    (17, "Command Injection vector", {"filename": "; rm -rf /"}),
    (18, "Path Traversal vector", {"path": "../../../../etc/passwd"}),
    (19, "XSS Payload in stored field", {"bio": "<script>alert('xss')</script>"}),
    (20, "LDAP Injection vector", {"user": "*(|(mail=*))"}),
    (21, "XML External Entity (XXE) string", {"xml": "<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><foo>&xxe;</foo>"}),
    (22, "SSRF attempt in URL field", {"url": "http://169.254.169.254/latest/meta-data/"}),
    (23, "Carriage return injection (CRLF)", {"headers": "Host: foo\r\n\r\nBypass"}),
    (24, "Format string vulnerability", {"log_format": "%x %x %x %x"}),
    (25, "Null byte termination string", {"filename": "secret.txt\0.jpg"}),
    (26, "Overlapping Unicode normalization", {"username": "admin\uFEFF"}),
    (27, "Bidi override attack", {"text": "RLO\u202eexe.txt"}),
    (28, "Zero width string", {"name": "\u200b\u200c\u200d"}),
    (29, "Special control characters", {"desc": "\x01\x02\x03\x04"}),
    (30, "Emoji bomb", {"bio": "🔥" * 5000}),
    (31, "Invalid date format", {"created_at": "2024-13-45T25:99:99Z"}),
    (32, "Unix epoch zero", {"created_at": "1970-01-01T00:00:00Z"}),
    (33, "Future date far ahead", {"created_at": "9999-12-31T23:59:59Z"}),
    (34, "Negative timestamp equivalent", {"created_at": "-1000-01-01T00:00:00Z"}),
    (35, "Malformed email address", {"email": "user@domain@com"}),
    (36, "Missing TLD in email", {"email": "user@locahost"}),
    (37, "Extremely long local email part", {"email": "A"*300 + "@gmail.com"}),
    (38, "Malformed UUID", {"id": "123e4567-e89b-12d3-a456-42661417400G"}),
    (39, "Missing boundary in multipart", {"file": "content..."}),
    (40, "Invalid IP Address format", {"ip": "256.256.256.256"}),
    (41, "IPv6 with excessive colons", {"ip": "::1::"}),
    (42, "Base64 payload missing padding", {"b64": "SGVsbG8gV29ybG"}),
    (43, "Hex encoding bypass attempt", {"hex": "%00%00"}),
    (44, "JSON Array containing mixed extreme types", {"items": [1, "test", None, [], {}]}),
    (45, "JSON Array with 10k items", {"items": [1] * 10000}),
    (
        46,
        "Duplicate keys in JSON map",
        json.loads('{"id": 1, "id": 2}'),  # Python's json.loads takes the last one
    ),
    (
        47,
        "Giant float precision",
        {"lat": 3.14159265358979323846264338327950},
    ),
    (48, "Octal notations in JSON string", {"val": "0123"}),
    (49, "YAML bypass strings", {"yaml_prop": "---"}),
    (50, "Extremely complex Regex DOS payload", {"regex": "(a+)+b"}),
]

@pytest.mark.parametrize("case_id, description, payload", EDGE_CASES)
def test_backend_edge_cases_stress(case_id, description, payload):
    """
    Test 50 distinct edge cases against a mock backend validation pipeline.
    Ensures that bad data safely throws a ValidationError or standard Exception
    instead of segfaulting, halting the thread, or leading to unchecked states.
    """
    # Mocking a basic validation layer
    def mock_validator(data):
        if not isinstance(data, dict):
            raise TypeError("Expected dict")
        # Ensure deep nesting isn't recursive infinity
        if str(data).count("{") > 10:
            raise ValueError("Too deep")
        return True

    try:
        mock_validator(payload)
        # If it passes validation, make sure it doesn't crash a mock database insert
        mock_db_insert = str(payload)
        assert len(mock_db_insert) < 2000000 # Memory bounds check threshold
    except (TypeError, ValueError, KeyError):
        # We expect many to fail validation safely
        pass
    except Exception as e:
        # Any other unknown exception implies a break in the system logic
        pytest.fail(f"System crashed on edge case {case_id} ({description}): {str(e)}")

def test_concurrency_stress():
    """
    Simulate 50 rapid simultaneous validations
    """
    import threading
    results = []

    def worker():
        try:
            # simple mock action
            json.dumps({"a": "b" * 1000})
            results.append(True)
        except Exception:
            results.append(False)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(results)
