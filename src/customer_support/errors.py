"""Safe errors shared by the graph and transport without circular imports."""


class CustomerSupportModelError(RuntimeError):
    """A real provider failed; no alternate provider or mock response was used."""

    def __init__(self) -> None:
        super().__init__(
            "Customer support model call failed. Check provider connectivity, credentials "
            "and model availability. No fallback was used."
        )
