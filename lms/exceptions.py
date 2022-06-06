import frappe
from utils.exceptions import APIException


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


class NotFoundException(APIException):
    http_status_code = 404
    message = frappe._("Data not found")
    save_error_log = False


class ForbiddenException(APIException):
    http_status_code = 403
    message = frappe._("Please check the entered data")
    save_error_log = False


class UnauthorizedException(APIException):
    http_status_code = 401
    message = frappe._("Data expired")
    save_error_log = False


class FailureException(APIException):
    http_status_code = 422
    message = frappe._("Something went wrong")
    save_error_log = False


class RespondFailureException(APIException):
    http_status_code = 417
    message = frappe._("Something went wrong")
    save_error_log = False


class RespondWithFailureException(APIException):
    http_status_code = 500
    message = frappe._("Something went wrong")
    save_error_log = False
