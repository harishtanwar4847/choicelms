# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe import _
from traceback import format_exc
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from random import choice
from datetime import datetime, timedelta
from itertools import groupby
from lms.auth import send_verification_email_

__version__ = '0.0.1'

def after_install():
	frappe.db.set_value('System Settings', 'System Settings', 'allow_consecutive_login_attempts', 3)

	frappe.db.set_value('Contact Us Settings', None, 'forward_to_email', 'erp@atritechnocrat.in')

class ValidationError(Exception):
	http_status_code = 422

class ServerError(Exception):
	http_status_code = 500

class FirebaseError(Exception):
	pass

class FirebaseCredentialsFileNotFoundError(FirebaseError):
	pass

class InvalidFirebaseCredentialsError(FirebaseError):
	pass

class FirebaseTokensNotProvidedError(FirebaseError):
	pass

class FirebaseDataNotProvidedError(FirebaseError):
	pass

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
			"used": 0
		})

		OTP_CODE = random_token(length=4, is_numeric=True)

		mess = _('Your OTP for LMS is {0}. Do not share your OTP with anyone.').format(OTP_CODE)
		frappe.enqueue(method=send_sms, receiver_list=[phone], msg=mess)

		otp_doc = frappe.get_doc(dict(
			doctype="User Token",
			entity=phone,
			token_type="OTP",
			token=OTP_CODE,
			expiry= datetime.now() + timedelta(minutes=10)
		)).insert(ignore_permissions=True)
		
		if not otp_doc:
			raise ServerError(_('There was some problem while sending OTP. Please try again.'))
	except Exception as e:
		generateResponse(is_success=False, error=e)
		raise

def check_user_token(entity, token, token_type):
	if token_type == "Firebase Token":
		otp_list = frappe.db.get_all("User Token", {"entity": entity, "token_type": token_type, "token": token, "used": 0})
	else:	
		otp_list = frappe.db.get_all("User Token", {"entity": entity, "token_type": token_type, "token": token, "used": 0, "expiry": ('>', datetime.now())})

	if len(otp_list) == 0:
		return False, None

	return True, otp_list[0].name

def get_firebase_tokens(entity):
	token_list = frappe.db.get_all('User Token', filters={'entity': entity, 'token_type': 'Firebase Token'}, fields=['token'])

	return [i.token for i in token_list]

def random_token(length=10, is_numeric=False):
	set_ = '0123456789'
	if not is_numeric:
		set_ = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
	return ''.join(choice(set_) for _ in range(length))

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

		customer = frappe.get_doc(dict(
			doctype="Customer",
			username = user.email,
			owner = user.email
		)).insert(ignore_permissions=True)

		send_verification_email_(email)

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

def convert_list_to_tuple_string(list_):
	tuple_string = ''

	for i in list_:
		tuple_string += "'{}',".format(i)

	return '({})'.format(tuple_string[:-1])

def get_security_prices(securities=None):
	# sauce: https://stackoverflow.com/a/10030851/9403680
	if securities:
		query = """select security, price, time from `tabSecurity Price` inner join (
			select security as security_, max(time) as latest from `tabSecurity Price` where security in {} group by security_
			) res on time = res.latest and security = res.security_;""".format(convert_list_to_tuple_string(securities))
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

def get_security_categories(securities):
	query = """select isin, category from `tabAllowed Security` where isin in {}""".format(convert_list_to_tuple_string(securities))

	results = frappe.db.sql(query, as_dict=1)

	security_map = {}
	
	for r in results:
		security_map[r.isin] = r.category

	return security_map

def chunk_doctype(doctype, limit):
	total = frappe.db.count(doctype)
	limit = 50
	chunks = range(0, total, limit)

	return {
		'total': total,
		'limit': limit,
		'chunks': chunks
	}

def get_customer(mobile):
	customer_list = frappe.get_all('Customer', filters={'phone': mobile}, fields=['*'])
	return customer_list[0]

def delete_user(doc, method):
	print('=======================')
	customer = get_customer(doc.phone)
	frappe.delete_doc('Customer', customer.name)

def create_user_token(firebase_token, user=None):
	get_user_token = frappe.db.get_value("User Token", {"token_type": "Firebase Token", "token": firebase_token})
	if get_user_token:
		return 
	user_token = frappe.get_doc({
				"doctype": "User Token",
				"token_type": "Firebase Token",
				"entity": user or frappe.session.user,
				"token": firebase_token,
				"expiry": ""
				})
	user_token.insert(ignore_permissions=True)	