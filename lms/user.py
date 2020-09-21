import frappe
from frappe import _
from frappe.utils.password import update_password
import lms
from datetime import datetime
import requests
import json
from xmljson import parker
from xml.etree.ElementTree import fromstring
from lms.firebase import FirebaseAdmin

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
def kyc(pan_no=None, birth_date=None):
	try:
		# validation
		lms.validate_http_method('GET')

		user = frappe.get_doc('User', frappe.session.user)
		user_kyc_list = frappe.db.get_all("User KYC", filters={ "pan_no": pan_no, "user_mobile_number": user.username }, order_by="kyc_type", fields=["*"])

		if len(user_kyc_list) > 0:
			return lms.generateResponse(message="User KYC", data=user_kyc_list[0])
		

		if not pan_no:
			raise lms.ValidationError(_('Pan is required.'))
		if not birth_date:
			raise lms.ValidationError(_('Birth date is required.'))
		
		try:
			datetime.strptime(birth_date, "%d/%m/%Y")
		except ValueError:
			raise lms.ValidationError(_('Please enter valid date.'))

		las_settings = frappe.get_single('LAS Settings')

		# check in choice
		params = {"panNum": pan_no}
		headers = {
			"businessUnit": las_settings.choice_business_unit,
			"userId": las_settings.choice_user_id,
			"investorId": las_settings.choice_investor_id,
			"ticket": las_settings.choice_ticket
		}
		r = requests.get(las_settings.choice_pan_api, params=params, headers=headers)
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

			customer = lms.get_customer(user.username)
			customer.kyc_update = 1
			customer.choice_kyc = user_kyc.name
			customer.save(ignore_permissions=True)
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
def esign(cart_name=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not cart_name:
			raise lms.ValidationError(_('Cart Required.'))

		user = frappe.get_doc('User', frappe.session.user)
		customer = lms.get_customer(user.username)
		cart = frappe.get_doc('Cart', cart_name)
		if not cart:
				return lms.generateResponse(status=404, message=_('Cart not found.'))
		if cart.customer != customer.name:
			return lms.generateResponse(status=403, message=_('Please use your own cart.'))
		
		for tnc in frappe.get_list('Terms and Conditions', filters={'is_active': 1}):
			approved_tnc = frappe.get_doc({
				'doctype': 'Approved Terms and Conditions',
				'mobile': user.username,
				'tnc': tnc.name,
				'time': datetime.now()
			})
			approved_tnc.insert(ignore_permissions=True)

		from frappe.utils.pdf import get_pdf
		html = frappe.get_print('Cart', cart_name, 'Loan Aggrement', no_letterhead=True)

		las_settings = frappe.get_single('LAS Settings')

		headers = {'userId': las_settings.choice_user_id}
		files = {'file': ('loan-aggrement.pdf', get_pdf(html))}
		r = requests.post(las_settings.esign_upload_file_url, files=files, headers=headers)

		if not r.ok:
			return lms.generateResponse(status=500, message=_('There was some problem in uploading loan aggrement file'))

		data = r.json()

		url = las_settings.esign_request_url.format(
			id=data.get('id'),
			x=200,
			y=200,
			page_number=2
		)

		return lms.generateResponse(message=_('Esign URL.'), data={'esign_url': url, 'file_id': data.get('id')})
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def securities():
	try:
		lms.validate_http_method('GET')

		user = frappe.get_doc('User', frappe.session.user)
		
		user_kyc_list = frappe.db.get_all("User KYC", filters={ "user_mobile_number": user.username }, order_by="kyc_type", fields=["*"])

		if len(user_kyc_list) == 0:
			raise lms.ValidationError(_('User KYC not done.'))

		if user_kyc_list[0].kyc_type != "CHOICE":
			raise lms.ValidationError(_('CHOICE KYC not done.'))

		las_settings = frappe.get_single('LAS Settings')

		# get securities list from choice
		data = {
			"UserID": las_settings.choice_user_id,
			"ClientID": user_kyc_list[0].choice_client_id
		}

		res = requests.post(las_settings.choice_securities_list_api, json=data, headers={"Accept": "application/json"})
		if not res.ok:
			return lms.generateResponse(status=res.status_code, message=_('There was a problem while getting share list from choice.'))
		res_json = res.json()
		if res_json["Status"] != "Success":
			return lms.generateResponse(status=422, message=_('Problem in getting securities list.'))
			
		# setting eligibility
		securities_list = res_json["Response"]
		securities_list_ = [i['ISIN'] for i in securities_list]
		securities_category_map = lms.get_security_categories(securities_list_)

		for i in securities_list:
			try:
				i["Category"] = securities_category_map[i['ISIN']]
				i["Is_Eligible"] = True
			except KeyError:
				i["Is_Eligible"] = False
				i["Category"] = None
		
		return lms.generateResponse(message="securities list", data=securities_list)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, data=e, error=e)

@frappe.whitelist()
def save_firebase_token(firebase_token):
	try:
		# validation
		lms.validate_http_method('POST')

		if not firebase_token:
			raise lms.ValidationError(_('Firebase Token Required.'))

		tokens = lms.get_firebase_tokens(frappe.session.user)

		if firebase_token not in tokens:
			token = frappe.get_doc({
				'doctype': 'User Token',
				'entity': frappe.session.user,
				'token_type': 'Firebase Token',
				'token': firebase_token
			})
			token.insert(ignore_permissions=True)

		return lms.generateResponse(message=_('Firebase token added successfully'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, data=e, error=e)

@frappe.whitelist(allow_guest=True)
def tds(tds_amount):

	files = frappe.request.files
	is_private = frappe.form_dict.is_private
	doctype = frappe.form_dict.doctype
	docname = frappe.form_dict.docname
	fieldname = frappe.form_dict.fieldname
	file_url = frappe.form_dict.file_url
	folder = frappe.form_dict.folder or 'Home'
	method = frappe.form_dict.method
	content = None
	filename = None

	if 'tds_file_upload' in files:
		file = files['tds_file_upload']
		content = file.stream.read()
		filename = file.filename

	frappe.local.uploaded_file = content
	frappe.local.uploaded_filename = filename

	from frappe.utils import cint
	f = frappe.get_doc({
		"doctype": "File",
		"attached_to_doctype": doctype,
		"attached_to_name": docname,
		"attached_to_field": fieldname,
		"folder": folder,
		"file_name": filename,
		"file_url": file_url,
		"is_private": cint(is_private),
		"content": content
	})
	f.save(ignore_permissions=True)
	tds = frappe.get_doc(dict(
		doctype = "TDS",
		tds_amount = tds_amount,
		tds_file_upload = f.file_url
	))
	tds.insert(ignore_permissions=True)

	return lms.generateResponse(message=_('TDS Create Successfully.'), data={'file': tds})