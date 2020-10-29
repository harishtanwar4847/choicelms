# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from lms.loan import create_loan_collateral
from num2words import num2words
import lms
class LoanApplication(Document):
	def get_lender(self):
		return frappe.get_doc('Lender', self.lender)

	def get_customer(self):
		return frappe.get_doc('Customer', self.customer)
	
	def esign_request(self):
		customer = self.get_customer()
		user = frappe.get_doc('User', customer.username)
		user_kyc = frappe.get_doc('User KYC', customer.choice_kyc)
		lender = self.get_lender()
		doc = {
			'borrower_name': user.full_name, 
			'borrower_address': user_kyc.address,
			'sanctioned_amount': self.drawing_power,
			'sanctioned_amount_in_words': num2words(self.drawing_power, lang='en_IN'),
			'rate_of_interest': lender.rate_of_interest,
			'default_interest': lender.default_interest,
			'account_renewal_charges': lender.account_renewal_charges,
			'documentation_charges': lender.documentation_charges,
			'processing_fee': lender.lender_processing_fees,
			'transaction_charges_per_request': lender.transaction_charges_per_request,
			'security_selling_share': lender.security_selling_share,
			'cic_charges': lender.cic_charges,
			'total_pages': lender.total_pages,
		}

		agreement_template = lender.get_loan_agreement_template()
		agreement = frappe.render_template(agreement_template.get_content(), {'doc': doc})
		
		from frappe.utils.pdf import get_pdf
		agreement_pdf = get_pdf(agreement)

		coordinates = lender.coordinates.split(',')

		las_settings = frappe.get_single('LAS Settings')
		headers = {'userId': las_settings.choice_user_id}
		files = {'file': ('loan-aggrement.pdf', agreement_pdf)}

		return {
			'file_upload_url': las_settings.esign_upload_file_url,
			'headers': headers,
			'files': files,
			'esign_url_dict': {
				'x': coordinates[0],
				'y': coordinates[1],
				'page_number': lender.esign_page
			},
			'esign_url': las_settings.esign_request_url
		}

	def on_update(self):
		if self.status == 'Approved':
			if not self.loan:
				loan=self.create_loan()
			else:
				loan=self.update_existing_loan()

	def before_save(self):
		if self.status == 'Approved' and not self.lender_esigned_document:
			frappe.throw('Please upload Lender Esigned Document')

	def create_loan(self):
		items = []

		for item in self.items:
			temp = frappe.get_doc({
				'doctype': 'Loan Item',
				'isin': item.isin,
				'security_name': item.security_name,
				'security_category': item.security_category,
				'pledged_quantity': item.pledged_quantity,
				'price': item.price,
				'amount': item.amount,
				'psn': item.psn,
				'error_code': item.error_code,
			})

			items.append(temp)

		loan = frappe.get_doc({
			'doctype': 'Loan',
			'total_collateral_value': self.total_collateral_value,
			'drawing_power': self.drawing_power,
			'sanctioned_limit': self.drawing_power,
			'expiry_date': self.expiry_date,
			'allowable_ltv': self.allowable_ltv,
			'customer': self.customer,
			'lender': self.lender,
			'items': items,
		})
		loan.insert(ignore_permissions=True)

		file_name = frappe.db.get_value('File', {'file_url': self.lender_esigned_document})
		loan_agreement = frappe.get_doc('File', file_name)
		loan_agreement_file = frappe.get_doc({
			'doctype': 'File',
			'file_name': '{}-loan-aggrement.pdf'.format(loan.name),
			'content': loan_agreement.get_content(),
			'attached_to_doctype': 'Loan',
			'attached_to_name': loan.name,
			'attached_to_field': 'loan_agreement',
			'folder': 'Home'
		})
		loan_agreement_file.save(ignore_permissions=True)

		loan.loan_agreement = loan_agreement.file_url
		loan.save(ignore_permissions=True)

		customer = frappe.db.get_value('Customer', {'name': self.customer}, 'username')
		doc = frappe.get_doc('User', customer)
		frappe.enqueue_doc('Notification', 'Loan Sanction', method='send', doc=doc)

		mobile = frappe.db.get_value('Customer', {'name': self.customer}, 'user')
		mess = _("Dear " + doc.full_name + ", \nCongratulations! Your loan account is active now! \nCurrent available limit - " + str(loan.drawing_power) + ".")
		frappe.enqueue(method=send_sms, receiver_list=[mobile], msg=mess)

		customer = frappe.get_doc('Customer', self.customer)
		if not customer.loan_open:
			customer.loan_open = 1
			customer.save(ignore_permissions=True)
		self.update_collateral_ledger(loan.name)
		return loan

	def update_existing_loan(self):
		loan = frappe.get_doc('Loan', self.loan)

		for item in self.items:
			loan.append('items', {
				'isin': item.isin,
				'security_name': item.security_name,
				'security_category': item.security_category,
				'pledged_quantity': item.pledged_quantity,
				'price': item.price,
				'amount': item.amount,
				'psn': item.psn,
				'error_code': item.error_code,
			})

		loan.total_collateral_value += self.total_collateral_value
		loan.drawing_power += (loan.allowable_ltv/100) * loan.total_collateral_value

		loan.save(ignore_permissions=True)
		self.update_collateral_ledger(loan.name)
		return loan

	def update_collateral_ledger(self, loan_name):
		frappe.db.sql("""
			update `tabCollateral Ledger`
			set loan = '{}'
			where loan_application = '{}';
		""".format(loan_name, self.name))

def only_pdf_upload(doc, method):
	if doc.attached_to_doctype == 'Loan Application':
		if doc.file_name.split('.')[-1].lower() != 'pdf':
			frappe.throw('Kindly upload PDF files only.')

def get_permission_query_conditions(user):
	if not user: user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None
	elif "Lender" in frappe.get_roles(user):
		roles = frappe.get_roles(user)

		return """(`tabLoan Application`.lender in {role_tuple})"""\
			.format(role_tuple=lms.convert_list_to_tuple_string(roles))