from utils.exceptions import APIException


class CustomerNotFoundException(APIException):
    http_status_code = 404

    def __init__(self, message="Customer not found"):
        self.message = message
