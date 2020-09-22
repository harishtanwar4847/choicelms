import frappe
from frappe import _
import lms
from datetime import datetime, timedelta
from frappe.core.doctype.sms_settings.sms_settings import send_sms
import requests
from itertools import groupby

@frappe.whitelist()
def upsert(securities, cart_name=None, expiry=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not securities or (type(securities) is not dict and "list" not in securities.keys()):
			raise lms.ValidationError(_('Securities required.'))
		
		securities = securities["list"]

		if len(securities) == 0:
			raise lms.ValidationError(_('Securities required.'))

		# check if securities is a list of dict
		securities_valid = True
		
		if type(securities) is not list:
			securities_valid = False
			message = _('securities should be list of dictionaries')

		securities_list = [i['isin'] for i in securities]

		if securities_valid:
			if len(set(securities_list)) != len(securities_list):
				securities_valid = False
				message = _('duplicate isin')
		
		if securities_valid:
			securities_list_from_db_ = frappe.db.sql("select isin from `tabAllowed Security` where isin in {}".format(lms.convert_list_to_tuple_string(securities_list)))
			securities_list_from_db = [i[0] for i in securities_list_from_db_]

			diff = list(set(securities_list) - set(securities_list_from_db))
			if diff:
				securities_valid = False
				message = _('{} isin not found'.format(','.join(diff)))

		if securities_valid:
			for i in securities:
				if type(i) is not dict:
					securities_valid = False
					message = _('items in securities need to be dictionaries')
					break
				
				keys = i.keys()
				if "isin" not in keys or "quantity" not in keys or "price" not in keys:
					securities_valid = False
					message = _('any/all of isin, quantity, price not present')
					break

				if type(i["isin"]) is not str or len(i["isin"]) > 12:
					securities_valid = False
					message = _('isin not correct')
					break

				if not frappe.db.exists('Allowed Security', i['isin']):
					securities_valid = False
					message = _('{} isin not found').format(i['isin'])
					break

				if not lms.is_float_num_valid(i["quantity"], 16, 3):
					securities_valid = False
					message = _('quantity not correct')
					break

				if not lms.is_float_num_valid(i["price"], 14, 2):
					securities_valid = False
					message = _('price not correct')
					break

		if not securities_valid:
			raise lms.ValidationError(message)

		if not expiry:
			expiry = datetime.now() + timedelta(days = 365)

		customer = lms.get_customer(frappe.session.user)

		if not cart_name:
			cart = frappe.get_doc({
				"doctype": "Cart",
				"customer": customer.name
			})
			for i in securities:
				cart.append('items', {
					"isin": i["isin"],
					"pledged_quantity": i["quantity"],
					"price": i["price"] 
				})
			cart.insert(ignore_permissions=True)
		else:
			cart = frappe.get_doc("Cart", cart_name)
			if not cart:
				return lms.generateResponse(status=404, message=_('Cart not found.'))
			if cart.customer != customer.name:
				return lms.generateResponse(status=403, message=_('Please use your own cart.'))

			cart.items = []
			for i in securities:
				cart.append('items', {
					"isin": i["isin"],
					"pledged_quantity": i["quantity"],
					"price": i["price"] 
				})
			cart.save(ignore_permissions=True)

		return lms.generateResponse(message=_('Cart Saved'), data=cart)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def process(cart_name, otp, file_id, pledgor_boid=None, expiry=None, pledgee_boid=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not cart_name:
			raise lms.ValidationError(_('Cart name required.'))
		if len(otp) != 4 or not otp.isdigit():
			raise lms.ValidationError(_('Enter 4 digit OTP.'))
		if not file_id:
			raise lms.ValidationError(_('File ID Required.'))

		otp_res = lms.check_user_token(entity=frappe.session.user, token=otp, token_type="Pledge OTP")
		if not otp_res[0]:
			raise lms.ValidationError(_('Wrong OTP.'))

		cart = frappe.get_doc("Cart", cart_name)
		customer = lms.get_customer(frappe.session.user)
		if not cart:
			return lms.generateResponse(status=404, message=_('Cart not found.'))
		if cart.customer != customer.name:
			return lms.generateResponse(status=403, message=_('Please use your own cart.'))

		if not pledgor_boid:
			pledgor_boid = '1206690000014534'
		if not pledgee_boid:
			pledgee_boid = '1206690000014023'
		if not expiry:
			expiry = datetime.now() + timedelta(days = 365)

		securities_array = []
		for i in cart.items:
			j = {
				"ISIN": i.isin,
				"Quantity": i.pledged_quantity,
				"Value": i.price
			}
			securities_array.append(j)

		las_settings = frappe.get_single('LAS Settings')
		
		API_URL = '{}{}'.format(las_settings.cdsl_host, las_settings.pledge_setup_uri)
		payload = {
			"PledgorBOID": pledgor_boid, #customer
			"PledgeeBOID": pledgee_boid, #our client
			"PRFNumber": lms.get_cdsl_prf_no(),
			"ExpiryDate": expiry.strftime('%d%m%Y'),
			"ISINDTLS": securities_array
		}

		response = requests.post(
			API_URL,
			headers=las_settings.cdsl_headers(),
			json=payload
		)

		response_json = response.json()
		frappe.logger().info({'CDSL PLEDGE HEADERS': las_settings.cdsl_headers(), 'CDSL PLEDGE PAYLOAD': payload, 'CDSL PLEDGE RESPONSE': response_json})

		if response.ok and response_json.get("Success") == True:
			response_json_item_groups = {}
			for key, group in groupby(response_json['PledgeSetupResponse']['ISINstatusDtls'], key=lambda x: x['ISIN']):
				response_json_item_groups[key] = list(group)[0]

			items = []
			
			for item in cart.items:
				frappe.logger().info({'print error code': response_json_item_groups[item.isin]['ErrorCode']})
				item = frappe.get_doc({
					'doctype': 'Loan Application Item',
					'isin': item.isin,
					'security_name': item.security_name,
					'security_category': item.security_category,
					'pledged_quantity': item.pledged_quantity,
					'price': item.price,
					'amount': item.amount,
					'psn': response_json_item_groups[item.isin]['PSN'],
					'error_code': response_json_item_groups[item.isin]['ErrorCode'],
				})
				items.append(item)

			loan_application = frappe.get_doc({
				'doctype': 'Loan Application',
				'total_collateral_value': cart.total_collateral_value,
				'overdraft_limit': cart.eligible_loan,
				'pledgor_boid': pledgor_boid,
				'pledgee_boid': pledgee_boid,
				'prf_number': response_json['PledgeSetupResponse']['PRFNumber'],
				'expiry_date': expiry,
				'allowable_ltv': cart.allowable_ltv,
				'customer': cart.customer,
				'loan': cart.loan,
				'items': items
			})
			loan_application.insert(ignore_permissions=True)

			username = frappe.db.get_value('User', self.owner, 'full_name')
			args = {'username': username}
			template = "/templates/emails/loan_application_creation.html"
			frappe.enqueue(method=frappe.sendmail, recipients=self.owner, sender=None, 
			subject="Application Successful", message=frappe.get_template(template).render(args))

			mobile = frappe.db.get_value('User', self.owner, 'phone')
			mess = _("Dear " + username + " Your Loan Application is successfully received. Application number: " + loan_application.name + ". You will be notified once your OD limit is approved by our bank partner.")
			frappe.enqueue(method=send_sms, receiver_list=[mobile], msg=mess)	

			cart.is_processed = 1
			cart.save(ignore_permissions=True)

			if not customer.pledge_securities:
				customer.pledge_securities = 1
				customer.save(ignore_permissions=True)

			las_settings = frappe.get_single('LAS Settings')
			loan_aggrement_file = las_settings.esign_download_signed_file_url.format(file_id=file_id)
			file_ = frappe.get_doc({
				'doctype': 'File',
				'attached_to_doctype': 'Loan Application',
				'attached_to_name': loan_application.name,
				'file_url': loan_aggrement_file,
				'file_name': 'loan-aggrement.pdf'
			})
			file_.insert(ignore_permissions=True)
			
			frappe.db.set_value("User Token", otp_res[1], "used", 1)
			return lms.generateResponse(message="CDSL", data=loan_application)
		else:
			return lms.generateResponse(is_success=False, message="CDSL Pledge Error", data=response_json)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def process_dummy(cart_name):
	cart = frappe.get_doc('Cart', cart_name)
	items = []
	for item in cart.items:
			item = frappe.get_doc({
				'doctype': 'Loan Application Item',
				'isin': item.isin,
				'security_name': item.security_name,
				'security_category': item.security_category,
				'pledged_quantity': item.pledged_quantity,
				'price': item.price,
				'amount': item.amount,
				'psn': 'psn',
				'error_code': 'error_code',
			})
			items.append(item)

	loan_application = frappe.get_doc({
		'doctype': 'Loan Application',
		'total_collateral_value': cart.total_collateral_value,
		'overdraft_limit': cart.eligible_loan,
		'pledgor_boid': 'pledgor',
		'pledgee_boid': 'pledgee',
		'prf_number': 'prf',
		'expiry_date': '2021-01-31',
		'allowable_ltv': cart.allowable_ltv,
		'customer': cart.customer,
		'loan': cart.loan,
		'items': items
	})
	loan_application.insert(ignore_permissions=True)

	username = frappe.db.get_value('User', self.owner, 'full_name')
	args = {'username': username}
	template = "/templates/emails/loan_application_creation.html"
	frappe.enqueue(method=frappe.sendmail, recipients=self.owner, sender=None, 
	subject="Application Successful", message=frappe.get_template(template).render(args))

	mobile = frappe.db.get_value('User', self.owner, 'phone')
	mess = _("Dear " + username + "Your Loan Application is successfully received. Application number: " + loan_application.name + ". You will be notified once your OD limit is approved by our bank partner.")
	frappe.enqueue(method=send_sms, receiver_list=[mobile], msg=mess)	
	cart.is_processed = 1
	cart.save(ignore_permissions=True)

	return loan_application.name

@frappe.whitelist()
def request_pledge_otp():
	try:
		# validation
		lms.validate_http_method('POST')

		lms.create_user_token(entity=frappe.session.user, token_type="Pledge OTP", token=lms.random_token(length=4, is_numeric=True))
		return lms.generateResponse(message=_('Pledge OTP sent'))
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)