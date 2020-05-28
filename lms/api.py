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


@frappe.whitelist()
def appErrorLog(title, error):
	d = frappe.get_doc({
		"doctype": "App Error Log",
		"title": str("User:") + str(title + " " + "App Error"),
		"error": traceback.format_exc()
	})
	d = d.insert(ignore_permissions=True)
	return d


@frappe.whitelist()
def generateResponse(_type, status=None, message=None, data=None, error=None):
	response = {}
	if _type == "S":
		if status:
			response["status"] = int(status)
		else:
			response["status"] = 200
		response["message"] = message
		response["data"] = data
	else:
		error_log = appErrorLog(frappe.session.user, str(error))
		if status:
			response["status"] = status
		else:
			response["status"] = 500
		if message:
			response["message"] = message
		else:
			response["message"] = "Something Went Wrong"
		response["message"] = message
		response["data"] = []
	return response

@frappe.whitelist(allow_guest=True)
def custom_login(mobile):
	# take user input from STDIN
	try:
		res = send_otp(mobile)
		if res == True:
			return generateResponse("S", "200", message="OTP Send Successfully ", data=[])
		else:
			return generateResponse("S", "401", message="Phone Incorrect", data=[])

	except Exception as e:
		return generateResponse("F", message="Something Wrong", error=e)

@frappe.whitelist()
def ping():
	return "Pong"

@frappe.whitelist(allow_guest=True)
def validate_mobile(mobile):
	user = get_user(mobile)
	if user:
		return generateResponse("S", "422", message="Mobile Already Registered", data=[])
	else:
		return generateResponse("S", "200", message="Ok", data=[])


@frappe.whitelist(allow_guest=True)
def register_customer(first_name,last_name,phone,email=None):
	try:
		user_id = get_user(phone)
		if user_id:
			return generateResponse("S", "422", message="Mobile Already Registered", data=[])
		user_id = get_user(email)
		if user_id:
			return generateResponse("S", "422", message="Email Already Registered", data=[])
		user = add_user(first_name,last_name,phone,email)
		if user:
			otp_res = send_otp(phone)
			if otp_res == False:
				return generateResponse("S", "500", message="Something Wrong During OTP Send", data=[])
			return generateResponse("S", message="Register Successfully", data=user)
		else:
			return generateResponse("S", "500", message="Something Wrong During User Creation. Try Again", data=[])

	except Exception as e:
		return generateResponse("F", error=e)

@frappe.whitelist()
def generate_keys(user):
	"""
	generate api key and api secret

	:param user: str
	"""
	user_details = frappe.get_doc("User", user)
	api_secret = frappe.generate_hash(length=15)
	# if api key is not set generate api key
	if not user_details.api_key:
		api_key = frappe.generate_hash(length=15)
		user_details.api_key = api_key
	user_details.api_secret = api_secret
	user_details.save(ignore_permissions=True)
	return api_secret


@frappe.whitelist(allow_guest = True)
def add_user(first_name,last_name,phone,email=None):
	try:
		user = frappe.get_doc(dict(
			doctype="User",
			email=email,
			first_name=first_name,
			last_name = last_name,
			username = str(first_name)+str(phone),
			phone=phone,
			mobile_no=phone,
			send_welcome_email=0,
			new_password = '123456789',
			roles=[{"doctype": "Has Role", "role": "Loan Customer"}]
		)).insert(ignore_permissions=True)
		update_password(user.name, '123456789')
		return user
	except Exception as e:
		return generateResponse("F", error=e)


@frappe.whitelist()
def send_otp(phone):
	try:
		otpobj = frappe.db.get("Mobile OTP", {"mobile_no": phone})
		if otpobj:
			frappe.db.sql("""delete from `tabMobile OTP` where mobile_no='""" + phone + """'""")
		OPTCODE = id_generator_otp()
		#sms_key = frappe.db.get_value("App Version", "App Version", "sms_key")
		mess = "Your OTP for LMS is " + str(OPTCODE) + ". Do not share your OTP with anyone."
		# response = sendSMS(phone, mess)
		# res = json.loads(response)
		# if res["status"] == "success":
		otp_doc = frappe.get_doc(dict(
			doctype="Mobile OTP",
			mobile_no=phone,
			otp=OPTCODE
		)).insert(ignore_permissions=True)
		if otp_doc:
			return True
		else:
			return False
	except Exception as e:
		generateResponse("F", error=e)
		return False


@frappe.whitelist(allow_guest=True)
def send_user_otp(phone):
	try:
		res = send_otp(phone)
		if res:
			return generateResponse("S", message="User OTP Send Successfully", data=[])
		else:
			return generateResponse("S", "204", message="Something Wrong", data=[])

	except Exception as e:
		generateResponse("F", error=e)
		return False


@frappe.whitelist(allow_guest=True)
def verify_otp_code(phone, otp):
	try:
		user = get_user(phone)
		otpobj = frappe.db.get("Mobile OTP", {"mobile_no": phone})
		if otpobj.otp == otp:
			secret_key = generate_keys(user)
			api_key = frappe.db.get_value("User", user, "api_key")
			token = dict(
				token="token {}:{}".format(api_key, secret_key),
				phone=frappe.db.get_value("User", user, "phone") or ''
			)
			return generateResponse("S", message="OTP Verified", data=token)
		else:
			return generateResponse("S", status="417", message="Wrong OTP", data={})
	except Exception as e:
		return generateResponse("F", message="Something Wrong Please Try Again", error=e)


@frappe.whitelist()
def id_generator_otp():
	return ''.join(random.choice('0123456789') for _ in range(6))


def get_user(user):
	user_data = frappe.db.sql("""select name from `tabUser` where email=%s or phone=%s""",(user,user), as_dict=1)
	if len(user_data) >= 1:
		return user_data[0].name
	else:
		return False
