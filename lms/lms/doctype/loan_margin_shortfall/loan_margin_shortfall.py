# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.core.doctype.sms_settings.sms_settings import send_sms
import math

class LoanMarginShortfall(Document):
	def before_save(self):
		self.fill_items()

	def fill_items(self):
		loan = frappe.get_doc('Loan', self.loan)

		self.total_collateral_value = loan.total_collateral_value
		self.allowable_ltv = loan.allowable_ltv
		self.drawing_power = loan.drawing_power

		self.loan_balance = loan.balance
		self.ltv = (self.loan_balance/self.total_collateral_value) * 100
		self.surplus_margin = 100 - self.ltv
		self.minimum_collateral_value = (100/self.allowable_ltv) * self.loan_balance 

		self.shortfall = math.ceil((self.minimum_collateral_value - self.total_collateral_value) if self.loan_balance > self.drawing_power else 0)
		self.shortfall_c = math.ceil(((self.loan_balance - self.drawing_power)*2) if self.loan_balance > self.drawing_power else 0)
		self.shortfall_percentage = ((self.loan_balance - self.drawing_power) / 100) if self.loan_balance > self.drawing_power else 0

		self.minimum_pledge_amount = self.shortfall_c
		self.advisable_pledge_amount = math.ceil(self.minimum_pledge_amount * 1.1)
		self.minimum_cash_amount = (self.allowable_ltv / 100) * self.shortfall_c
		self.advisable_cash_amount = math.ceil(self.minimum_cash_amount * 1.1)

		self.set_shortfall_action()

	def set_shortfall_action(self):
		self.margin_shortfall_action = None
		
		action_list = frappe.get_all('Margin Shortfall Action', filters={'threshold': ('<=', self.shortfall_percentage)}, order_by='threshold desc', page_length=1)
		if len(action_list):
			self.margin_shortfall_action = action_list[0].name

	def after_insert(self):
		self.notify_customer()
	
	def get_loan(self):
		return frappe.get_doc('Loan', self.loan)

	def get_shortfall_action(self):
		return frappe.get_doc('Margin Shortfall Action', self.margin_shortfall_action)

	def notify_customer(self):
		margin_shortfall_action = self.get_shortfall_action()
		customer = self.get_loan().get_customer()
		mess = _('Your Loan {0} has been marked as margin shortfall.').format(self.loan)

		if margin_shortfall_action.sms:
			frappe.enqueue(method=send_sms, receiver_list=[customer.phone], msg=mess)

		if margin_shortfall_action.email:
			frappe.enqueue(
				method=frappe.sendmail, 
				recipients=[customer.email], 
				sender=None, 
				subject="Margin Shortfall Notification",
				message=mess
			)