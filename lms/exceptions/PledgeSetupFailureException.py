from utils.exceptions import APIException


class PledgeSetupFailureException(APIException):
    http_status_code = 500

    def __init__(self, message="A problem occured during pledge.", errors=None):
        self.message = message
        if errors:
            self.errors = errors
