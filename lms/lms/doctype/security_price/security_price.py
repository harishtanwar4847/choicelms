# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import lms
from frappe.model.document import Document
from datetime import datetime
from random import uniform
import requests
from requests.exceptions import RequestException

class SecurityPrice(Document):
	pass

def update_security_prices(securities_dict, session_id):
	try:
		# print(securities, session_id)
		# securities_ = frappe.get_all('Security', filters=[['name', 'in', securities]], fields=['name', 'segment', 'token_id'])
		# securities_dict = {}
		# for i in securities_:
		# 	securities_dict['{}@{}'.format(i.segment, i.token_id)] = i.name 

		las_settings = frappe.get_single('LAS Settings')
		get_latest_security_price_url = '{}{}'.format(las_settings.jiffy_host, las_settings.jiffy_security_get_latest_price_uri)

		payload = {
			'UserId': session_id,
			'SessionId': session_id,
			'MultipleTokens': ','.join(securities_dict.keys()),
		}
		response = requests.post(get_latest_security_price_url, json=payload)
		response_json = response.json()

		if response.ok and response_json.get("Status") == "Success":
			fields = ['name', 'security', 'time', 'price', 'creation', 'modified', 'owner', 'modified_by']
			values = {}
			for security in response_json.get('Response').get('lstMultipleTouchline'):
				isin = securities_dict.get('{}@{}'.format(security.get('SegmentId'), security.get('Token')))
				time = datetime.strptime(security.get('LUT'), '%d-%m-%Y %H:%M:%S')
				price = float(security.get('LTP')) / security.get('PriceDivisor')
				values['{}-{}'.format(isin, time)] = (
					'{}-{}'.format(isin, time),
					isin,
					time,
					price,
					time,
					time, 
					'Administrator',
					'Administrator'
				)

			# removing duplicates
			duplicates = [i.name for i in frappe.get_all('Security Price', fields=['name'], filters=[['name', 'in', values.keys()]])]
			for i in duplicates:
				del values[i]

			values_ = list(values.values())
			values_.append(())
			frappe.db.bulk_insert('Security Price', fields=fields, values=values_)
	except (RequestException, Exception) as e:
		frappe.log_error()

@frappe.whitelist()
def update_all_security_prices():
	try:
		chunks = lms.chunk_doctype(doctype='Security', limit=50)
		las_settings = frappe.get_single('LAS Settings')
		session_id_generator_url = '{}{}'.format(las_settings.jiffy_host, las_settings.jiffy_session_generator_uri)
		
		response = requests.get(session_id_generator_url)
		response_json = response.json()

		if response.ok and response_json.get("Status") == "Success":
			for start in chunks.get('chunks'):
				security_list = frappe.db.get_all('Security', fields=['name', 'segment', 'token_id'], limit_page_length=chunks.get('limit'), limit_start=start)

				securities_dict = {}
				for i in security_list:
					securities_dict['{}@{}'.format(i.segment, i.token_id)] = i.name 

				frappe.enqueue(
					method='lms.lms.doctype.security_price.security_price.update_security_prices', 
					securities_dict=securities_dict, 
					session_id = response_json.get('Response'),
					queue='long'
				)

			frappe.enqueue(
				method='lms.lms.doctype.loan.loan.check_all_loans_for_shortfall',
				queue='long'
			)
	except (RequestException, Exception) as e:
		frappe.log_error()
