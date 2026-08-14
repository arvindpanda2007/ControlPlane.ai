import re


class InjectionViolation(Exception):
    """Raised when a prompt appears to contain an injection attempt."""

    def __init__(self, matches: list[str]):
        self.matches = matches

        message = (
            "Potential prompt injection detected: "
            + ", ".join(matches)
        )

        super().__init__(message)


INJECTION_PATTERNS = {
    "ignore_previous_instructions": re.compile(
        r"\b(ignore|disregard|forget)\b.{0,50}"
        r"\b(previous|prior|above|system)\b.{0,50}"
        r"\b(instructions?|rules?)\b",
        re.IGNORECASE,
    ),

    "system_prompt_extraction": re.compile(
        r"\b(reveal|show|print|give|output)\b.{0,50}"
        r"\b(system\s+prompt|hidden\s+instructions?)\b",
        re.IGNORECASE,
    ),

    "developer_instruction_override": re.compile(
        r"\b(ignore|override|bypass)\b.{0,50}"
        r"\b(developer|system)\b.{0,50}"
        r"\b(instructions?|rules?)\b",
        re.IGNORECASE,
    ),
}


def scan_input(text: str) -> list[str]:
    """
    Scan user input for common prompt injection patterns.

    Returns a list of detected pattern names.
    """

    matches = []

    for name, pattern in INJECTION_PATTERNS.items():
        if pattern.search(text):
            matches.append(name)

    return matches


def check_input(text: str) -> None:
    """
    Raise InjectionViolation if suspicious injection patterns are detected.
    """

    matches = scan_input(text)

    if matches:
        raise InjectionViolation(matches)