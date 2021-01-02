from utils.exceptions import APIException


class UserKYCNotFoundException(APIException):
    http_status_code = 404

    def __init__(self, message="User KYC not found"):
        self.message = message
