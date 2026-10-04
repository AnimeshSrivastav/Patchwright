import pytest
from autofix.monitor.fingerprint import compute_fingerprint


STACK_TRACE = """  File "app/routes.py", line 24, in get_item
    return items[item_id]
KeyError: 'price'"""

STACK_TRACE_DIFF_LINE = """  File "app/routes.py", line 30, in get_item
    return items[item_id]
KeyError: 'price'"""

STACK_TRACE_DIFF_UUID = """  File "app/routes.py", line 24, in get_item
    item_id=550e8400-e29b-41d4-a716-446655440000
KeyError: 'price'"""


def test_same_error_same_fingerprint():
    fp1 = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE)
    fp2 = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE)
    assert fp1 == fp2


def test_different_line_number_same_fingerprint():
    """Same bug at different line numbers should produce same fingerprint."""
    fp1 = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE)
    fp2 = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE_DIFF_LINE)
    # Line numbers are normalized away
    assert fp1 == fp2


def test_different_error_type_different_fingerprint():
    fp1 = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE)
    fp2 = compute_fingerprint("ValueError", "ValueError: 'price'", STACK_TRACE)
    assert fp1 != fp2


def test_different_message_different_fingerprint():
    fp1 = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE)
    fp2 = compute_fingerprint("KeyError", "KeyError: 'name'", STACK_TRACE)
    assert fp1 != fp2


def test_uuid_in_message_normalized():
    """UUIDs in messages should be normalized so same bug with diff UUIDs -> same fingerprint."""
    fp1 = compute_fingerprint(
        "KeyError", "KeyError: '550e8400-e29b-41d4-a716-446655440000'", STACK_TRACE
    )
    fp2 = compute_fingerprint(
        "KeyError", "KeyError: 'aabbccdd-1234-5678-abcd-ef0123456789'", STACK_TRACE
    )
    assert fp1 == fp2


def test_fingerprint_is_16_hex_chars():
    fp = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE)
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_site_packages_frames_ignored():
    """Stack frames from site-packages should not affect fingerprint."""
    stack_with_libs = """  File "/usr/lib/python3.12/site-packages/fastapi/routing.py", line 100, in handle
    return handler()
  File "app/routes.py", line 24, in get_item
    return items[item_id]"""
    fp1 = compute_fingerprint("KeyError", "KeyError: 'price'", STACK_TRACE)
    fp2 = compute_fingerprint("KeyError", "KeyError: 'price'", stack_with_libs)
    assert fp1 == fp2
