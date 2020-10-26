import frappe
from frappe import _
import lms
from datetime import datetime, timedelta
from frappe.core.doctype.sms_settings.sms_settings import send_sms
import requests
from itertools import groupby
import utils

def validate_securities_for_cart(securities, lender):
	if not securities or (type(securities) is not dict and "list" not in securities.keys()):
		raise utils.ValidationException({'securities':{'required':_('Securities required.')}})
		
	securities = securities["list"]

	if len(securities) == 0:
		raise utils.ValidationException({'securities':{'required':_('Securities required.')}})

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
		if len(set(securities_list)) > 10:
			securities_valid = False
			message = _('max 10 isin allowed')
	
	if securities_valid:
		securities_list_from_db_ = frappe.db.sql("select isin from `tabAllowed Security` where lender = '{}' and isin in {}".format(lender, lms.convert_list_to_tuple_string(securities_list)))
		securities_list_from_db = [i[0] for i in securities_list_from_db_]
		print(securities_list_from_db)

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
			if "isin" not in keys or "quantity" not in keys:
				securities_valid = False
				message = _('any/all of isin, quantity, price not present')
				break

	if not securities_valid:
		raise utils.ValidationException({'securities':{'required':message}})

	return securities

@frappe.whitelist()
def upsert(**kwargs):
	try:
		utils.validator.validate_http_method('POST')

		data = utils.validator.validate(kwargs, {
			'securities': '',
			'cart_name': '',
			'loan_name': '',
			'lender': '',
			'expiry': '',
			'pledgor_boid': 'required'
		})

		if not data.get('lender', None):
			data['lender'] = frappe.get_last_doc('Lender').name

		if not data.get('expiry', None):
			expiry = datetime.now() + timedelta(days = 365)

		securities = validate_securities_for_cart(data.get('securities', {}), data.get('lender'))

		customer = lms.__customer()

		if data.get('loan_name', None):
			loan = frappe.get_doc('Loan', loan_name)
			if not loan:
				return utils.respondNotFound(message=_('Loan not found.'))
			if loan.customer != customer.name:
				return utils.respondForbidden(message=_('Please use your own loan.'))

		if not data.get('cart_name', None):
			cart = frappe.get_doc({
				"doctype": "Cart",
				"customer": customer.name,
				"lender": data.get('lender'),
				"pledgor_boid": data.get('pledgor_boid'),
				"expiry": expiry
			})
		else:
			cart = frappe.get_doc("Cart", data.get('cart_name'))
			if not cart:
				return utils.respondNotFound(message=_('Cart not found.'))
			if cart.customer != customer.name:
				return utils.respondForbidden(message=_('Please use your own cart.'))

			cart.items = []

		for i in securities:
			cart.append('items', {
				"isin": i["isin"],
				"pledged_quantity": i["quantity"],
			})
		cart.save(ignore_permissions=True)

		data = {
			'cart': utils.frappe_doc_proper_dict(cart)
		}

		if data.get('loan_name', None):
			loan_margin_shortfall = loan.get_margin_shortfall()
			cart.loan = loan.name
			cart.save(ignore_permissions=True)

			if not loan_margin_shortfall.get('__islocal', 0):
				data['minimum_pledge_amount_present'] = True
				data['minimum_pledge_amount'] = loan_margin_shortfall.shortfall_c * 2
				if loan_margin_shortfall.shortfall_c * 2 > cart.total_collateral_value:
					data['minimum_pledge_amount_present'] = False

		return utils.respondWithSuccess(data=data)
	except utils.APIException as e:
		return e.respond()

@frappe.whitelist()
def upsert_old(securities, cart_name=None, loan_name=None, expiry=None):
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
			if len(set(securities_list)) > 10:
				securities_valid = False
				message = _('max 10 isin allowed')
		
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

		if loan_name:
			loan = frappe.get_doc('Loan', loan_name)
			if not loan:
				return lms.generateResponse(status=404, message=_('Loan not found.'))
			if loan.customer != customer.name:
				return lms.generateResponse(status=403, message=_('Please use your own loan.'))

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

		data = cart

		if loan_name:
			loan_margin_shortfall = loan.get_margin_shortfall()
			cart.loan = loan_name
			cart.save(ignore_permissions=True)

			if not loan_margin_shortfall.get('__islocal', 0):
				data = {'cart': data, 'minimum_pledge_amount_present': True, 'minimum_pledge_amount': loan_margin_shortfall.shortfall_c * 2}
				if loan_margin_shortfall.shortfall_c * 2 > cart.total_collateral_value:
					data['minimum_pledge_amount_present'] = False
				

		return lms.generateResponse(message=_('Cart Saved'), data=data)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def process(**kwargs):
	try:
		utils.validator.validate_http_method('POST')

		data = utils.validator.validate(kwargs, {
			'cart_name': 'required',
			'expiry': ''
		})

		customer = lms.__customer()

		cart = frappe.get_doc("Cart", data.get('cart_name'))
		if not cart:
			return utils.respondNotFound(message=_('Cart not found.'))
		if cart.customer != customer.name:
			return utils.respondForbidden(message=_('Please use your own cart.'))

		pledge_request = cart.pledge_request()
		frappe.db.set_value('Cart', cart.name, 'prf_number', pledge_request.get('payload').get('PRFNumber'))
		
		try:
			res = requests.post(pledge_request.get('url'), headers=pledge_request.get('headers'), json=pledge_request.get('payload'))
			data = res.json()
			
			# Pledge LOG
			log = {
				'url': pledge_request.get('url'),
				'headers': pledge_request.get('headers'),
				'request': pledge_request.get('payload'),
				'response': data,
			}

			import json
			import os
			pledge_log_file = frappe.utils.get_files_path('pledge_log.json')
			pledge_log = None
			if os.path.exists(pledge_log_file):
				with open(pledge_log_file, 'r') as f:
					pledge_log = f.read()
				f.close()
			pledge_log = json.loads(pledge_log or "[]")
			pledge_log.append(log)
			with open(pledge_log_file, 'w') as f:
				f.write(json.dumps(pledge_log))
			f.close()
			# Pledge LOG end

			if not res.ok or not data.get('Success'):
				raise lms.PledgeSetupFailureException
			
			cart.reload()
			cart.process(data)
			cart.save(ignore_permissions=True)
			loan_application = cart.create_loan_application()

			return utils.respondWithSuccess(data=utils.frappe_doc_proper_dict(loan_application))
		except requests.RequestException as e:
			raise utils.APIException(str(e))
	except utils.APIException as e:
		return e.respond()

@frappe.whitelist()
def process_old(cart_name, otp, pledgor_boid, file_id=None, expiry=None, pledgee_boid=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not cart_name:
			raise lms.ValidationError(_('Cart name required.'))
		if len(otp) != 4 or not otp.isdigit():
			raise lms.ValidationError(_('Enter 4 digit OTP.'))
		if not pledgor_boid:
			raise lms.ValidationError(_('Pledgod BOID required.'))

		otp_res = lms.check_user_token(entity=frappe.session.user, token=otp, token_type="Pledge OTP")
		if not otp_res[0]:
			raise lms.ValidationError(_('Wrong OTP.'))

		cart = frappe.get_doc("Cart", cart_name)
		customer = lms.get_customer(frappe.session.user)
		if not cart:
			return lms.generateResponse(status=404, message=_('Cart not found.'))
		if cart.customer != customer.name:
			return lms.generateResponse(status=403, message=_('Please use your own cart.'))

		if not pledgee_boid:
			pledgee_boid = '1206690000014023'
		if not expiry:
			expiry = datetime.now() + timedelta(days = 365)

		securities_array = []
		for i in cart.items:
			j = {
				"ISIN": i.isin,
				"Quantity": str(float(i.pledged_quantity)),
				"Value": str(float(i.price))
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
			pledge_failure = False

			response_json_item_groups = {}
			for key, group in groupby(response_json['PledgeSetupResponse']['ISINstatusDtls'], key=lambda x: x['ISIN']):
				response_json_item_groups[key] = list(group)[0]
				if len(response_json_item_groups[key]['ErrorCode']) > 0:
					pledge_failure = True

			# if pledge_failure:
			# 	return lms.generateResponse(is_success=False, message="CDSL Pledge Total Failure")

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
				'drawing_power': cart.eligible_loan,
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

			doc = frappe.get_doc('User', frappe.session.user)
			frappe.enqueue_doc('Notification', 'Loan Application Creation', method='send', doc=doc)

			mess = _("Dear " + doc.full_name + ",\nYour pledge request and Loan Application was successfully accepted. \nPlease download your e-agreement - <Link>. \nApplication number: " + loan_application.name + ". \nYou will be notified once your OD limit is approved by our bank partner.")
			frappe.enqueue(method=send_sms, receiver_list=[doc.phone], msg=mess)	

			cart.is_processed = 1
			cart.save(ignore_permissions=True)

			if not customer.pledge_securities:
				customer.pledge_securities = 1
				customer.save(ignore_permissions=True)

			if file_id:
				lms.save_signed_document(file_id, doctype='Loan Application', docname=loan_application.name)
			
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
		'drawing_power': cart.eligible_loan,
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

	cart.is_processed = 1
	cart.save(ignore_permissions=True)

	doc = frappe.get_doc('User', frappe.session.user)
	frappe.enqueue_doc('Notification', 'Loan Application Creation', method='send', doc= doc)

	mess = _("Dear " + doc.full_name + ",\nYour pledge request and Loan Application was successfully accepted. \nPlease download your e-agreement - <Link>. \nApplication number: " + loan_application.name + ". \nYou will be notified once your OD limit is approved by our bank partner.")
	frappe.enqueue(method=send_sms, receiver_list=[doc.phone], msg=mess)	

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