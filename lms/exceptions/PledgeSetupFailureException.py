from utils.exceptions import APIException

class PledgeSetupFailureException(APIException):
	http_status_code = 500

	def __init__(self, message='A problem occured during pledge.'):
		self.message = message