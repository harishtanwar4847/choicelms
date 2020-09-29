import frappe
from frappe import _
import lms

@frappe.whitelist()
def my_loans():
    try:
        customer = lms.get_customer(frappe.session.user)

        loans = frappe.db.sql("""select 
            loan.total_collateral_value, loan.name, mrgloan.shortfall, loan.drawing_power,
            mrgloan.shortfall_percentage, mrgloan.shortfall_c,
            SUM(COALESCE(CASE WHEN loantx.record_type = 'DR' THEN loantx.transaction_amount END,0)) 
			- SUM(COALESCE(CASE WHEN loantx.record_type = 'CR' THEN loantx.transaction_amount END,0)) outstanding 
            from `tabLoan` as loan
            left join `tabLoan Margin Shortfall` as mrgloan
            on loan.name = mrgloan.loan 
            left join `tabLoan Transaction` as loantx
            on loan.name = loantx.loan
            where loan.customer = '{}' group by loantx.loan """.format(customer.name), as_dict = 1)

        data = {'loans': loans}
        data['total_outstanding'] = sum([i.outstanding for i in loans])
        data['total_drawing_power'] = sum([i.drawing_power for i in loans])
        data['total_total_collateral_value'] = sum([i.total_collateral_value for i in loans])
        data['total_margin_shortfall'] = sum([i.shortfall_c for i in loans])

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
    
        if not securities_array and if type(securities_array) is not list:
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
            else if i['quantity'] <= valid_isin[0].total_pledged:
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