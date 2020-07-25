import frappe
from frappe import _
from frappe.utils.password import update_password
import lms
from datetime import datetime
import requests
import json
from xmljson import parker
from xml.etree.ElementTree import fromstring

@frappe.whitelist()
def set_pin(pin):
	try:
		# validation
		lms.validate_http_method('POST')

		if not pin:
			raise lms.ValidationError(_('PIN Required.'))
		if len(pin) != 4 or not pin.isdigit():
			raise lms.ValidationError(_('Please enter 4 digit PIN'))

		update_password(frappe.session.user, pin)
		return lms.generateResponse(message=_('User PIN has been set'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def kyc(pan_no, birth_date):
	try:
		# validation
		lms.validate_http_method('GET')

		if not pan_no:
			raise lms.ValidationError(_('Pan is required.'))
		if not birth_date:
			raise lms.ValidationError(_('Birth date is required.'))
		
		try:
			datetime.strptime(birth_date, "%d/%m/%Y")
		except ValueError:
			raise lms.ValidationError(_('Please enter valid date.'))

		user = frappe.get_doc('User', frappe.session.user)
		user_kyc_list = frappe.db.get_all("User KYC", filters={ "user": user.username }, order_by="user_type", fields=["*"])

		if len(user_kyc_list) > 0:
			return lms.generateResponse(message="User KYC", data=user_kyc_list[0])

		las_settings = frappe.get_single('LAS Settings')

		# check in choice
		url = "{}{}".format(las_settings.choice_host, las_settings.choice_pan_details_uri)
		params = {"panNum": pan_no}
		headers = {
			"businessUnit": las_settings.choice_business_unit,
			"userId": las_settings.choice_user_id,
			"investorId": las_settings.choice_investor_id,
			"ticket": las_settings.choice_ticket
		}
		r = requests.get(url, params=params, headers=headers)
		if not r.ok:
			return lms.generateResponse(status=r.status_code, message=_('A problem occured while fetching KYC details from CHOICE.'))
		data = json.loads(r.text)
		if 'status' not in data:
			user_kyc = frappe.get_doc({
				"doctype": "User KYC",
				"user_mobile_number": user.username,
				"kyc_type": "CHOICE",
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

			return lms.generateResponse(message="CHOICE USER KYC", data=user_kyc)

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
			return lms.generateResponse(message="KRA USER KYC", data=user_kyc)
		return lms.generateResponse(message="KYC not found")
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def tnc():
	try:
		user = frappe.get_doc('User', frappe.session.user)
		
		for tnc in frappe.get_list('Terms and Conditions', filters={'is_active': 1}):
			approved_tnc = frappe.get_doc({
				'doctype': 'Approved Terms and Conditions',
				'mobile': user.username,
				'tnc': tnc.name,
				'time': datetime.now()
			})
			approved_tnc.insert(ignore_permissions=True)

		return lms.generateResponse(message=_('Approved TnC saved.'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)