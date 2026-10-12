import re

PLATFORM_BY_CREDENTIAL = {
    "LinkedIn Integration": "LinkedIn",
    "Twitter Integration": "X (Twitter)",
    "Reddit Integration": "Reddit",
}

CREDENTIAL_BY_PLATFORM = {
    platform: credential_type
    for credential_type, platform in PLATFORM_BY_CREDENTIAL.items()
}


def get_platform(credential_type: str | None) -> str | None:
    return PLATFORM_BY_CREDENTIAL.get(credential_type)


# Markdown that LinkedIn and X would show literally. Hashtags (#tag) have no space, so they are kept.
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def to_platform_text(credential_type: str | None, content: str) -> str:
    """Strip markdown from AI output for platforms that do not render it (Reddit does)."""
    if not content or get_platform(credential_type) == "Reddit":
        return content
    return _HEADING.sub("", _BOLD.sub(r"\2", content))
