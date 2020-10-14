import frappe
import lms
import utils

class Login(utils.APITestCase):
	@classmethod
	def setUpClass(cls):
		cls.mobile = '9876543210'
		cls.client = utils.FrappeClient('http://localhost:8000')

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
		cls.client = utils.FrappeClient('http://localhost:8000')

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

class Register(utils.APITestCase):
	@classmethod
	def setUpClass(cls):
		cls.first_name="Neel"
		cls.last_name="Bhanushali"
		cls.mobile = '9876543210'
		# cls.mobile = '7506253632'
		# cls.mobile = ''
		cls.email="neal.bhanushali@atritechnocrat.in"
		# cls.email="iccha.konalkar@atritechnocrat.in"
		# cls.email = ''
		cls.client = utils.FrappeClient('http://localhost:8000')

	def test_validation_error(self):
		res = self.client.post_api("lms.auth.register")
		self.assertValidationError(res)
	
	def test_mobile_exist(self):
		res = self.client.post_api("lms.auth.register",{'firebase_token': 'asdf', 'first_name': self.first_name,'last_name': self.last_name, 'mobile': self.mobile, 'email':self.email})
		print(res.text)
		self.assertValidationError(res)
		self.assertRegex(res.text, 'Mobile already taken.')

	# def test_email_exist(self):
	# 	res = self.client.get_api("lms.auth.register")
	# 	self.assertValidationError(res)
	# 	self.assertRegex(res.text, 'User not found.')

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete('User', {
			'name': cls.email
		})
		frappe.db.delete('User Token', {
			'entity': cls.mobile
		})