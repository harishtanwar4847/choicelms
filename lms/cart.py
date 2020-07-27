import frappe
from frappe import _
import lms
from datetime import datetime, timedelta

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


		if not securities_valid:
			raise lms.ValidationError(message)

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
				return lms.generateResponse(status=404, message=_('Cart not found.'))
			if cart.owner != frappe.session.user:
				return lms.generateResponse(status=403, message=_('Please use your own cart.'))

			cart.cart_items = cart_items
			cart.save()

		return lms.generateResponse(message=_('Cart Saved'), data=cart)
	except (lms.ValidationError, lms.ServerError) as e:
		return lms.generateResponse(status=e.http_status_code, message=str(e))
	except Exception as e:
		return lms.generateResponse(is_success=False, error=e)