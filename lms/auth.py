import frappe
from frappe import _
from frappe.auth import LoginManager
import lms
from frappe.utils.password import delete_login_failed_cache


@frappe.whitelist(allow_guest=True)
def login(mobile, pin=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not mobile:
			raise lms.ValidationError(_('Mobile is required.'))
		if len(mobile) != 10 or not mobile.isdigit():
			raise lms.ValidationError(_('Enter valid Mobile.'))

		if pin:
			login_manager = LoginManager()
			login_manager.authenticate(user=mobile, pwd=pin)

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


@frappe.whitelist(allow_guest=True)
def verify_otp(mobile, otp):
	try:
		# validation
		lms.validate_http_method('POST')

		if not mobile:
			raise lms.ValidationError(_('Mobile is required.'))
		if not otp:
			raise lms.ValidationError(_('OTP is required.'))
		if len(mobile) != 10 or not mobile.isdigit():
			raise lms.ValidationError(_('Enter valid Mobile.'))
		if len(otp) != 4 or not otp.isdigit():
			raise lms.ValidationError(_('Enter 4 digit OTP.'))

		login_manager = LoginManager()
		user_name = lms.get_user(mobile)
		otpobj = frappe.db.get_all("User Token", {"entity": mobile, "token_type": "OTP", "token": otp, "verified": 0})
		if len(otpobj) == 0:
			if user_name:
				login_manager.update_invalid_login(user_name)
				login_manager.check_if_enabled(user_name)

			return lms.generateResponse(status=422, message=_('Wrong OTP.'))

		login_manager.check_if_enabled(user_name)
		token = dict(
			token=lms.generate_user_token(user_name),
		)

		frappe.db.set_value("User Token", otpobj[0].name, "verified", 1)
		delete_login_failed_cache(user_name)
		return lms.generateResponse(message=_('Login Success.'), data=token)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except frappe.SecurityException as e:
		return lms.generateResponse(status=401, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)


@frappe.whitelist(allow_guest=True)
def register(first_name, phone, email, otp, last_name=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not first_name:
			raise lms.ValidationError(_('First Name is required.'))
		if not phone:
			raise lms.ValidationError(_('Phone is required.'))
		if not email:
			raise lms.ValidationError(_('Email is required.'))
		if not otp:
			raise lms.ValidationError(_('OTP is required.'))

		# if email id is correct, it returns the email id
		# if it is wrong, it returns empty string
		# empty string is a falsey value
		if not frappe.utils.validate_email_address(email):
			raise lms.ValidationError(_('Enter valid Email.'))
		if len(phone) != 10 or not phone.isdigit():
			raise lms.ValidationError(_('Enter valid Phone.'))
		if len(otp) != 4 or not otp.isdigit():
			raise lms.ValidationError(_('Enter 4 digit OTP.'))

		if type(lms.get_user(phone)) is str:
			raise lms.ValidationError(_('Mobile already Registered.'))
		if type(lms.get_user(email)) is str:
			raise lms.ValidationError(_('Email already Registered.'))

		# validating otp to protect sign up api
		otpobj = frappe.db.get_all("User Token", {"entity": phone, "token_type": "OTP", "token": otp, "verified": 0})
		if len(otpobj) == 0:
			raise lms.ValidationError(_('Wrong OTP'))

		# creating user
		user_name = lms.add_user(first_name, last_name, phone, email)
		if type(user_name) is str:
			token = dict(
				token=lms.generate_user_token(user_name),
			)

			frappe.db.set_value("User Token", otpobj[0].name, "verified", 1)

			return lms.generateResponse(message=_('Registered Successfully.'), data=token)
		else:
			return lms.generateResponse(status=500, message="Something Wrong During User Creation. Try Again.")
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist(allow_guest=True)
def verify_user(token, user):
	tokenlist = frappe.db.get_all("User Token", {"entity": user, "token_type": "Verification Token", "token": token, "verified": 0})

	if len(tokenlist) == 0:
		frappe.respond_as_web_page(
			_("Something went wrong"), 
			_("Your token is expired or invalid."),
			indicator_color='red'
		)
		return
	
	frappe.db.set_value("User Token", tokenlist[0].name, "verified", 1)
	frappe.db.commit()
	frappe.respond_as_web_page(
			_("Success"), 
			_("User verified."),
			indicator_color='green'
		)