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
import re
import string
import random
import json
import time
import traceback
import urllib.request
import urllib.parse
import requests
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.auth import LoginManager
from frappe.utils.password import delete_login_failed_cache
from datetime import datetime, timedelta
from xmljson import parker
from xml.etree.ElementTree import fromstring


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
def custom_login(mobile, pin=None):
	# take user input from STDIN
	try:
		# validation
		if not mobile:
			return generateResponse(status=422, message="Mobile is required.")
		if len(mobile) != 10 or not mobile.isdigit():
			return generateResponse(status=422, message="Enter valid Mobile.")
		
		if pin:
			login_manager = LoginManager()
			login_manager.authenticate(user=mobile, pwd=pin)

		res = send_otp(mobile)
		if res == True:
			return generateResponse(message="OTP Send Successfully")
		else:
			return generateResponse(status=500, message="There was some problem while sending OTP. Please try again.")
	except frappe.AuthenticationError as e:
		return generateResponse(status=401, message="Incorrect PIN")
	except frappe.SecurityException as e:
		return generateResponse(status=401, message=str(e))
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
		update_password(user.name, '{0}-{0}'.format(datetime.now().strftime('%s')))
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
		login_manager = LoginManager()
		user_name = get_user(phone)
		otpobj = frappe.db.get_all("Mobile OTP", {"mobile_no": phone, "otp": otp, "verified": 0})
		if len(otpobj) == 0:
			if type(user_name) is str:
				login_manager.update_invalid_login(user_name)
				login_manager.check_if_enabled(user_name)
			return generateResponse(status=422, message="Wrong OTP")
		
		if type(user_name) is str:
			login_manager.check_if_enabled(user_name)
			token = dict(
				token=generate_user_token(user_name),
			)

			frappe.db.set_value("Mobile OTP", otpobj[0].name, "verified", 1)
			delete_login_failed_cache(user_name)
			return generateResponse(message="Login Success", data=token)
		else:
			return generateResponse(status=422, message="Mobile no. does not exist.")
	except frappe.SecurityException as e:
		return generateResponse(status=422, message=str(e))
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
	return '1234'
	return ''.join(random.choice('0123456789') for _ in range(4))


def get_user(input):
	user_data = frappe.db.sql("""select name from `tabUser` where email=%s or phone=%s""",(input,input), as_dict=1)
	print('get_user', frappe.as_json(user_data))
	if len(user_data) >= 1:
		return user_data[0].name
	else:
		return False

@frappe.whitelist()
def get_user_kyc(pan_no, birth_date):
	try:
		if not pan_no:
			return generateResponse(status=422, message="Pan is required.")
		if not birth_date:
			return generateResponse(status=422, message="Birth date is required.")

		datetime.strptime(birth_date, "%d/%m/%Y")

		user_kyc_list = frappe.db.get_all("User KYC", filters={ "user": frappe.session.user }, order_by="user_type", fields=["*"])

		if len(user_kyc_list) > 0:
			return generateResponse(message="User KYC", data=user_kyc_list[0])

		# check in choice
		url = "https://uat-pwa.choicetechlab.com/api/spark/getByPanNumDetails"
		params = {"panNum": pan_no}
		headers = {
			"businessUnit": "JF",
			"userId": "Spark",
			"investorId": "1",
			"ticket": "c3Bhcms="
		}
		r = requests.get(url, params=params, headers=headers)
		data = json.loads(r.text)
		if 'status' not in data:
			user_kyc = frappe.get_doc({
				"doctype": "User KYC",
				"user": frappe.session.user,
				"user_type": "CHOICE",
				"investor_name": data["investorName"],
				"father_name": data["fatherName"],
				"mother_name": data["motherName"],
				"address": data["address"],
				"city": data["addressCity"],
				"state": data["addressState"],
				"pincode": data["addressPinCode"],
				"mobile_number": data["mobileNum"],
				"choice_client_id": data["clientId"],
				"pan_no": data["panNum"],
				"aadhar_no": data["panNum"],
				"bank_account_type": data["accountType"],
				"bank_name": data["bank"],
				"bank_code": data["bankcode"],
				"bank_mode": data["bankMode"],
				"bank_branch": data["branch"],
				"bank_ifsc": data["ifsc"],
				"bank_micr": data["micr"],
				"bank_account_number": data["accountNumber"],
				"bank_address": data["bankAddress"],
				"bank_address_district": data["district"],
				"bank_address_city": data["city"],
				"bank_address_state": data["state"],
				"bank_address_pincode": data["bankZipCode"],
				"bank_contact": data["contact"]
			})
			user_kyc.insert(ignore_permissions=True)
			frappe.db.commit()
			user_kyc = user_kyc.as_dict()
			user_kyc["response"] = data
			return generateResponse(message="CHOICE USER KYC", data=user_kyc)

		# check in kra
		url = "https://www.cvlkra.com/paninquiry.asmx/SolicitPANDetailsFetchALLKRA"
		params = {
			"inputXML": "<APP_REQ_ROOT><APP_PAN_INQ> <APP_PAN_NO>{0}</APP_PAN_NO> <APP_DOB_INCORP>{1}</APP_DOB_INCORP> <APP_POS_CODE>1100066900</APP_POS_CODE> <APP_RTA_CODE>1100066900</APP_RTA_CODE> <APP_KRA_CODE></APP_KRA_CODE> <FETCH_TYPE>I</FETCH_TYPE> </APP_PAN_INQ></APP_REQ_ROOT>".format(pan_no, birth_date),
			"userName": "EKYC",
			"PosCode": "1100066900",
			"Password": "n3Xy62aLxQbXypuF0OyDiQ==",
			"PassKey": "choice@123"
		}
		r = requests.get(url, params=params)
		data = parker.data(fromstring(r.text))
		if "APP_PAN_RES" not in data and "ERROR" not in data:
			user_kyc = frappe.get_doc({
				"doctype": "User KYC",
				"user": frappe.session.user,
				"user_type": "KRA",
				"investor_name": "investor name",
				"father_name": data["APP_PAN_INQ"]["APP_F_NAME"],
				"mother_name": "mother name",
				"address": ", ".join(filter([data["APP_PAN_INQ"]["APP_PER_ADD1"], data["APP_PAN_INQ"]["APP_PER_ADD2"], data["APP_PAN_INQ"]["APP_PER_ADD3"]], None)),
				"city": data["APP_PAN_INQ"]["APP_PER_CITY"],
				"state": data["APP_PAN_INQ"]["APP_PER_STATE"],
				"pincode": data["APP_PAN_INQ"]["APP_PER_PINCD"],
				"mobile_number": data["APP_PAN_INQ"]["APP_MOB_NO"],
				"choice_client_id": None,
				"pan_no": data["APP_PAN_INQ"]["APP_PAN_NO"],
				"aadhar_no": data["APP_PAN_INQ"]["APP_PAN_NO"]
				})
			user_kyc.insert(ignore_permissions=True)
			frappe.db.commit()
			user_kyc = user_kyc.as_dict()
			user_kyc["response"] = data
			return generateResponse(message="KRA USER KYC", data=user_kyc)
		return generateResponse(message="KYC not found")
		
	except ValueError as e:
		return generateResponse(status=422, message="Please enter valid date.")
	except Exception as e:
		return generateResponse(is_success=False, error=e)

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

@frappe.whitelist()
def get_share_list():
	try:
		user_kyc_list = frappe.db.get_all("User KYC", filters={ "user": frappe.session.user }, order_by="user_type", fields=["*"])

		if len(user_kyc_list) == 0:
			return generateResponse(status=422, message="User KYC not done.")

		if user_kyc_list[0].user_type != "CHOICE":
			return generateResponse(status=422, message="CHOICE KYC not done.")

		# get securities list from choice
		url = "https://api.choicebroking.in/api/middleware/GetClientHoldingDetails"
		data = {
			"UserID": "Spark",
			"ClientID": user_kyc_list[0].choice_client_id
		}

		res = requests.post(url, json=data, headers={"Accept": "application/json"})
		if not res.ok:
			return generateResponse(status=res.status_code, message="There was a problem while getting share list from choice.")
		res_json = res.json()
		if res_json["Status"] != "Success":
			return generateResponse(status=422, message="Problem in getting securities list")
			
		# setting eligibility
		securities_list = res_json["Response"]
		for i in securities_list:
			allowed_securities_list = frappe.db.get_all("Allowed Security Master", filters={ "isin_no": i["ISIN"] }, fields=["*"])
			i["Is_Eligible"] = False
			i["Category"] = None
			if len(allowed_securities_list) > 0:
				i["Is_Eligible"] = True
				i["Category"] = allowed_securities_list[0].category
		
		return generateResponse(message="securities list", data=securities_list)
	except Exception as e:
		return generateResponse(is_success=False, data=e, error=e)

def get_cdsl_headers():

	 return {
	 		"Referer": "https://www.cdslindia.com/index.html",
	 		# "Referer": "https://dev.sparklms.atritechnocrat.in",
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
	return datetime.now().strftime('%s')

def is_float_num_valid(num, length, precision):
	valid = True
	
	valid = True if type(num) is float else False
	
	num_str = str(num)
	if valid:
		valid = True if len(num_str.replace('.', '')) <= length else False

	if valid:
		valid = True if len(num_str.split('.')[1]) <= precision else False

	return valid

@frappe.whitelist()
def cdsl_pedge(securities, expiry=None, pledgor_boid=None, pledgee_boid=None):
	try:
		if not securities or "list" not in securities.keys():
			return generateResponse(status=422, message="Securities required")
		
		securities = securities["list"]
		# check if securities is a list of dict
		securities_valid = True
		
		if type(securities) is not list:
			securities_valid = False
			message = "securities should be list of dictionaries"

		if securities_valid:
			for i in securities:
				if type(i) is not dict:
					securities_valid = False
					message = "items in securities need to be dictionaries"
					break
				
				keys = i.keys()
				if "isin" not in keys or "quantity" not in keys or "value" not in keys:
					securities_valid = False
					message = "any/all of isin, quantity, value not present"
					break

				if type(i["isin"]) is not str or len(i["isin"]) > 12:
					securities_valid = False
					message = "isin not correct"
					break

				if not is_float_num_valid(i["quantity"], 16, 3):
					securities_valid = False
					message = "quantity not correct"
					break

				if not is_float_num_valid(i["value"], 14, 2):
					securities_valid = False
					message = "value not correct"
					break


		if not securities_valid:
			return generateResponse(status=422, message=message)

		if not expiry:
			expiry = datetime.now() + timedelta(days = 365)
		
		if not pledgor_boid:
			pledgor_boid = "1206690000014534"
		if not pledgee_boid:
			pledgee_boid = "1206690000014023"

		securities_array = []
		for i in securities:
			j = {
				"ISIN": i["isin"],
				"Quantity": i["quantity"],
				"Value": i["value"]
			}
			securities_array.append(j)

		API_URL = "http://mockapp.cdslindia.com/PledgeAPIService/api/pledgesetup"
		payload = {
			"PledgorBOID": pledgor_boid, #customer
			"PledgeeBOID": pledgee_boid, #our client
			"PRFNumber": "PL" + get_cdsl_prf_no(),
			"ExpiryDate": expiry.strftime('%d%m%Y'),
			"ISINDTLS": securities_array
		}
		# payload = json.dumps(payload)
		frappe.logger().info(["cdsl_pedge", payload])
		response = requests.post(
			API_URL,
			headers=get_cdsl_headers(),
			json=payload
		)

		print(response.text)
		response_json = response.json()
		frappe.logger().info(['res', response_json])
		print("response_json", response_json)
		if response_json and response_json.get("Success") == True:
			return generateResponse(message="CDSL", data=response_json)
		else:
			return generateResponse(is_success=False, message="CDSL Pledge Error", data=response_json)
	except Exception as e:
		print(e)
		return generateResponse(is_success=False, error=e)


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

@frappe.whitelist()
def my_cart(securities, cart_name=None, expiry=None):
	try:
		if not securities or "list" not in securities.keys():
			return generateResponse(status=422, message="Securities required")
		
		securities = securities["list"]
		# check if securities is a list of dict
		securities_valid = True
		
		if type(securities) is not list:
			securities_valid = False
			message = "securities should be list of dictionaries"

		if securities_valid:
			for i in securities:
				if type(i) is not dict:
					securities_valid = False
					message = "items in securities need to be dictionaries"
					break
				
				keys = i.keys()
				if "isin" not in keys or "quantity" not in keys or "price" not in keys:
					securities_valid = False
					message = "any/all of isin, quantity, price not present"
					break

				if type(i["isin"]) is not str or len(i["isin"]) > 12:
					securities_valid = False
					message = "isin not correct"
					break

				if not is_float_num_valid(i["quantity"], 16, 3):
					securities_valid = False
					message = "quantity not correct"
					break

				if not is_float_num_valid(i["price"], 14, 2):
					securities_valid = False
					message = "price not correct"
					break


		if not securities_valid:
			return generateResponse(status=422, message=message)

		if not expiry:
			expiry = datetime.now() + timedelta(days = 365)


		cart_items = []
		for i in securities:
			item = frappe.get_doc({
				"doctype": "Cart Item",
				"isin": i["isin"],
				"pledged_quantity": i["quantity"],
				"price": i["price"] 
			})

			cart_items.append(item)

		if not cart_name:
			cart = frappe.get_doc({
				"doctype": "Cart",
				"user": frappe.session.user,
				"expiry": expiry,
				"cart_items": cart_items
			})
			cart.insert()
		else:
			cart = frappe.get_doc("Cart", cart_name)
			if not cart:
				return generateResponse(status=404, message="Cart not found.")
			if cart.owner != frappe.session.user:
				return generateResponse(status=403, message="Please use your own cart.")

			cart.cart_items = cart_items
			cart.save()

		return generateResponse(message="Cart Saved", data=cart)
	except Exception as e:
		return generateResponse(is_success=False, error=e)