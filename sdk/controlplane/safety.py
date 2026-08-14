import re


class SafetyViolation(Exception):
    """Raised when an LLM response contains sensitive information."""

    def __init__(self, violations: list[str]):
        self.violations = violations

        message = (
            "Sensitive information detected: "
            + ", ".join(violations)
        )

        super().__init__(message)


SECRET_PATTERNS = {
    "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
}


def scan_output(text: str) -> list[str]:
    """
    Scan LLM output for sensitive information.

    Returns a list of detected violation types.
    """

    violations = []

    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            violations.append(name)

    return violations


def check_output(text: str) -> None:
    """
    Raise SafetyViolation if sensitive information is detected.
    """

    violations = scan_output(text)

    if violations:
        raise SafetyViolation(violations)