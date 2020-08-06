# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe import _
from traceback import format_exc
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from random import choice
from datetime import datetime
from itertools import groupby

__version__ = '0.0.1'

def after_install():
	frappe.db.set_value('System Settings', 'System Settings', 'allow_consecutive_login_attempts', 3)

class ValidationError(Exception):
	http_status_code = 422

class ServerError(Exception):
	http_status_code = 500

def validate_http_method(allowed_method_csv):
	if str(frappe.request.method).upper() not in allowed_method_csv.split(','):
		raise ValidationError(_('{} not allowed.').format(frappe.request.method))

def appErrorLog(title, error):
	d = frappe.get_doc({
		"doctype": "App Error Log",
		"title": str("User:") + str(title + " " + "App Error"),
		"error": format_exc()
	})
	d = d.insert(ignore_permissions=True)
	return d


def generateResponse(is_success=True, status=200, message=None, data=[], error=None):
	response = {}
	if is_success:
		response["status"] = int(status)
		response["message"] = message
		response["data"] = data
	else:
		appErrorLog(frappe.session.user, str(error))
		response["status"] = 500
		response["message"] = message or "Something Went Wrong"
		response["data"] = data
	return response

def send_otp(phone):
	try:
		# delete unused otp
		frappe.db.delete("User Token", {
			"entity": phone,
			"token_type": "OTP",
			"verified": 0
		})

		OTP_CODE = random_token()

		mess = _('Your OTP for LMS is {0}. Do not share your OTP with anyone.').format(OTP_CODE)
		frappe.enqueue(method=send_sms, receiver_list=[phone], msg=mess)

		otp_doc = frappe.get_doc(dict(
			doctype="User Token",
			entity=phone,
			token_type="OTP",
			token=OTP_CODE
		)).insert(ignore_permissions=True)
		
		if not otp_doc:
			raise ServerError(_('There was some problem while sending OTP. Please try again.'))
	except Exception as e:
		generateResponse(is_success=False, error=e)
		raise

def random_token(length=4):
	return ''.join(choice('0123456789') for _ in range(length))

def get_user(input, throw=False):
	user_data = frappe.db.sql("""select name from `tabUser` where email=%s or phone=%s""",(input,input), as_dict=1)
	print('get_user', frappe.as_json(user_data))
	if len(user_data) >= 1:
		return user_data[0].name
	else:
		if throw:
			raise ValidationError(_('Mobile no. does not exist.'))
		return False

def generate_user_secret(user_name):
	"""
	generate api key and api secret

	:param user: str
	"""
	user_details = frappe.get_doc("User", user_name)
	api_secret = frappe.generate_hash(length=15)
	# if api key is not set generate api key
	if not user_details.api_key:
		api_key = frappe.generate_hash(length=15)
		user_details.api_key = api_key
	user_details.api_secret = api_secret
	user_details.save(ignore_permissions=True)
	return api_secret

def generate_user_token(user_name):
	secret_key = generate_user_secret(user_name)
	api_key = frappe.db.get_value("User", user_name, "api_key")
	
	return "token {}:{}".format(api_key, secret_key)

def add_user(first_name, last_name, phone, email):
	try:
		user = frappe.get_doc(dict(
			doctype="User",
			email=email,
			first_name=first_name,
			last_name = last_name,
			username = str(phone),
			phone=phone,
			mobile_no=phone,
			send_welcome_email=0,
			new_password='{0}-{0}'.format(datetime.now().strftime('%s')),
			roles=[{"doctype": "Has Role", "role": "Loan Customer"}]
		)).insert(ignore_permissions=True)

		user_token = frappe.get_doc({
			"doctype": "User Token",
			"token_type": "Verification Token",
			"entity": email,
			"token": random_token(10),
		})
		user_token.insert(ignore_permissions=True)

		template = "/templates/emails/user_email_verification.html"
		url = frappe.utils.get_url("/api/method/lms.auth.verify_user?token={}&user={}".format(user_token.token, email))

		frappe.enqueue(
			method=frappe.sendmail, 
			recipients=email, 
			sender=None, 
			subject="User Verification",
			message=frappe.get_template(template).render(url=url)
		)

		return user.name
	except Exception:
		return False

def is_float_num_valid(num, length, precision):
	valid = True
	
	valid = True if type(num) is float else False
	
	num_str = str(num)
	if valid:
		valid = True if len(num_str.replace('.', '')) <= length else False

	if valid:
		valid = True if len(num_str.split('.')[1]) <= precision else False

	return valid

def get_cdsl_prf_no():
	return 'PF{}'.format(datetime.now().strftime('%s'))

def get_security_prices(securities=None):
	# sauce: https://stackoverflow.com/a/10030851/9403680
	if securities:
		securities_ = ''
		for s in securities:
			securities_ += "'{}',".format(s)
		query = """select security, price, time from `tabSecurity Price` inner join (
			select security as security_, max(time) as latest from `tabSecurity Price` where security in (%s) group by security_
			) res on time = res.latest and security = res.security_;""" % (securities_[:-1])
		results = frappe.db.sql(query, as_dict=1)
	else:
		query = """select security, price, time from `tabSecurity Price` inner join (
			select security as security_, max(time) as latest from `tabSecurity Price` group by security_
			) res on time = res.latest and security = res.security_;"""
		results = frappe.db.sql(query, as_dict=1)

	price_map = {}

	for r in results:
		price_map[r.security] = r.price

	return price_map

def chunk_doctype(doctype, limit):
	total = frappe.db.count(doctype)
	limit = 50
	chunks = range(0, total, limit)

	return {
		'total': total,
		'limit': limit,
		'chunks': chunks
	}