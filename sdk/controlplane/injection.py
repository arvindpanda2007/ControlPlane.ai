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
    # Examples:
    #   ignore previous instructions
    #   disregard prior rules
    #   forget above instructions
    "ignore_previous_instructions": re.compile(
        r"\b(ignore|disregard|forget)\b"
        r"(?:.{0,50})?"
        r"\b(previous|prior|above)\b"
        r"(?:.{0,50})?"
        r"\b(instructions?|rules?)\b",
        re.IGNORECASE,
    ),

    # Examples:
    #   ignore system prompt
    #   override developer instructions
    #   bypass system rules
    #   disregard system prompt
    "system_prompt_override": re.compile(
        r"\b(ignore|override|bypass|disregard|forget)\b"
        r"(?:.{0,50})?"
        r"\b(system|developer)\b"
        r"(?:.{0,20})?"
        r"\b(prompt|instructions?|rules?)\b",
        re.IGNORECASE,
    ),

    # Examples:
    #   reveal system prompt
    #   show system prompt
    #   give me the system prompt
    #   share system prompt
    #   print hidden instructions
    #   display developer prompt
    "system_prompt_extraction": re.compile(
        r"\b(reveal|show|print|give|share|output|display|tell)\b"
        r"(?:.{0,50})?"
        r"\b("
        r"system\s+prompt|"
        r"hidden\s+instructions?|"
        r"developer\s+prompt"
        r")\b",
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
    Raise InjectionViolation if suspicious injection patterns
    are detected.
    """

    matches = scan_input(text)

    if matches:
        raise InjectionViolation(matches)