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

	def loan_agreement(self):
		doc = {
			'full_name': 'John Doe', 
			'address': 'Canada, North America'
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

		# with open(loan_agreement_pdf, 'rb') as f:
		# 	return f.read()

	def pledge_request(self):
		las_settings = frappe.get_single('LAS Settings')
		API_URL = '{}{}'.format(las_settings.cdsl_host, las_settings.pledge_setup_uri)

		securities_array = []
		for i in cart.items:
			j = {
				"ISIN": i.isin,
				"Quantity": str(float(i.pledged_quantity)),
				"Value": str(float(i.price))
			}
			securities_array.append(j)

		expiry = datetime.now() + timedelta(days = 365)

		payload = {
			"PledgorBOID": self.pledgor_boid,
			"PledgeeBOID": las_settings.pledgee_boid,
			"PRFNumber": lms.get_cdsl_prf_no(),
			"ExpiryDate": expiry.strftime('%d%m%Y'),
			"ISINDTLS": securities_array
		}

		headers = las_settings.cdsl_headers()

		return {
			'url': API_URL,
			'headers': headers,
			'payload': payload
		}

	def before_save(self):
		self.process_cart_items()
		self.process_cart()

	def process_cart_items(self):
		isin = [i.isin for i in self.items]
		price_map = lms.get_security_prices(isin)
		securities = frappe.db.get_values(
			'Allowed Security',
			{'isin': ('in', isin), 'lender': self.lender},
			['category', 'security_name', 'eligible_percentage', 'isin'],
			as_dict=1
		)
		securities_map = {}
		for i in securities:
			securities_map[i.isin] = i

		for i in self.items:
			security = securities_map.get(i.isin)
			i.security_category = security.category
			i.security_name = security.security_name
			i.eligible_percentage = security.eligible_percentage

			i.price = price_map.get(i.isin, 0)
			i.amount = i.pledged_quantity * i.price

	def process_cart(self):
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