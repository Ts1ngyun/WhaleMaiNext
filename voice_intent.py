def explicit_voice_request(content):
    """Only the literal, case-sensitive /v marker authorizes voice."""
    return '/v' in str(content)
