class ConversationNotFoundError(LookupError):
    pass


class RetrievalError(RuntimeError):
    pass


class AIServiceUnavailableError(RuntimeError):
    pass