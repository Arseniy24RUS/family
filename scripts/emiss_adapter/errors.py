class EmissConnectorError(RuntimeError):
    def __init__(self, message, *, category="source_error", **kwargs):
        super().__init__(message)
        self.category = category
