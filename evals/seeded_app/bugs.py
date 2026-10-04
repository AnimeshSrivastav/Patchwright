from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Bug:
    id: str
    endpoint: str
    description: str
    error_type: str
    fix_description: str
    category: str  # "system_error" | "user_error" | "infra"


BUGS: list[Bug] = [
    Bug("BUG001", "/items/{item_id}", "KeyError on missing dict key", "KeyError",
        "Use .get() with a default or check key existence", "system_error"),
    Bug("BUG002", "/divide/{a}/{b}", "Division by zero when b=0", "ZeroDivisionError",
        "Add guard: if b == 0: raise HTTPException(400)", "system_error"),
    Bug("BUG003", "/users/{user_id}/profile", "AttributeError on None user", "AttributeError",
        "Check if user is None before accessing .name", "system_error"),
    Bug("BUG004", "/products", "IndexError on empty product list", "IndexError",
        "Check list length before accessing [0]", "system_error"),
    Bug("BUG005", "/orders/{order_id}/total", "TypeError: unsupported operand (str + int)", "TypeError",
        "Cast price to float before summing", "system_error"),
    Bug("BUG006", "/search", "ValueError: invalid literal for int()", "ValueError",
        "Validate query param is numeric before int()", "system_error"),
    Bug("BUG007", "/config", "KeyError in os.environ access", "KeyError",
        "Use os.environ.get() with fallback", "system_error"),
    Bug("BUG008", "/reports/daily", "NameError: name 'df' is not defined", "NameError",
        "Fix variable scoping — df defined inside if block not accessible outside", "system_error"),
    Bug("BUG009", "/auth/verify", "RecursionError in token parsing", "RecursionError",
        "Add base case to recursive token decode function", "system_error"),
    Bug("BUG010", "/files/{filename}", "OverflowError in file size calculation", "OverflowError",
        "Use integer division for byte conversion", "system_error"),
    Bug("BUG011", "/metrics/average", "ZeroDivisionError: mean of empty list", "ZeroDivisionError",
        "Return 0 or None when list is empty", "system_error"),
    Bug("BUG012", "/users/batch", "TypeError: object is not subscriptable (None)", "TypeError",
        "Ensure batch endpoint returns [] not None on empty", "system_error"),
    Bug("BUG013", "/cache/flush", "AttributeError: NoneType has no attribute 'clear'", "AttributeError",
        "Initialize cache to {} not None", "system_error"),
    Bug("BUG014", "/notifications/send", "KeyError: 'email' missing from payload", "KeyError",
        "Validate required fields before accessing payload", "system_error"),
    Bug("BUG015", "/stats/percentile", "IndexError: list index out of range", "IndexError",
        "Clamp percentile index to valid range", "system_error"),
    # User errors (4xx) — router should ignore these
    Bug("BUG016", "/items/notanumber", "Client sends non-int item_id", "ValueError",
        "FastAPI handles this — return 422 automatically", "user_error"),
    Bug("BUG017", "/protected", "Missing auth header", "HTTPException",
        "Client error — return 401", "user_error"),
    # Infra-style — router should send to reporter
    Bug("BUG018", "/db/query", "Simulated DB connection refused", "ConnectionRefusedError",
        "Infra issue — requires ops intervention", "infra"),
    Bug("BUG019", "/external/api", "Upstream timeout simulation", "TimeoutError",
        "Infra issue — circuit breaker or retry policy", "infra"),
    # Tricky 4xx that are actually our bug
    Bug("BUG020", "/validate/age", "Our validation rejects valid input (off-by-one)", "HTTPException",
        "Fix validation boundary: age >= 0, not age > 0", "system_error"),
]
