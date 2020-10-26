# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import lms
from datetime import datetime, timedelta

class Cart(Document):
	def get_customer(self):
		return frappe.get_doc('Customer', self.customer)

	def get_lender(self):
		return frappe.get_doc('Lender', self.lender)

	def loan_agreement(self):
		doc = {
			'full_name': 'John Doe', 
			'address': 'Canada, North America',
			'sanctioned_credit_limit':'25000',
			'rate_of_interest1':'15',
			'rate_of_interest2':'18',
			'processing_fee':'257',
			'account_renewal_charges':'350',
			'documentation_charges':'160',
			'processing_charges_per_req':'130',
		}
		agreement_form = frappe.render_template('templates/loan_agreement_form.html', {'doc': doc})
		from frappe.utils.pdf import get_pdf
		agreement_form_pdf = get_pdf(agreement_form)

		from PyPDF2 import PdfFileMerger
		merger = PdfFileMerger()

		from io import BytesIO
		pdfs = [frappe.get_app_path('lms', 'loan_tnc.pdf'), BytesIO(agreement_form_pdf)]

		for i in pdfs:
			merger.append(i)

		loan_agreement_pdf = frappe.utils.get_files_path('{}.pdf'.format(self.name))
		merger.write(loan_agreement_pdf)

		with open(loan_agreement_pdf, 'rb') as f:
			return f.read()

	def pledge_request(self):
		las_settings = frappe.get_single('LAS Settings')
		API_URL = '{}{}'.format(las_settings.cdsl_host, las_settings.pledge_setup_uri)

		securities_array = []
		for i in self.items:
			j = {
				"ISIN": i.isin,
				"Quantity": str(float(i.pledged_quantity)),
				"Value": str(float(i.price))
			}
			securities_array.append(j)

		payload = {
			"PledgorBOID": self.pledgor_boid,
			"PledgeeBOID": self.pledgee_boid,
			"PRFNumber": '{}R{}'.format(self.name, datetime.now().strftime('%s')),
			"ExpiryDate": self.expiry.strftime('%d%m%Y'),
			"ISINDTLS": securities_array
		}

		headers = las_settings.cdsl_headers()

		return {
			'url': API_URL,
			'headers': headers,
			'payload': payload
		}

	def process(self, pledge_response):
		if self.status != 'Not Processed':
			return

		isin_details_ = pledge_response.get('PledgeSetupResponse').get('ISINstatusDtls')
		isin_details = {}
		for i in isin_details_:
			isin_details[i.get('ISIN')] = i

		self.total_collateral_value = 0
		self.allowable_ltv = 0
		total_successful_pledge = 0
		
		for i in self.items:
			cur = isin_details.get(i.get('isin'))
			i.psn = cur.get('PSN')
			i.error_code = cur.get('ErrorCode')

			success = len(i.psn) > 0

			if success:
				if self.status == 'Not Processed':
					self.status = 'Success'
				elif self.status == 'Failure':
					self.status = 'Partial Success'
				self.total_collateral_value += i.amount
				self.allowable_ltv += i.eligible_percentage
				total_successful_pledge += 1
			else:
				if self.status == 'Not Processed':
					self.status = 'Failure'
				elif self.status == 'Success':
					self.status = 'Partial Success'

		if total_successful_pledge == 0:
			raise lms.PledgeSetupFailureException('Pledge Setup failed.')
		
		self.allowable_ltv = self.allowable_ltv / total_successful_pledge
		self.eligible_loan = (self.allowable_ltv / 100) * self.total_collateral_value

	def save_collateral_ledger(self):
		for i in self.items:
			collateral_ledger = frappe.get_doc({
				'doctype': 'Collateral Ledger',
				
				'cart': self.name,
				'customer': self.customer,
				'lender': self.lender,

				'request_type': 'Pledge',
				'request_identifier': self.prf_number,
				'expiry': self.expiry,

				'pledgor_boid': self.pledgor_boid,
				'pledgee_boid': self.pledgee_boid,

				'isin': i.isin,
				'quantity': i.quantity,
				'psn': i.psn,
				'error_code': i.error_code,
				'is_success': len(i.psn) > 0
			})
			collateral_ledger.save(ignore_permissions=True)


	def create_loan_application(self):
		if self.status == 'Not Processed':
			return
		
		self.save_collateral_ledger()
		
		items = []
		for item in self.items:
			if len(item.psn) > 0:
				item = frappe.get_doc({
					'doctype': 'Loan Application Item',
					'isin': item.isin,
					'security_name': item.security_name,
					'security_category': item.security_category,
					'pledged_quantity': item.pledged_quantity,
					'price': item.price,
					'amount': item.amount,
					'psn': item.psn,
					'error_code': item.error_code,
				})
				items.append(item)

		loan_application = frappe.get_doc({
			'doctype': 'Loan Application',
			'total_collateral_value': self.total_collateral_value,
			'drawing_power': self.eligible_loan,
			'pledgor_boid': self.pledgor_boid,
			'pledgee_boid': self.pledgee_boid,
			'prf_number': self.prf_number,
			'expiry_date': self.expiry,
			'allowable_ltv': self.allowable_ltv,
			'customer': self.customer,
			'loan': self.loan,
			'items': items
		})
		loan_application.insert(ignore_permissions=True)
		
		return loan_application

	def before_save(self):
		self.process_cart_items()
		self.process_cart()

	def process_cart_items(self):
		if self.status == 'Not Processed':
			self.pledgee_boid = self.get_lender().demat_account_number
			isin = [i.isin for i in self.items]
			price_map = lms.get_security_prices(isin)
			allowed_securities = lms.get_allowed_securities(isin, self.lender)

			for i in self.items:
				security = allowed_securities.get(i.isin)
				i.security_category = security.category
				i.security_name = security.security_name
				i.eligible_percentage = security.eligible_percentage

				i.price = price_map.get(i.isin, 0)
				i.amount = i.pledged_quantity * i.price

	def process_cart(self):
		if self.status == 'Not Processed':
			self.total_collateral_value = 0
			self.allowable_ltv = 0
			for item in self.items:
				self.total_collateral_value += item.amount
				self.allowable_ltv += item.eligible_percentage
			
			self.allowable_ltv = float(self.allowable_ltv) / len(self.items)
			self.eligible_loan = (self.allowable_ltv / 100) * self.total_collateral_value

	def process_bre(self):
		las_settings = frappe.get_single('LAS Settings')
		self.eligible_amount = 0

		for item in self.items:
			item.eligible_amount = item.amount * (las_settings.loan_margin / 100)
			self.eligible_amount += item.eligible_amount

	def validate_bre(self):
		is_single_script = True if len(self.items) == 1 else False
		for item in self.items:
			concentration_rule = item.get_concentration_rule()
			item.bre_passing = 1
			item.bre_validation_message = None

			# single script rule
			if is_single_script:
				if concentration_rule.is_single_script_allowed:
					process_concentration_rule(
						item=item, 
						amount=item.amount,
						rule=concentration_rule,
						rule_type='single_script_threshold',
						total=self.total
					)
				else:
					item.bre_passing = 0
					item.bre_validation_message = "Single script not allowed."

				# continue to next item if bre fails
				if not item.bre_passing:
					continue

			# group script rule
			if not is_single_script:
				category_amount_sum = 0
				for i in self.items:
					if i.security_category == item.security_category:
						category_amount_sum += item.amount

				if concentration_rule.is_group_script_limited:
					# per script rule
					if concentration_rule.per_script_threshold > 0:
						process_concentration_rule(
							item=item,
							amount=item.amount, 
							rule=concentration_rule,
							rule_type='per_script_threshold',
							total=self.total
						)

					# continue to next item if bre fails
					if not item.bre_passing:
						continue
					
					# group script rule
					if concentration_rule.group_script_threshold > 0:
						process_concentration_rule(
							item=item,
							amount=category_amount_sum, 
							rule=concentration_rule,
							rule_type='group_script_threshold',
							total=self.total
						)

					# continue to next item if bre fails
					if not item.bre_passing:
						continue

				# max script rule
				if concentration_rule.is_group_script_max_limited:
					if concentration_rule.group_script_max_limit > 0:
						process_concentration_rule(
							item=item,
							amount=category_amount_sum, 
							rule=concentration_rule,
							rule_type='group_script_max_limit',
							total=self.total
						)
		
		self.bre_passing = all([item.bre_passing for item in self.items])

def process_concentration_rule(item, amount, rule, rule_type, total):
	threshold = rule.get(rule_type)
	threshold_type = rule.get("{}_type".format(rule_type))
	threshold_amt = threshold if threshold_type == "Amount" else (threshold/100.0) * total
	
	if amount > threshold_amt:
		item.bre_passing = 0
		item.bre_validation_message = "Script Amount should not exceed {}.".format(threshold_amt)

def get_permission_query_conditions(user):
	if not user: user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None
	elif "Lender" in frappe.get_roles(user):
		roles = frappe.get_roles(user)

		return """(`tabCart`.lender in {role_tuple})"""\
			.format(role_tuple=lms.convert_list_to_tuple_string(roles))