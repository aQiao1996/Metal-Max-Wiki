class BusinessError(Exception):
    """可向用户展示的业务失败。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
