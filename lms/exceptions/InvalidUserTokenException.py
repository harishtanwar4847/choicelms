from utils.exceptions import APIException


class InvalidUserTokenException(APIException):
    http_status_code = 422
    save_error_log = False

    def __init__(self, message):
        self.message = message
