# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe import _
from traceback import format_exc
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from random import choice
from datetime import datetime, timedelta
from itertools import groupby
from .exceptions import *
import utils

__version__ = '1.0.0'

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


def generateResponse(is_success=True, status=200, message=None, data={}, error=None):
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

def send_otp(entity):
	try:
		OTP_CODE = random_token(length=4, is_numeric=True)
		otp_doc = create_user_token(entity=entity, token=OTP_CODE)
		
		if not otp_doc:
			raise ServerError(_('There was some problem while sending OTP. Please try again.'))
	except Exception as e:
		generateResponse(is_success=False, error=e)
		raise

def verify_user_token(entity, token, token_type):
	filters = {
		'entity': entity,
		'token': token,
		'token_type': token_type,
		'used': 0
	}

	token_name = frappe.db.get_value('User Token', filters, 'name')

	if not token_name:
		raise InvalidUserTokenException('Invalid {}'.format(token_type))

	return frappe.get_doc('User Token', token_name)
	

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

def __user(input=None):
	# get session user if input is not provided
	if not input:
		input=frappe.session.user
	res = frappe.get_all('User', or_filters={'email': input, 'username': input})
	
	if len((res)) == 0:
		raise UserNotFoundException

	return frappe.get_doc('User', res[0].name)

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

def create_user(first_name, last_name, mobile, email):
	try:
		user = frappe.get_doc({
			'doctype': 'User',
			'email': email,
			'first_name': first_name,
			'last_name': last_name,
			'username': mobile,
			'phone': mobile,
			'mobile_no': mobile,
			'send_welcome_email': 0,
			'new_password': frappe.mock('password'),
			'roles': [{"doctype": "Has Role", "role": "Loan Customer"}]
		}).insert(ignore_permissions=True)

		return user
	except Exception as e:
		raise utils.exceptions.APIException(message=str(e))

def create_customer(user):
	try:
		customer = frappe.get_doc({
			'doctype': "Customer",
			'username': user.email
		}).insert(ignore_permissions=True)

		return customer
	except Exception as e:
		frappe.delete_doc('User', user.name)
		raise utils.exceptions.APIException(message=str(e))

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

		create_user_token(entity=email, token=random_token(), token_type="Email Verification Token")
		
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

def get_security_categories(securities, lender):
	query = """select isin, category from `tabAllowed Security`
				where 
				lender = '{}' and
				isin in {}""".format(lender, convert_list_to_tuple_string(securities))

	results = frappe.db.sql(query, as_dict=1)

	security_map = {}
	
	for r in results:
		security_map[r.isin] = r.category

	return security_map

def get_allowed_securities(securities, lender):
	query = """select 
				allowed.isin, allowed.security_name, allowed.eligible_percentage,
				master.category
				from `tabAllowed Security` allowed
				left join `tabSecurity` master
				on allowed.isin = master.isin 
				where 
				allowed.lender = '{}' and
				allowed.isin in {}""".format(lender, convert_list_to_tuple_string(securities))

	results = frappe.db.sql(query, as_dict=1)

	security_map = {}
	
	for r in results:
		security_map[r.isin] = r

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

def __customer(entity=None):
	res = frappe.get_all('Customer', filters={'username': __user(entity).name})

	if len(res) == 0:
		raise CustomerNotFoundException

	return frappe.get_doc('Customer', res[0].name)

def __user_kyc(entity=None, pan_no=None, throw=True):
	filters = {'user': __user(entity).name}
	if pan_no:
		filters['pan_no'] = pan_no
	res = frappe.get_all('User KYC', filters=filters, order_by='creation desc')

	if len(res) == 0:
		if throw:
			raise UserKYCNotFoundException
		return frappe.get_doc({
			'doctype': 'User KYC',
			'user': filters['user']
		})

	return frappe.get_doc('User KYC', res[0].name)

def __banks(user_kyc=None):
	if not user_kyc:
		user_kyc = __user_kyc().name

	res = frappe.get_all('Bank Account', filters={'user_kyc': user_kyc}, fields=['*'])

	for i in res:
		i.creation = str(i.creation)
		i.modified = str(i.modified)

	return res

def round_down_amount_to_nearest_thousand(amount):
	return float(int(amount/1000) * 1000)

def get_customer(entity):
	customer_list = frappe.get_all('Customer', filters={'username': get_user(entity)})
	return frappe.get_doc('Customer', customer_list[0].name)

def delete_user(doc, method):
	customer = get_customer(doc.phone)
	frappe.delete_doc('Customer', customer.name)

def add_firebase_token(firebase_token, user=None):
	if not user:
		user = frappe.session.user
	get_user_token = frappe.db.get_value("User Token", {"token_type": "Firebase Token", "token": firebase_token, "entity": user})
	if get_user_token:
		return 
	
	create_user_token(entity=user, token=firebase_token, token_type='Firebase Token')

def create_user_token(entity, token, token_type="OTP"):
	expiry_map = {
		'OTP': 2,
		'Email Verification Token': 60,
		'Pledge OTP': 2,
		'Withdraw OTP': 2,
	}

	doc_data = {
		'doctype': 'User Token',
		'entity': entity,
		'token': token,
		'token_type': token_type
	}

	expiry_in_minutes = expiry_map.get(token_type, None)
	if expiry_in_minutes:
		# expire previous OTPs
		frappe.db.sql("""
			update `tabUser Token` set expiry = CURRENT_TIMESTAMP
			where entity = '{entity}' and token_type = '{token_type}' and expiry > CURRENT_TIMESTAMP; 
		""".format(entity=entity, token_type=token_type))
		doc_data['expiry'] = datetime.now() + timedelta(minutes=expiry_in_minutes)
	
	user_token = frappe.get_doc(doc_data)
	user_token.save(ignore_permissions=True)
	frappe.db.commit()

	return user_token
	
def loan_timeline(loan_name):
	if not loan_name:
		frappe.throw(_('Loan Name is required.'))

	loan = frappe.get_doc('Loan', loan_name)

	loan_timeline = frappe.get_doc(dict(
		doctype = "Loan Timeline",
		total_collateral_value = loan.total_collateral_value,
		drawing_power = loan.drawing_power,
		pledgor_boid = loan.pledgor_boid,
		prf_number = loan.prf_number,
		allowable_ltv = loan.allowable_ltv,
		pledgee_boid = loan.pledgee_boid,
		expiry_date = loan.expiry_date,
		items = loan.items
	)).insert(ignore_permissions=True)

	return loan_timeline

def save_signed_document(file_id, doctype, docname):
	las_settings = frappe.get_single('LAS Settings')
	loan_aggrement_file = las_settings.esign_download_signed_file_url.format(file_id=file_id)
	file_ = frappe.get_doc({
		'doctype': 'File',
		'attached_to_doctype': doctype,
		'attached_to_name': docname,
		'file_url': loan_aggrement_file,
		'file_name': 'loan-aggrement.pdf'
	})
	file_.insert(ignore_permissions=True)