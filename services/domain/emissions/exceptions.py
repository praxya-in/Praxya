class FactorNotFoundError(Exception):
    def __init__(self, process_id: str):
        self.process_id = process_id
        super().__init__(
            f"No emission factor found for process_id='{process_id}'. "
            "Human input required — do not approximate."
        )


class CalculationInputError(Exception):
    pass
