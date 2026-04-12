class ExtractionValidationError(Exception):
    """Pydantic rejected Claude's tool_use output."""
    def __init__(self, doc_type: str, validation_error: str, raw_input: dict):
        self.doc_type = doc_type
        self.raw_input = raw_input  # for logging — never surface to frontend
        super().__init__(f"Pydantic validation failed for {doc_type}: {validation_error}")


class LLMTimeoutError(Exception):
    """Claude API did not respond within timeout_seconds."""
    pass


class LLMRateLimitError(Exception):
    """Claude API rate limit hit. Worker should back off."""
    pass


class LLMAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Claude API error {status_code}: {message}")


class NoToolUseBlockError(LLMAPIError):
    """Claude responded but did not return a tool_use block.
    This violates our tool_choice='any' contract and should never happen
    under normal conditions. If it does, it signals a model or prompt issue."""
    def __init__(self, doc_type: str):
        super().__init__(0, f"Claude returned no tool_use block for doc_type={doc_type}")


class ExtractionServiceError(Exception):
    """DB insert or pipeline_jobs update failed after successful extraction."""
    pass
