# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import lms
from frappe.model.document import Document
from datetime import datetime
from random import uniform

class SecurityPrice(Document):
	pass

def update_security_prices(securities, start, total, show_progress=False):
	cur_doc = start
	fields = ['security', 'time', 'price', 'name', 'creation', 'modified', 'owner', 'modified_by']
	values = []
	for security in securities:
		cur_time = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
		values.append((
			security,
			cur_time,
			uniform(5, 30),
			'{}-{}'.format(security, cur_time),
			cur_time,
			cur_time, 
			'Administrator',
			'Administrator'
		))
		cur_doc += 1
		if show_progress:
			frappe.publish_progress((cur_doc / total) * 100, 'Updating Security Prices...')

	frappe.db.bulk_insert('Security Price', fields=fields, values=values)
	if cur_doc == total and show_progress:
		frappe.publish_realtime(event='eval_js', message='cur_list.refresh()', user=frappe.session.user)

@frappe.whitelist()
def update_all_security_prices(show_progress=False):
	chunks = lms.chunk_doctype(doctype='Allowed Security', limit=50)

	for start in chunks.get('chunks'):
		security_list = frappe.db.get_all('Allowed Security', limit_page_length=chunks.get('limit'), limit_start=start)

		frappe.enqueue(
			method='lms.lms.doctype.security_price.security_price.update_security_prices', 
			securities=[i.name for i in security_list], 
			start=start, 
			total=chunks.get('total'), 
			show_progress=show_progress,
			queue='long'
		)

	frappe.enqueue(
		method='lms.lms.doctype.loan.loan.check_all_loans_for_shortfall',
		queue='long'
	)