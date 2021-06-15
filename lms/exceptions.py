from utils.exceptions.APIException import APIException


class CustomerNotFoundException(APIException):
    http_status_code = 404

    def __init__(self, message="Customer not found"):
        self.message = message


class InvalidUserTokenException(APIException):
    http_status_code = 422
    save_error_log = False

    def __init__(self, message):
        self.message = message


class PledgeSetupFailureException(APIException):
    http_status_code = 500

    def __init__(self, message="A problem occured during pledge.", errors=None):
        self.message = message
        if errors:
            self.errors = errors


class UserKYCNotFoundException(APIException):
    http_status_code = 404

    def __init__(self, message="User KYC not found"):
        self.message = message


class UserNotFoundException(APIException):
    http_status_code = 404
    save_error_log = False

    def __init__(self, message="User not found"):
        self.message = message
