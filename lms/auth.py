import frappe
from frappe import _
from frappe.auth import LoginManager
from frappe.auth import get_login_failed_count
import lms
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.utils.password import delete_login_failed_cache
from datetime import datetime, timedelta
from lms.firebase import FirebaseAdmin
from json import dumps


@frappe.whitelist(allow_guest=True)
def login(mobile, firebase_token, pin=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not mobile:
			raise lms.ValidationError(_('Mobile is required.'))
		if len(mobile) != 10 or not mobile.isdigit():
			raise lms.ValidationError(_('Enter valid Mobile.'))

		if pin:
			if not firebase_token:
				raise lms.ValidationError(_('Firebase Token is required.'))
			login_manager = LoginManager()
			user_name = lms.get_user(mobile)
			login_manager.authenticate(user=mobile, pwd=pin)
			token = dict(
				token=lms.generate_user_token(user_name),
				customer = lms.get_customer(mobile)
			)
			lms.add_firebase_token(firebase_token, user_name)
			
			return lms.generateResponse(message=_('Logged in Successfully'), data=token)

		lms.send_otp(mobile)

		return lms.generateResponse(message=_('OTP Send Successfully'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))	
	except frappe.AuthenticationError as e:
		return lms.generateResponse(status=401, message=_('Incorrect PIN'), data={'invalid_attempts': get_login_failed_count(user_name)})
	except frappe.SecurityException as e:
		mess = _('There are 3 time wrong attempt.')
		frappe.enqueue(method=send_sms, receiver_list=[mobile], msg=mess)
		return lms.generateResponse(status=401, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def logout(firebase_token):
	get_user_token = frappe.db.get_value("User Token", {"token_type": "Firebase Token", "token": firebase_token})
	print(get_user_token)
	if not get_user_token:
		raise lms.ValidationError(_('Firebase Token does not exist.'))	
	else:
		frappe.db.set_value("User Token", get_user_token, "used", 1)
		# filters = {'name': frappe.session.user}
		frappe.db.sql(""" delete from `__Auth` where doctype='User' and name='{}' and fieldname='api_secret' """.format(frappe.session.user) )
		frappe.local.login_manager.logout()
		frappe.db.commit()
		return lms.generateResponse(message=_('Logged out Successfully'))

@frappe.whitelist(allow_guest=True)
def verify_otp(mobile, firebase_token, otp):
	try:
		# validation
		lms.validate_http_method('POST')

		if not mobile:
			raise lms.ValidationError(_('Mobile is required.'))
		if not otp:
			raise lms.ValidationError(_('OTP is required.'))
		if len(mobile) != 10 or not mobile.isdigit():
			raise lms.ValidationError(_('Enter valid Mobile.'))
		if not firebase_token:
			raise lms.ValidationError(_('Firebase Token is required.'))
		if len(otp) != 4 or not otp.isdigit():
			raise lms.ValidationError(_('Enter 4 digit OTP.'))

		login_manager = LoginManager()
		user_name = lms.get_user(mobile)
		otp_res = lms.check_user_token(entity=mobile, token=otp, token_type="OTP")
		if not otp_res[0]:
			if user_name:
				login_manager.update_invalid_login(user_name)
				login_manager.check_if_enabled(user_name)

			return lms.generateResponse(status=422, message=_('Either OTP is invalid or expire'), data={'invalid_attempts': get_login_failed_count(user_name)})

		login_manager.check_if_enabled(user_name)
		token = dict(
			token=lms.generate_user_token(user_name),
			customer = lms.get_customer(mobile)
		)
		lms.add_firebase_token(firebase_token, user_name)

		frappe.db.set_value("User Token", otp_res[1], "used", 1)
		delete_login_failed_cache(user_name)
		return lms.generateResponse(message=_('Login Success.'), data=token)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except frappe.SecurityException as e:
		mess = _('There are 3 time wrong attempt.')
		frappe.enqueue(method=send_sms, receiver_list=[mobile], msg=mess)
		return lms.generateResponse(status=401, message=str(e))
	except frappe.AuthenticationError as e:
		return lms.generateResponse(status=401, message=_('Mobile no. does not exist.'))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)


@frappe.whitelist(allow_guest=True)
def register(first_name, mobile, email, firebase_token, last_name=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not first_name:
			raise lms.ValidationError(_('First Name is required.'))
		if not mobile:
			raise lms.ValidationError(_('Mobile is required.'))
		if not email:
			raise lms.ValidationError(_('Email is required.'))
		if not firebase_token:
			raise lms.ValidationError(_('Firebase Token is required.'))

		# if email id is correct, it returns the email id
		# if it is wrong, it returns empty string
		# empty string is a falsey value
		if not frappe.utils.validate_email_address(email):
			raise lms.ValidationError(_('Enter valid Email.'))
		if len(mobile) != 10 or not mobile.isdigit():
			raise lms.ValidationError(_('Enter valid Mobile.'))
	
		# validating otp to protect sign up api
		# otp_res = lms.check_user_token(entity=mobile, token=otp, token_type="OTP")
		# if not otp_res[0]:
		# 	raise lms.ValidationError(_('Wrong OTP'))

		if type(lms.get_user(mobile)) is str:
			raise lms.ValidationError(_('Mobile already Registered.'))
		if type(lms.get_user(email)) is str:
			raise lms.ValidationError(_('Email already Registered.'))

		# creating user
		user_name = lms.add_user(first_name, last_name, mobile, email)
		if type(user_name) is str:
			token = dict(
				token=lms.generate_user_token(user_name),
				customer = lms.get_customer(mobile)
			)
			lms.add_firebase_token(firebase_token, user_name)

			# frappe.db.set_value("User Token", otp_res[1], "used", 1)

			return lms.generateResponse(message=_('Registered Successfully.'), data=token)
		else:
			return lms.generateResponse(status=500, message=_('Something Wrong During User Creation. Try Again.'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def request_verification_email():
	try:
		# validation
		lms.validate_http_method('POST')

		lms.create_user_token(entity=frappe.session.user, token=lms.random_token(), token_type="Email Verification Token")

		return lms.generateResponse(message=_('Verification email sent'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist(allow_guest=True)
def verify_user(token, user):
	token_res = lms.check_user_token(entity=user, token=token, token_type="Email Verification Token")

	if not token_res[0]:
		frappe.respond_as_web_page(
			_("Something went wrong"), 
			_("Your token is expired or invalid."),
			indicator_color='red'
		)
		return

	frappe.db.set_value("User Token", token_res[1], "used", 1)
	customer = lms.get_customer(user)
	customer.is_email_verified = 1
	customer.save(ignore_permissions=True)
	frappe.db.commit()
	
	frappe.respond_as_web_page(
			_("Success"), 
			_("User verified."),
			indicator_color='green'
		)