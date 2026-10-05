class GNSSParseError(ValueError):
    def __init__(self, message: str, *, file: str, line: int | None = None, column: int | None = None):
        location = file
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        self.file = file
        self.line = line
        self.column = column
        super().__init__(f"{location}: {message}")


