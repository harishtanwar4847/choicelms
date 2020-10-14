import frappe
import lms
import utils

class Login(utils.APITestCase):
	@classmethod
	def setUpClass(cls):
		cls.mobile = '9876543210'
		cls.client = utils.FrappeClient('http://localhost:8003')

	def test_validation_error(self):
		res = self.client.post_api('lms.auth.login')
		self.assertValidationError(res)

	def test_otp_send(self):
		res = self.client.post_api('lms.auth.login', {'mobile': self.mobile})
		self.assertSuccess(res)

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete('User Token', {
			'entity': cls.mobile
		})

class VerifyOTP(utils.APITestCase):
	@classmethod
	def setUpClass(cls):
		cls.mobile = '9876543210'
		cls.client = utils.FrappeClient('http://localhost:8003')

	def test_validation_error(self):
		res = self.client.post_api('lms.auth.verify_otp')
		self.assertValidationError(res)

	def test_user_not_found(self):
		otp = lms.create_user_token(entity=self.mobile, token=lms.random_token(length=4, is_numeric=True))
		res = self.client.post_api('lms.auth.verify_otp', {'otp': otp.token, 'firebase_token': 'asdf', 'mobile': self.mobile})
		self.assertNotFound(res)
		self.assertRegex(res.text, 'User not found.')

	def test_otp_expired(self):
		otp = lms.create_user_token(entity=self.mobile, token=lms.random_token(length=4, is_numeric=True))
		from datetime import datetime, timedelta
		otp.expiry = datetime.now() - timedelta(minutes=1)
		otp.save(ignore_permissions=True)
		frappe.db.commit()
		res = self.client.post_api('lms.auth.verify_otp', {'otp': otp.token, 'firebase_token': 'asdf', 'mobile': self.mobile})
		self.assertUnauthorized(res)
		self.assertRegex(res.text, 'OTP Expired.')

	def test_wrong_otp(self):
		res = self.client.post_api('lms.auth.verify_otp', {'otp': 1234, 'firebase_token': 'asdf', 'mobile': self.mobile})
		print(res.text)
		self.assertUnauthorized(res)
		self.assertRegex(res.text, 'Invalid OTP.')

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete('User', {
			'username': cls.mobile
		})
		frappe.db.delete('User Token', {
			'entity': cls.mobile
		})