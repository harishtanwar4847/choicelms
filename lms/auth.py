import frappe
from frappe import _
from frappe.auth import LoginManager
import lms
from frappe.utils.password import delete_login_failed_cache
from datetime import datetime, timedelta
from lms.firebase import FirebaseAdmin


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
			login_manager.authenticate(user=mobile, pwd=pin)
			token = dict(
					token=lms.generate_user_token(frappe.session.user),
					customer = lms.get_customer(mobile)
			)
			lms.create_user_token(firebase_token, mobile)
			return lms.generateResponse(message=_('Logged in Successfully'), data=token)

		lms.send_otp(mobile)

		return lms.generateResponse(message=_('OTP Send Successfully'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except frappe.AuthenticationError as e:
		return lms.generateResponse(status=401, message=_('Incorrect PIN'))
	except frappe.SecurityException as e:
		return lms.generateResponse(status=401, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def logout(firebase_token):
	get_user_token = frappe.db.get_value("User Token", {"token_type": "Firebase Token", "token": firebase_token})
	if not get_user_token:
		raise lms.ValidationError(_('Firebase Token does not exist.'))	
	else:
		frappe.db.set_value("User Token", otp_res[1], "used", 1)
		frappe.local.login_manager.logout()
		frappe.db.commit()

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

			return lms.generateResponse(status=422, message=_('Wrong OTP.'))

		login_manager.check_if_enabled(user_name)
		token = dict(
			token=lms.generate_user_token(user_name),
			customer = lms.get_customer(mobile)
		)
		lms.create_user_token(firebase_token, mobile)

		frappe.db.set_value("User Token", otp_res[1], "used", 1)
		delete_login_failed_cache(user_name)
		return lms.generateResponse(message=_('Login Success.'), data=token)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except frappe.SecurityException as e:
		return lms.generateResponse(status=401, message=str(e))
	except frappe.AuthenticationError as e:
		return lms.generateResponse(status=401, message=_('Mobile no. does not exist.'))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)


@frappe.whitelist(allow_guest=True)
def register(first_name, mobile, email, otp, firebase_token, last_name=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not first_name:
			raise lms.ValidationError(_('First Name is required.'))
		if not mobile:
			raise lms.ValidationError(_('Mobile is required.'))
		if not email:
			raise lms.ValidationError(_('Email is required.'))
		if not otp:
			raise lms.ValidationError(_('OTP is required.'))
		if not firebase_token:
			raise lms.ValidationError(_('Firebase Token is required.'))

		# if email id is correct, it returns the email id
		# if it is wrong, it returns empty string
		# empty string is a falsey value
		if not frappe.utils.validate_email_address(email):
			raise lms.ValidationError(_('Enter valid Email.'))
		if len(mobile) != 10 or not mobile.isdigit():
			raise lms.ValidationError(_('Enter valid Mobile.'))
		if len(otp) != 4 or not otp.isdigit():
			raise lms.ValidationError(_('Enter 4 digit OTP.'))

		# validating otp to protect sign up api
		otp_res = lms.check_user_token(entity=mobile, token=otp, token_type="OTP")
		if not otp_res[0]:
			raise lms.ValidationError(_('Wrong OTP'))

		if type(lms.get_user(mobile)) is str:
			raise lms.ValidationError(_('Mobile already Registered.'))
		if type(lms.get_user(email)) is str:
			raise lms.ValidationError(_('Email already Registered.'))

		# creating user
		user_name = lms.add_user(first_name, last_name, mobile, email)
		print(user_name)
		if type(user_name) is str:
			token = dict(
				token=lms.generate_user_token(user_name),
				customer = lms.get_customer(mobile)
			)
			lms.create_user_token(firebase_token, mobile)

			frappe.db.set_value("User Token", otp_res[1], "used", 1)

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

		send_verification_email_(frappe.session.user)

		return lms.generateResponse(message=_('Verification email sent'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

def send_verification_email_(email):
	user_token = frappe.get_doc({
			"doctype": "User Token",
			"token_type": "Email Verification Token",
			"entity": email,
			"token": lms.random_token(),
			"expiry": datetime.now() + timedelta(hours=1)
		})
	user_token.insert(ignore_permissions=True)

	template = "/templates/emails/user_email_verification.html"
	url = frappe.utils.get_url("/api/method/lms.auth.verify_user?token={}&user={}".format(user_token.token, email))

	frappe.enqueue(
		method=frappe.sendmail, 
		recipients=email, 
		sender=None, 
		subject="User Email Verification",
		message=frappe.get_template(template).render(url=url)
	)

@frappe.whitelist(allow_guest=True)
def verify_user(token, user):
	token_res = lms.check_user_token(entity=user, token=token, token_type="Email Verification Token")
	user_mobile = frappe.db.get_value('User', user, 'phone')

	if not token_res[0]:
		frappe.respond_as_web_page(
			_("Something went wrong"), 
			_("Your token is expired or invalid."),
			indicator_color='red'
		)
		return
	
	fa = FirebaseAdmin()
	fa.send_data(
		title='User Verification', 
		body='Your email was verified', 
		tokens=lms.get_firebase_tokens(user_mobile)
	)

	frappe.db.set_value("User Token", token_res[1], "used", 1)
	frappe.db.set_value("Customer", {"email": user}, "is_email_verified", 1)
	frappe.db.commit()
	frappe.respond_as_web_page(
			_("Success"), 
			_("User verified."),
			indicator_color='green'
		)