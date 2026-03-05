class TopicAccessError(PermissionError):
    """Raised when a publisher tries to publish to a topic it doesn't own."""
    pass
