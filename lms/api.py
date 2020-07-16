from __future__ import unicode_literals
import frappe
from frappe.utils import cint, get_gravatar, get_url, format_datetime, now_datetime, add_days, today, formatdate, \
	date_diff, getdate, get_last_day, get_first_day, flt, nowdate,nowtime
from frappe import throw, msgprint, _
from frappe.contacts.doctype.address.address import get_company_address
from frappe.model.utils import get_fetch_values
from frappe.utils.password import update_password, check_password
from frappe.desk.notifications import clear_notifications
from frappe.core.utils import get_parent_doc
from frappe.utils.user import get_system_managers
from frappe.utils.print_format import download_pdf
from frappe.core.doctype.communication.email import get_attach_link
import frappe.permissions
import frappe.share
from frappe.model.mapper import get_mapped_doc
from erpnext.selling.doctype.sales_order.sales_order import update_status
from html2text import html2text
import re, datetime
import string
import random
import json
import time
import traceback
import urllib.request
import urllib.parse
import requests
from frappe.core.doctype.sms_settings.sms_settings import send_sms


def appErrorLog(title, error):
	d = frappe.get_doc({
		"doctype": "App Error Log",
		"title": str("User:") + str(title + " " + "App Error"),
		"error": traceback.format_exc()
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

@frappe.whitelist(allow_guest=True)
def custom_login(mobile):
	# take user input from STDIN
	try:
		# validation
		if not mobile:
			return generateResponse(status=422, message="Mobile is required.")
		if len(mobile) != 10 or not mobile.isdigit():
			return generateResponse(status=422, message="Enter valid Mobile.")
		
		res = send_otp(mobile)
		if res == True:
			return generateResponse(message="OTP Send Successfully")
		else:
			return generateResponse(status=500, message="There was some problem while sending OTP. Please try again.")

	except Exception as e:
		return generateResponse(is_success=False, error=e)

@frappe.whitelist()
def ping():
	return "Pong"

@frappe.whitelist(allow_guest=True)
def validate_mobile(mobile):
	user = get_user(mobile)
	if user:
		return generateResponse(status="422", message="Mobile Already Registered")
	else:
		return generateResponse(message="Ok")


@frappe.whitelist(allow_guest=True)
def register_customer(first_name, last_name, phone, email, otp):
	try:
		# validation
		if not first_name:
			return generateResponse(status=422, message="First Name is required.")
		if not phone:
			return generateResponse(status=422, message="Phone is required.")
		if not email:
			return generateResponse(status=422, message="Email is required.")
		if not otp:
			return generateResponse(status=422, message="OTP is required.")

		# if email id is correct, it returns the email id
		# if it is wrong, it returns empty string
		# empty string is a falsey value
		if not frappe.utils.validate_email_address(email):
			return generateResponse(status=422, message="Enter valid Email.")
		if len(phone) != 10 or not phone.isdigit():
			return generateResponse(status=422, message="Enter valid Phone.")
		if len(otp) != 4 or not otp.isdigit():
			return generateResponse(status=422, message="Enter 4 digit OTP.")

		if type(get_user(phone)) is str:
			return generateResponse(status=422, message="Mobile already Registered.")
		if type(get_user(email)) is str:
			return generateResponse(status=422, message="Email already Registered.")

		# validating otp to protect sign up api
		otpobj = frappe.db.get_all("Mobile OTP", {"mobile_no": phone, "otp": otp, "verified": 0})
		if len(otpobj) == 0:
			return generateResponse(status=422, message="Wrong OTP")

		# creating user
		user_name = add_user(first_name, last_name, phone, email)
		if type(user_name) is str:
			token = dict(
				token=generate_user_token(user_name),
			)

			frappe.db.set_value("Mobile OTP", otpobj[0].name, "verified", 1)

			return generateResponse(message="Register Successfully", data=token)
		else:
			return generateResponse(status=500, message="Something Wrong During User Creation. Try Again.")

	except Exception as e:
		return generateResponse(is_success=False, error=e)

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

def add_user(first_name,last_name,phone,email):
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
			# new_password = '123456789',
			roles=[{"doctype": "Has Role", "role": "Loan Customer"}]
		)).insert(ignore_permissions=True)
		# update_password(user.name, '123456789')
		return user.name
	except Exception:
		return False


def send_otp(phone):
	try:
		# delete unused otp
		frappe.db.delete("Mobile OTP", {
			"mobile_no": phone,
			"verified": 0
		})

		OTP_CODE = id_generator_otp()

		mess = "Your OTP for LMS is " + str(OTP_CODE) + ". Do not share your OTP with anyone."
		send_sms([phone], mess)

		otp_doc = frappe.get_doc(dict(
			doctype="Mobile OTP",
			mobile_no=phone,
			otp=OTP_CODE
		)).insert(ignore_permissions=True)
		
		if otp_doc:
			return True
		else:
			return False
	except Exception as e:
		generateResponse(is_success=False, error=e)
		return False


@frappe.whitelist(allow_guest=True)
def send_user_otp(phone):
	try:
		res = send_otp(phone)
		if res:
			return generateResponse(message="User OTP Send Successfully")
		else:
			return generateResponse(status="204", message="Something Wrong")

	except Exception as e:
		return generateResponse(is_success=False, error=e)


@frappe.whitelist(allow_guest=True)
def verify_otp_code(phone, otp):
	try:
		otpobj = frappe.db.get_all("Mobile OTP", {"mobile_no": phone, "otp": otp, "verified": 0})
		if len(otpobj) == 0:
			return generateResponse(status=422, message="Wrong OTP")
		
		user_name = get_user(phone)
		if type(user_name) is str:
			token = dict(
				token=generate_user_token(user_name),
			)

			frappe.db.set_value("Mobile OTP", otpobj[0].name, "verified", 1)

			return generateResponse(message="Login Success", data=token)
		else:
			return generateResponse(status=422, message="Mobile no. does not exist.")
	except Exception as e:
		return generateResponse(is_success=False, error=e)

@frappe.whitelist()
def set_pin(pin):
	print('user', frappe.session.user)
	try:
		# validation
		if not pin:
			return generateResponse(status=422, message="PIN Required")
		if len(pin) != 4 or not pin.isdigit():
			return generateResponse(status=422, message="Please enter 4 digit PIN")

		update_password(frappe.session.user, pin)
		return generateResponse(message="User PIN has been set")
	except Exception as e:
		return generateResponse(is_success=False, error=e)


# {
#     "investorName": "UPPARI SAI KUMAR",
#     "fatherName": "MANAIAH UPPAR",
#     "motherName": "Uppari swaroopa",
#     "address": "H NO 4-1-300/4/A BTS COLONY,VIKARABAD",
#     "mobileNum": "9666366077",
#     "defaultBank": "Y",
#     "accountType": "S",
#     "cancelChequeFileName": "ACSPU1322P_CancelledCheque.jpg",
#     "clientId": "HAD025",
#     "panNum": "ACSPU1322P",
#     "ifsc": "UTIB0001382",
#     "micr": "500211035",
#     "branch": "SANGAREDDY",
#     "bank": "AXIS BANK",
#     "bankAddress": "SR NO.13/P, 14&108, SITE NO.2,POTHIREDDYPALLY VILLAGE , SANGAREDDY,DIST. MEDAK, ANDHRA PRADESH, PIN 502001.",
#     "contact": "0",
#     "city": "SANGAREDDY",
#     "district": "MEDAK",
#     "state": "ANDHRA PRADESH",
#     "bankMode": "DIRECT",
#     "bankcode": "UTI",
#     "bankZipCode": null,
#     "accountNumber": "916010008054697"
# }
@frappe.whitelist()
def save_user_kyc(*args, **kwargs):
	print('user', frappe.session.user)
	print('kwargs', kwargs)
	# print('locals', locals())
	print(kwargs.get('investorName', 'not found'))
	print(kwargs.get('accountNumber', 'not found'))
	if frappe.db.exists('User KYC', frappe.session.user):
		return generateResponse(message="User KYC Already Added")

	data = kwargs

	if data.get('accountNumber', None):
		user_bank_details_doc = frappe.get_doc(dict(
			doctype="User Bank Details",
			user=frappe.session.user,
			default=True if data.get('defaultBank', None)=="Y" else False,
			bank_name=data.get('bank', None),
			account_number=data.get('accountNumber', None),
			account_type=data.get('accountType', None),
			ifsc=data.get('ifsc', None),
			micr=data.get('micr', None),
			branch=data.get('branch', None),
			bank_address=data.get('bankAddress', None),
			city=data.get('city', None),
			district=data.get('district', None),
			state=data.get('state', None),
			zip_code=data.get('bankZipCode', None),
			bank_mode=data.get('bankMode', None),
			bank_code=data.get('bankcode', None)
		)).insert(ignore_permissions=True)

		if not user_bank_details_doc:
			return generateResponse(is_success=False, message="Bank Details Add Failed")
	print(user_bank_details_doc)
	user_kyc_doc = frappe.get_doc(dict(
		doctype="User KYC",
		user=frappe.session.user,
		investor_name=data.get('accountNumber', None),
		father_name=data.get('fatherName', None),
		mother_name=data.get('motherName', None),
		address=data.get('address', None),
		city=data.get('city', None),
		state=data.get('state', None),
		pincode=data.get('pincode', None),
		mobile_number=data.get('mobileNum', None),
		choice_client_id=data.get('clientId', None),
		pan_no=data.get('panNum', None),
		aadhar_no=data.get('aadharNum', None),
		bank=user_bank_details_doc.name
	)).insert(ignore_permissions=True)
	if user_kyc_doc:
		return generateResponse(message="User KYC Added")
	else:
		return generateResponse(is_success=False, message="User KYC Add Failed")



@frappe.whitelist()
def id_generator_otp():
	return ''.join(random.choice('0123456789') for _ in range(4))


def get_user(input):
	user_data = frappe.db.sql("""select name from `tabUser` where email=%s or phone=%s""",(input,input), as_dict=1)
	print('get_user', frappe.as_json(user_data))
	if len(user_data) >= 1:
		return user_data[0].name
	else:
		return False

@frappe.whitelist()
def get_pan(pan_no,birth_date):
	try:
		import xmljson
		from xmljson import parker, Parker
		from xml.etree.ElementTree import fromstring
		from json import dumps

		response = requests.get(
			'https://www.cvlkra.com/paninquiry.asmx/SolicitPANDetailsFetchALLKRA?inputXML=<APP_REQ_ROOT><APP_PAN_INQ> <APP_PAN_NO>{0}</APP_PAN_NO> <APP_DOB_INCORP>{1}</APP_DOB_INCORP> <APP_POS_CODE>1100066900</APP_POS_CODE> <APP_RTA_CODE>1100066900</APP_RTA_CODE> <APP_KRA_CODE></APP_KRA_CODE> <FETCH_TYPE>I</FETCH_TYPE> </APP_PAN_INQ></APP_REQ_ROOT>&userName=EKYC&PosCode=1100066900&Password=n3Xy62aLxQbXypuF0OyDiQ%3d%3d&PassKey=choice@123'.format(pan_no,birth_date)
		)
		if response:
			return generateResponse(message="Pan Details Found", data=parker.data(fromstring(response.text)))
		else:
			return generateResponse(message="Pan Details Not Found")
	except Exception as e:
		return generateResponse(is_success=False, message="Something Wrong Please Check Error Log", error=e)


def get_cdsl_headers():

	 return {
	 		"Referer": "https://www.cdslindia.com/index.html",
			"DPID": "66900",
			"UserID": "ADMIN",
			"Password": "CDsl12##"
			}

# curl -X POST \
#   -H "Referer: https://www.cdslindia.com/index.html" \
#   -H "DPID: 66900" \
#   -H "UserID: ADMIN" \
#   -H "Password: CDsl12##" \
#   -d '{
#           "PledgorBOID": "1206690000014549",
#           "PledgeeBOID": "1206690000014141",
#           "PRFNumber": "CDSL67",
#           "ExpiryDate": "03052018",
#           "ISINDTLS": [
#             {
#               "ISIN": "INE000000001",
#               "Quantity": "1100000000000.000",
#               "Value": "110000000000.00"
#             }
#           ]
#         }' \
#   http://mockapp.cdslindia.com/PledgeAPIService/api/pledgesetup

def get_cdsl_prf_no():
	import datetime
	return datetime.datetime.now().strftime('%s')

@frappe.whitelist()
def cdsl_pedge(pledgor_boid=None, securities_array=None):
	try:
		if not pledgor_boid:
			pledgor_boid = "1206690000014534"
		if not securities_array:
			securities_array = [
			  {
				"ISIN": "INE138A01028",
				"Quantity": "100.000",
				"Value": "200"
			  },
			  {
				"ISIN": "INE221H01019",
				"Quantity": "100.000",
				"Value": "200.00"
			  }
			]
		API_URL = "http://mockapp.cdslindia.com/PledgeAPIService/api/pledgesetup"
		payload = {
					  "PledgorBOID": pledgor_boid, #customer
					  "PledgeeBOID": "1206690000014023", #our client
					  "PRFNumber": "PL" + get_cdsl_prf_no(),
					  "ExpiryDate": "12122020",
					  "ISINDTLS": json.loads(securities_array)
					}

		print("cdsl_pedge", payload)
		response = requests.post(
			API_URL,
			headers=get_cdsl_headers(),
			json=payload
		)

		print(response.text)
		response_json = json.loads(response.text)
		print("response_json", response_json)
		if response_json and response_json.get("Success") == True:
			return generateResponse(message="CDSL", data=response_json)
		else:
			return generateResponse(is_success=False, message="CDSL Pledge Error", data=response_json)
	except Exception as e:
		print(e)
		return generateResponse(is_success=False, message="Something Wrong Please Check Error Log", error=e)


@frappe.whitelist()
def cdsl_unpedge(securities_array=None):
	try:
		if not securities_array:
			securities_array = [
			  {
				"PSNumber": "1930499",
				"PartQuantity": "100.000"
			  }
			]

		API_URL = "http://mockapp.cdslindia.com/PledgeAPIService/api/UnPledgeSetup"
		payload = {
					  "URN": "UN" + get_cdsl_prf_no(),
					  "Type": "Pledgee",
					  "UNPLDGDTLS": json.loads(securities_array)
					}
		response = requests.post(
			API_URL,
			headers=get_cdsl_headers(),
			json=payload
		)

		print(response)
		print(response.text)
		response_json = json.loads(response.text)
		print("response_json", response_json)
		if response_json and response_json.get("Success") == True:
			return generateResponse(message="CDSL", data=response_json)
		else:
			return generateResponse(is_success=False, message="CDSL UnPledge Error", data=response_json)
	except Exception as e:
		print(e)
		return generateResponse(is_success=False, message="Something Wrong Please Check Error Log", error=e)

@frappe.whitelist()
def cdsl_confiscate(securities_array=None):
	try:
		if not securities_array:
			securities_array = [
			  {
				"PSNumber": "1930499",
				"PartQuantity": "100.000"
			  }
			]

		API_URL = "http://mockapp.cdslindia.com/PledgeAPIService/api/Confiscatesetup"
		payload = {
					  "URN": "CN" + get_cdsl_prf_no(),
					  "CONFISCATEDTLS": json.loads(securities_array)
					}
		response = requests.post(
			API_URL,
			headers=get_cdsl_headers(),
			json=payload
		)

		print(response)
		print(response.text)
		response_json = json.loads(response.text)
		print("response_json", response_json)
		if response_json and response_json.get("Success") == True:
			return generateResponse(message="CDSL", data=response_json)
		else:
			return generateResponse(is_success=False, message="CDSL Confiscate Error", data=response_json)
	except Exception as e:
		print(e)
		return generateResponse(is_success=False, message="Something Wrong Please Check Error Log", error=e)
