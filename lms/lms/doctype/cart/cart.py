# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class Cart(Document):
	def before_save(self):
		self.calculate_total()
		self.process_bre()

	def calculate_total(self):
		total = 0
		for item in self.items:
			item.amount = item.pledged_quantity * item.price
			total += item.amount

			# updating security_category
			item.set_security_category()

		self.total = total

	def process_bre(self):
		las_settings = frappe.get_single('LAS Settings')

		eligible_amounts = []
		for item in self.items:
			item.eligible_amount = item.amount * (las_settings.loan_margin / 100)
			eligible_amounts.append(item.eligible_amount)

		self.eligible_amount = sum(eligible_amounts)

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
