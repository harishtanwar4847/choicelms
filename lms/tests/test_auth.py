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
		cls.client = utils.FrappeClient('http://localhost:8000')
		cls.first_name="Neel"
		cls.last_name="Bhanushali"
		cls.mobile = '9876543210'
		cls.email="neal.bhanushali@atritechnocrat.in"
		# cls.mobile = '7506253632'
		# cls.email="iccha.konalkar@atritechnocrat.in"

	def test_validation_error(self):
		res = self.client.post_api("lms.auth.register", {'email':''})
		print("test_validation_error",res.text)
		self.assertValidationError(res)
	
	def test_mobile_exist(self):
		res = self.client.post_api("lms.auth.register",{'firebase_token': 'asdf', 'first_name': self.first_name,'last_name': self.last_name, 'mobile': '7506253632', 'email':self.email})
		self.assertValidationError(res)
		self.assertRegex(res.text, 'Mobile already taken')

	def test_email_exist(self):
		res = self.client.post_api("lms.auth.register",{'firebase_token': 'asdf', 'first_name': self.first_name,'last_name': self.last_name, 'mobile': self.mobile, 'email':"iccha.konalkar12@atritechnocrat.in"})
		self.assertValidationError(res)
		self.assertRegex(res.text, 'Email already taken')
	
	def test_register_success(self):
		res = self.client.post_api("lms.auth.register",{'firebase_token': 'cSQk2fGpS76sEaCiuSnoss:APA91bFK2wlTBuH6Xi5Di5w4QJpd0hithe8z2y43eVs7kAliac8eRhaAjY-cSQk2fGpS76sEaCiuSnoss:APA91bFK2wlTBuH6Xi5Di5w4QJpd0hithe8z2y43eVs7kAliac8eRhaAjY-AFmhJmWQ454rl9W6Zr85c4ziX76_ymAj8617Zu2PGJWBM347pfMmW_zOMoAQ1d0ylyWmY2e03W5AHDLCO', 'first_name': self.first_name,'last_name': self.last_name, 'mobile': self.mobile, 'email':self.email})
		print("test_register_success",res.text)
		self.assertSuccess(res)

	@classmethod
	def tearDownClass(cls):
		frappe.db.delete('User', {
			'name': cls.email
		})
		frappe.db.delete('User Token', {
			'entity': cls.mobile
		})