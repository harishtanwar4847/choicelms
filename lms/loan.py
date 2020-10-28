import frappe
from frappe import _
import utils
import lms
import requests

@frappe.whitelist()
def esign(**kwargs):
	try:
		utils.validator.validate_http_method('POST')

		data = utils.validator.validate(kwargs, {
			'loan_application_name': 'required',
		})

		customer = lms.__customer()
		loan_application = frappe.get_doc('Loan Application', data.get('loan_application_name'))
		if not loan_application:
			return utils.respondNotFound(message=_('Loan Application not found.'))
		if loan_application.customer != customer.name:
			return utils.respondForbidden(message=_('Please use your own Loan Application.'))

		user = lms.__user()

		esign_request = loan_application.esign_request()
		try:
			res = requests.post(esign_request.get('file_upload_url'), files=esign_request.get('files'), headers=esign_request.get('headers'))

			if not res.ok:
				raise utils.APIException(res.text)

			data = res.json()

			esign_url_dict = esign_request.get('esign_url_dict') 
			esign_url_dict['id'] = data.get('id')
			url = esign_request.get('esign_url').format(**esign_url_dict)

			return utils.respondWithSuccess(message=_('Esign URL.'), data={'esign_url': url, 'file_id': data.get('id')})
		except requests.RequestException as e:
			raise utils.APIException(str(e))
	except utils.APIException as e:
		return e.respond()

@frappe.whitelist()
def esign_done(**kwargs):
	try:
		utils.validator.validate_http_method('POST')

		data = utils.validator.validate(kwargs, {
			'loan_application_name': 'required',
			'file_id': 'required'
		})

		customer = lms.__customer()
		loan_application = frappe.get_doc('Loan Application', data.get('loan_application_name'))
		if not loan_application:
			return utils.respondNotFound(message=_('Loan Application not found.'))
		if loan_application.customer != customer.name:
			return utils.respondForbidden(message=_('Please use your own Loan Application.'))

		las_settings = frappe.get_single('LAS Settings')
		esigned_pdf_url = las_settings.esign_download_signed_file_url.format(file_id=data.get('file_id'))

		try:
			res = requests.get(esigned_pdf_url, allow_redirects=True)
			esigned_file = frappe.get_doc({
				'doctype': 'File',
				'file_name': '{}-aggrement.pdf'.format(data.get('loan_application_name')),
				'content': res.content,
				'attached_to_doctype': 'Loan Application',
				'attached_to_name': data.get('loan_application_name'),
				'attached_to_field': 'customer_esigned_document',
				'folder': 'Home'
			})
			esigned_file.save(ignore_permissions=True)

			loan_application.status = 'Esign Done'
			loan_application.workflow_state = 'Esign Done'
			loan_application.save(ignore_permissions=True)

			return utils.respondWithSuccess()
		except requests.RequestException as e:
			raise utils.APIException(str(e))
	except utils.APIException as e:
		return e.respond()

@frappe.whitelist()
def my_loans():
	try:
		customer = lms.get_customer(frappe.session.user)

		loans = frappe.db.sql("""select 
			loan.total_collateral_value, loan.name, loan.sanctioned_limit, loan.drawing_power,

			if (loan.total_collateral_value * loan.allowable_ltv / 100 > loan.sanctioned_limit, 1, 0) as top_up_available,

			if (loan.total_collateral_value * loan.allowable_ltv / 100 > loan.sanctioned_limit, 
			loan.total_collateral_value * loan.allowable_ltv / 100 - loan.sanctioned_limit, 0.0) as top_up_amount,

			IFNULL(mrgloan.shortfall_percentage, 0.0) as shortfall_percentage, 
			IFNULL(mrgloan.shortfall_c, 0.0) as shortfall_c,
			IFNULL(mrgloan.shortfall, 0.0) as shortfall,

			SUM(COALESCE(CASE WHEN loantx.record_type = 'DR' THEN loantx.amount END,0)) 
			- SUM(COALESCE(CASE WHEN loantx.record_type = 'CR' THEN loantx.amount END,0)) outstanding 

			from `tabLoan` as loan
			left join `tabLoan Margin Shortfall` as mrgloan
			on loan.name = mrgloan.loan 
			left join `tabLoan Transaction` as loantx
			on loan.name = loantx.loan
			where loan.customer = '{}' group by loantx.loan """.format(customer.name), as_dict = 1)

		data = {'loans': loans}
		data['total_outstanding'] = float(sum([i.outstanding for i in loans]))
		data['total_sanctioned_limit'] = float(sum([i.sanctioned_limit for i in loans]))
		data['total_drawing_power'] = float(sum([i.drawing_power for i in loans]))
		data['total_total_collateral_value'] = float(sum([i.total_collateral_value for i in loans]))
		data['total_margin_shortfall'] = float(sum([i.shortfall_c for i in loans]))

		return lms.generateResponse(message=_('Loan'), data=data)

	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)

def create_loan_collateral(loan_name, pledgor_boid, pledgee_boid, prf_number, items):
	for item in items:
		loan_collateral = frappe.get_doc({
			"doctype":"Loan Collateral",
			"loan":loan_name,
			"request_type":"Pledge",
			"pledgor_boid":pledgor_boid,
			"pledgee_boid":pledgee_boid,
			"request_identifier":prf_number,
			"isin":item.isin,
			"quantity": item.pledged_quantity,
			"psn": item.psn,
			"error_code": item.error_code,
			"is_success": item.psn and not item.error_code
		})
		loan_collateral.insert(ignore_permissions=True)

@frappe.whitelist()
def create_unpledge(loan_name, securities_array):
	try : 
		lms.validate_http_method("POST")

		if not loan_name:
			raise lms.ValidationError(_('Loan name required.'))
	
		if not securities_array and type(securities_array) is not list:
			raise lms.ValidationError(_('Securities required.'))    
		
		securities_valid = True

		for i in securities_array:
			if type(i) is not dict:
				securities_valid = False
				message = _('items in securities need to be dictionaries')
				break
			
			keys = i.keys()
			if "isin" not in keys or "quantity" not in keys:
				securities_valid = False
				message = _('any/all of isin, quantity not present')
				break

			if type(i["isin"]) is not str or len(i["isin"]) > 12:
				securities_valid = False
				message = _('isin not correct')
				break

			if not frappe.db.exists('Allowed Security', i['isin']):
				securities_valid = False
				message = _('{} isin not found').format(i['isin'])
				break       
			
			valid_isin = frappe.db.sql("select sum(quantity) total_pledged from `tabLoan Collateral` where request_type='Pledge' and loan={} and isin={}".format(loan_name,i["isin"]), as_dict=1)
			if not valid_isin:
				securities_valid = False
				message = _('invalid isin')
				break
			elif i['quantity'] <= valid_isin[0].total_pledged:
				securities_valid = False
				message = _('invalid unpledge quantity')
				break

		if securities_valid:
			securities_list = [i['isin'] for i in securities]
			
			if len(set(securities_list)) != len(securities_list):
				securities_valid = False
				message = _('duplicate isin')
			
		if not securities_valid:
			raise lms.ValidationError(message)
				
		loan = frappe.get_doc("Loan", loan_name)    
		if not loan:
			return lms.generateResponse(status=404, message=_('Loan {} does not exist.'.format(loan_name)))
		
		customer = lms.get_customer(frappe.session.user)
		if loan.customer != customer.name:
			return lms.generateResponse(status=403, message=_('Please use your own loan.'))

		UNPLDGDTLS = []
		for unpledge in securities_array:
			isin_data = frappe.db.sql("select isin, psn, quantity from `tabLoan Collateral` where request_type='Pledge' and loan={} and isin={} order by creation ASC".format(loan_name,unpledge["isin"]), as_dict=1)
			unpledge_qty = unpledge.quantity

			for pledged_item in isin_data:
				if unpledge_qty == 0:
					break
				
				removed_qty_from_current_pledge_entity = 0

				if unpledge_qty >= pledged_item.quantity:
					removed_qty_from_current_pledge_entity = pledged_item.quantity
				else:
					removed_qty_from_current_pledge_entity = pledged_item.quantity - unpledge_qty

				body_item = {
						"PRNumber":pledged_item.prn,
						"PartQuantity": removed_qty_from_current_pledge_entity
					}
				UNPLDGDTLS.append(body_item)

				unpledge_qty -= removed_qty_from_current_pledge_entity

		las_settings = frappe.get_single("LAS Settings")
		API_URL = '{}{}'.format(las_settings.cdsl_host, las_settings.unpledge_setup_uri)
		payload = {
					  "URN": "URN" + lms.random_token(length=13, is_numeric=True),
					  "UNPLDGDTLS": json.loads(UNPLDGDTLS)
					}

		response = requests.post(
			API_URL,
			headers=las_settings.cdsl_headers(),
			json=payload
		)

		response_json = response.json()
		frappe.logger().info({'CDSL UNPLEDGE HEADERS': las_settings.cdsl_headers(), 'CDSL UNPLEDGE PAYLOAD': payload, 'CDSL UNPLEDGE RESPONSE': response_json})

		if response_json and response_json.get("Success") == True:
			return lms.generateResponse(message="CDSL", data=response_json)
		else:
			return lms.generateResponse(is_success=False, message="CDSL UnPledge Error", data=response_json)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return generateResponse(is_success=False, error=e)

@frappe.whitelist()
def create_topup(loan_name, file_id):
	try :
		lms.validate_http_method("POST")

		if not loan_name:
			raise lms.ValidationError(_('Loan name required.'))

		loan = frappe.get_doc("Loan", loan_name)
		if not loan:
			return lms.generateResponse(status=404, message=_("Loan {} does not exist".format(loan_name)))

		customer = lms.get_customer(frappe.session.user)
		if loan.customer != customer.name:
			return lms.generateResponse(status=403, message=_("Please use your own loan"))

		# check if topup available
		top_up_available = (loan.total_collateral_value * (loan.allowable_ltv / 100)) > loan.sanctioned_limit
		if not top_up_available :
			raise lms.ValidationError(_('Topup not available.'))

		topup_amt = (loan.total_collateral_value * (loan.allowable_ltv / 100)) - loan.sanctioned_limit
		loan.drawing_power += topup_amt
		loan.sanctioned_limit += topup_amt
		loan.save(ignore_permissions=True)

		lms.save_signed_document(file_id, doctype='Loan', docname=loan.name)

		return lms.generateResponse(message="Topup added successfully.", data=loan)
					
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return generateResponse(is_success=False, error=e)
	