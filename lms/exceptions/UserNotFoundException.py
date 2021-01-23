from utils.exceptions.APIException import APIException


class UserNotFoundException(APIException):
    http_status_code = 404
    save_error_log = False

    def __init__(self, message="User not found"):
        self.message = message
