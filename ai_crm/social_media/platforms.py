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
