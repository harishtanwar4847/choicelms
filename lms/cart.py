import frappe
from frappe import _
import lms
from datetime import datetime, timedelta
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

		if securities_valid:
			isin_list = []
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
				isin_list.append(i['isin'])

				if not frappe.db.exists('Allowed Security Master', i['isin']):
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
			
			if len(set(isin_list)) != len(securities):
				securities_valid = False
				message = _('duplicate isin')



		if not securities_valid:
			raise lms.ValidationError(message)

		if not expiry:
			expiry = datetime.now() + timedelta(days = 365)


		items = []
		for i in securities:
			item = frappe.get_doc({
				"doctype": "Cart Item",
				"isin": i["isin"],
				"pledged_quantity": i["quantity"],
				"price": i["price"] 
			})

			items.append(item)

		if not cart_name:
			cart = frappe.get_doc({
				"doctype": "Cart",
				"items": items
			})
			cart.insert()
		else:
			cart = frappe.get_doc("Cart", cart_name)
			if not cart:
				return lms.generateResponse(status=404, message=_('Cart not found.'))
			if cart.owner != frappe.session.user:
				return lms.generateResponse(status=403, message=_('Please use your own cart.'))

			cart.items = items
			cart.save()

		return lms.generateResponse(message=_('Cart Saved'), data=cart)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

@frappe.whitelist()
def process(cart_name, pledgor_boid=None, expiry=None, pledgee_boid=None):
	try:
		# validation
		lms.validate_http_method('POST')

		if not cart_name:
			raise lms.ValidationError(_('Cart name required.'))

		cart = frappe.get_doc("Cart", cart_name)
		if not cart:
			return lms.generateResponse(status=404, message=_('Cart not found.'))
		if cart.owner != frappe.session.user:
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
					'security_category': item.security_category,
					'pledged_quantity': item.pledged_quantity,
					'price': item.price,
					'amount': item.eligible_amount,
					'psn': response_json_item_groups[item.isin]['PSN'],
					'error_code': response_json_item_groups[item.isin]['ErrorCode'],
				})
				items.append(item)

			loan_application = frappe.get_doc({
				'doctype': 'Loan Application',
				'total': cart.eligible_amount,
				'pledgor_boid': pledgor_boid,
				'pledgee_boid': pledgee_boid,
				'prf_number': response_json['PledgeSetupResponse']['PRFNumber'],
				'expiry_date': expiry,
				'items': items
			})
			loan_application.insert(ignore_permissions=True)

			return lms.generateResponse(message="CDSL", data=loan_application)
		else:
			return lms.generateResponse(is_success=False, message="CDSL Pledge Error", data=response_json)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)