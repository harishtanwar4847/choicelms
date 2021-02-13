# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime

import frappe
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document
from num2words import num2words

import lms
from lms.exceptions.PledgeSetupFailureException import PledgeSetupFailureException


class LoanApplication(Document):
    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def esign_request(self):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()

        doc = {
            "esign_date": datetime.now().strftime("%d-%m-%Y"),
            "loan_application_number": self.name,
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            "sanctioned_amount": self.drawing_power,
            "sanctioned_amount_in_words": num2words(self.drawing_power, lang="en_IN"),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "account_renewal_charges": lender.account_renewal_charges,
            "documentation_charges": lender.documentation_charges,
            "processing_fee": lender.lender_processing_fees,
            "transaction_charges_per_request": lender.transaction_charges_per_request,
            "security_selling_share": lender.security_selling_share,
            "cic_charges": lender.cic_charges,
            "total_pages": lender.total_pages,
        }

        agreement_template = lender.get_loan_agreement_template()
        agreement = frappe.render_template(
            agreement_template.get_content(), {"doc": doc}
        )

        from frappe.utils.pdf import get_pdf

        agreement_pdf = get_pdf(agreement)

        coordinates = lender.coordinates.split(",")

        las_settings = frappe.get_single("LAS Settings")
        headers = {"userId": las_settings.choice_user_id}
        files = {"file": ("loan-aggrement.pdf", agreement_pdf)}

        return {
            "file_upload_url": "{}{}".format(
                las_settings.esign_host, las_settings.esign_upload_file_uri
            ),
            "headers": headers,
            "files": files,
            "esign_url_dict": {
                "x": coordinates[0],
                "y": coordinates[1],
                "page_number": lender.esign_page,
            },
            "esign_url": "{}{}".format(
                las_settings.esign_host, las_settings.esign_request_uri
            ),
        }

    def on_update(self):
        if self.status == "Approved":
            if not self.loan:
                loan = self.create_loan()
            else:
                loan = self.update_existing_loan()
            frappe.db.commit()
        elif self.status == "Pledge accepted by Lender":
            approved_isin_list = []
            rejected_isin_list = []
            for i in self.items:
                if self.lender_approval_status == "Approved":
                    approved_isin_list.append(i.isin)
                elif self.lender_approval_status == "Rejected":
                    rejected_isin_list.append(i.isin)

            if len(approved_isin_list) > 0:
                self.update_collateral_ledger(
                    {"lender_approval_status": "Approved"},
                    "loan_application = '{}' and isin IN {}".format(
                        self.name, approved_isin_list
                    ),
                )

            if len(rejected_isin_list) > 0:
                self.update_collateral_ledger(
                    {"lender_approval_status": "Rejected"},
                    "loan_application = '{}' and isin IN {}".format(
                        self.name, rejected_isin_list
                    ),
                )

    def before_save(self):
        if (
            self.status == "Approved"
            and not self.lender_esigned_document
            and not self.loan_margin_shortfall
        ):
            frappe.throw("Please upload Lender Esigned Document")
        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.drawing_power_str = lms.amount_formatter(self.drawing_power)
        self.pledged_total_collateral_value_str = lms.amount_formatter(
            self.pledged_total_collateral_value
        )

    def create_loan(self):
        items = []

        for item in self.items:
            temp = frappe.get_doc(
                {
                    "doctype": "Loan Item",
                    "isin": item.isin,
                    "security_name": item.security_name,
                    "security_category": item.security_category,
                    "pledged_quantity": item.pledged_quantity,
                    "price": item.price,
                    "amount": item.amount,
                    "psn": item.psn,
                    "error_code": item.error_code,
                }
            )

            items.append(temp)

        loan = frappe.get_doc(
            {
                "doctype": "Loan",
                "total_collateral_value": self.total_collateral_value,
                "drawing_power": self.drawing_power,
                "sanctioned_limit": self.drawing_power,
                "expiry_date": self.expiry_date,
                "allowable_ltv": self.allowable_ltv,
                "customer": self.customer,
                "customer_name": self.customer_name,
                "lender": self.lender,
                "items": items,
                "is_eligible_for_interest": 1,
            }
        )
        loan.insert(ignore_permissions=True)
        loan.create_loan_charges()

        file_name = frappe.db.get_value(
            "File", {"file_url": self.lender_esigned_document}
        )
        loan_agreement = frappe.get_doc("File", file_name)
        loan_agreement_file_name = "{}-loan-aggrement.pdf".format(loan.name)
        is_private = 0
        loan_agreement_file_url = frappe.utils.get_files_path(
            loan_agreement_file_name, is_private=is_private
        )
        loan_agreement_file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": loan_agreement_file_name,
                "content": loan_agreement.get_content(),
                "attached_to_doctype": "Loan",
                "attached_to_name": loan.name,
                "attached_to_field": "loan_agreement",
                "folder": "Home",
                "file_url": loan_agreement_file_url,
                "is_private": is_private,
            }
        )
        loan_agreement_file.insert(ignore_permissions=True)
        frappe.db.set_value(
            loan.doctype,
            loan.name,
            "loan_agreement",
            loan_agreement_file.file_url,
            update_modified=False,
        )

        customer = frappe.get_doc("Loan Customer", self.customer)
        if not customer.loan_open:
            customer.loan_open = 1
            customer.save(ignore_permissions=True)

        # self.update_collateral_ledger(loan.name)
        self.update_collateral_ledger(
            {"loan": loan.name}, "loan_application = '{}'".format(self.name)
        )

        customer = frappe.db.get_value("Loan Customer", {"name": self.customer}, "user")
        doc = frappe.get_doc("User", customer)
        frappe.enqueue_doc("Notification", "Loan Sanction", method="send", doc=doc)

        mobile = frappe.db.get_value("Loan Customer", {"name": self.customer}, "phone")
        mess = _(
            "Dear "
            + doc.full_name
            + ", \nCongratulations! Your loan account is active now! \nCurrent available limit - "
            + str(loan.drawing_power)
            + "."
        )
        frappe.enqueue(method=send_sms, receiver_list=[mobile], msg=mess)

        return loan

    def update_existing_loan(self):
        loan = frappe.get_doc("Loan", self.loan)

        for item in self.items:
            loan.append(
                "items",
                {
                    "isin": item.isin,
                    "security_name": item.security_name,
                    "security_category": item.security_category,
                    "pledged_quantity": item.pledged_quantity,
                    "price": item.price,
                    "amount": item.amount,
                    "psn": item.psn,
                    "error_code": item.error_code,
                },
            )

        loan.total_collateral_value += self.total_collateral_value
        loan.drawing_power = (loan.allowable_ltv / 100) * loan.total_collateral_value
        if loan.drawing_power > loan.sanctioned_limit:
            loan.drawing_power = loan.sanctioned_limit

        loan.save(ignore_permissions=True)

        # self.update_collateral_ledger(loan.name)
        self.update_collateral_ledger(
            {"loan": loan.name}, "loan_application = '{}'".format(self.name)
        )

        if self.loan_margin_shortfall:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            loan_margin_shortfall.fill_items()
            # if not loan_margin_shortfall.margin_shortfall_action:
            if loan_margin_shortfall.shortfall_percentage == 0:
                loan_margin_shortfall.status = "Pledged Securities"
                loan_margin_shortfall.action_time = datetime.now()
            loan_margin_shortfall.save(ignore_permissions=True)

        return loan

    # def update_collateral_ledger(self, loan_name):
    #     frappe.db.sql(
    #         """
    # 		update `tabCollateral Ledger`
    # 		set loan = '{}'
    # 		where loan_application = '{}';
    # 	""".format(
    #             loan_name, self.name
    #         )
    #     )
    def update_collateral_ledger(self, set_values={}, where=""):
        set_values_str = ""
        last_col = sorted(set_values.keys())[-1]
        print(last_col)
        if len(set_values.keys()) == len(set_values.values()):
            for col, val in set_values.items():
                set_values_str += "{} = '{}'".format(col, val)
                if len(set_values.keys()) > 0 and col != last_col:
                    set_values_str += ", "

        sql = """update `tabCollateral Ledger` set {} """.format(set_values_str)

        if len(where) > 0:
            sql += " where {}".format(where)

        frappe.db.sql(sql, debug=True)

    # TODO : hit pledge request as per batch items
    def pledge_request(self, security_list):
        las_settings = frappe.get_single("LAS Settings")
        API_URL = "{}{}".format(las_settings.cdsl_host, las_settings.pledge_setup_uri)

        prf_number = lms.random_token(length=12)
        securities_array = []
        for i in self.items:
            if i.isin in security_list:
                # set prf_number to LA item
                i.prf_number = prf_number
                j = {
                    "ISIN": i.isin,
                    "Quantity": str(float(i.pledged_quantity)),
                    "Value": str(float(i.price)),
                }
                securities_array.append(j)
        self.save(ignore_permissions=True)

        payload = {
            "PledgorBOID": self.pledgor_boid,
            "PledgeeBOID": self.pledgee_boid,
            "PRFNumber": prf_number,
            # "ExpiryDate": self.expiry.strftime("%d%m%Y"),
            "ExpiryDate": self.expiry_date.strftime("%d%m%Y"),
            "ISINDTLS": securities_array,
        }

        headers = las_settings.cdsl_headers()

        return {"url": API_URL, "headers": headers, "payload": payload}

    # dummy pledge response for pledge
    def dummy_pledge_response(self, security_list):
        import random

        ISINstatusDtls = []
        flag = 0
        for item in security_list:
            flag = bool(random.getrandbits(1))
            error_code = ["CIF3065-F", "PLD0152-E", "PLD0125-F"]
            ISINstatusDtls_item = {
                "ISIN": item.get("ISIN"),
                "PSN": "" if flag else lms.random_token(7, is_numeric=True),
                "ErrorCode": random.choice(error_code) if flag else "",
            }
            ISINstatusDtls.append(ISINstatusDtls_item)
        return {
            "Success": True,
            "PledgeSetupResponse": {"ISINstatusDtls": ISINstatusDtls},
        }

    # TODO : handle pledge response(process loan application items)
    def process(self, security_list, pledge_response):
        isin_details_ = pledge_response.get("PledgeSetupResponse").get("ISINstatusDtls")
        isin_details = {}
        for i in isin_details_:
            isin_details[i.get("ISIN")] = i

        # self.approved_total_collateral_value = 0
        total_collateral_value = 0
        total_successful_pledge = 0

        for i in self.items:
            if i.get("isin") in security_list:
                cur = isin_details.get(i.get("isin"))

                i.psn = cur.get("PSN")
                i.error_code = cur.get("ErrorCode")
                i.pledge_executed = 1

                success = len(i.psn) > 0

                if success:
                    # TODO : manage individual LA item pledge status
                    i.pledge_status = "Success"
                    # if self.status == "Not Processed":
                    #     self.status = "Success"
                    # elif self.status == "Failure":
                    #     self.status = "Partial Success"
                    # self.approved_total_collateral_value += i.amount
                    total_collateral_value += i.amount
                    total_successful_pledge += 1
                else:
                    i.pledge_status = "Failure"
                    i.lender_approval_status = "Pledge Failure"
                #     if self.status == "Not Processed":
                #         self.status = "Failure"
                #     elif self.status == "Success":
                #         self.status = "Partial Success"

        self.total_collateral_value += total_collateral_value
        self.save(ignore_permissions=True)
        # if total_successful_pledge == 0:
        #     self.is_processed = 1
        #     self.save(ignore_permissions=True)
        #     raise PledgeSetupFailureException(
        #         "Pledge Setup failed.", errors=pledge_response
        #     )

        # self.approved_total_collateral_value = round(
        #     self.approved_total_collateral_value, 2
        # )
        # self.approved_eligible_loan = round(
        #     lms.round_down_amount_to_nearest_thousand(
        #         (self.allowable_ltv / 100) * self.approved_total_collateral_value
        #     ),
        #     2,
        # )
        # self.is_processed = 1
        return total_successful_pledge

    def save_collateral_ledger(self, loan_application_name=None):
        for i in self.items:
            # print(i.isin,"in collateral")
            collateral_ledger = frappe.get_doc(
                {
                    "doctype": "Collateral Ledger",
                    "customer": self.customer,
                    "lender": self.lender,
                    "loan_application": self.name,
                    "request_type": "Pledge",
                    "request_identifier": i.prf_number,
                    "expiry": self.expiry_date,
                    "pledgor_boid": self.pledgor_boid,
                    "pledgee_boid": self.pledgee_boid,
                    "isin": i.isin,
                    "quantity": i.pledged_quantity,
                    "psn": i.psn,
                    "error_code": i.error_code,
                    "is_success": len(i.psn) > 0,
                    "lender_approval_status": "Pledge Failure"
                    if len(i.error_code) > 0
                    else "",
                }
            )
            collateral_ledger.save(ignore_permissions=True)
        # print("coll save done")

    def check_for_pledge(self):
        # check if pledge is already in progress
        is_pledge_executing = frappe.get_all(
            "Loan Application",
            fields=["count(name) as count", "status"],
            filters={"status": "Executing pledge"},
            debug=True,
        )
        # print(is_pledge_executing,"is_pledge_executing")

        if is_pledge_executing[0].count == 0:
            # TODO : Workers assigned for this cron can be set in las and we can apply (fetch records)limit as per no. of workers assigned
            loan_application = frappe.get_all(
                "Loan Application",
                fields="name, creation",
                filters={"status": "Waiting to be pledged"},
                order_by="creation desc",
                start=0,
                page_length=1,
                debug=True,
            )
            # print(loan_application, "loan_application")

            if loan_application:
                loan_application_doc = frappe.get_doc(
                    "Loan Application", loan_application[0].name
                )
                frappe.db.begin()
                loan_application_doc.status = "Executing pledge"
                loan_application_doc.workflow_state = "Executing pledge"
                loan_application_doc.total_collateral_value = 0
                loan_application_doc.save(ignore_permissions=True)
                frappe.db.commit()

                customer = loan_application_doc.get_customer()
                # print(customer, "customer LA")
                count_la_items = frappe.db.count(
                    "Loan Application Item", {"parent": loan_application[0].name}
                )
                no_of_batches = 1
                if count_la_items > 10:
                    import math

                    no_of_batches = math.ceil(count_la_items / 10)
                # print(count_la_items, "count_la_items", no_of_batches, "no_of_batches")

                # loop as per no of batches
                start = 0
                page_length = 10
                total_successful_pledge = 0
                for b_no in range(no_of_batches):
                    frappe.db.begin()

                    # fetch loan application items
                    if b_no > 0:
                        start += page_length
                    # print(start, "start", page_length, "page_length")

                    la_items = frappe.get_all(
                        "Loan Application Item",
                        fields="*",
                        filters={"parent": loan_application[0].name},
                        start=start,
                        page_length=page_length,
                        debug=True,
                    )
                    la_items_list = [item.isin for item in la_items]
                    # print(la_items, "la_items")

                    # TODO : generate prf number and assign to items in batch
                    # print(la_items_list, "la_items_list")
                    pledge_request = loan_application_doc.pledge_request(la_items_list)
                    # print(pledge_request, "pledge_request")

                    # TODO : pledge request hit for all batches
                    # try:
                    #     res = requests.post(
                    #         pledge_request.get("url"),
                    #         headers=pledge_request.get("headers"),
                    #         json=pledge_request.get("payload"),
                    #     )
                    #     data = res.json()

                    #     # Pledge LOG
                    #     log = {
                    #         "url": pledge_request.get("url"),
                    #         "headers": pledge_request.get("headers"),
                    #         "request": pledge_request.get("payload"),
                    #         "response": data,
                    #     }

                    #     import json
                    #     import os

                    #     pledge_log_file = frappe.utils.get_files_path("pledge_log.json")
                    #     pledge_log = None
                    #     if os.path.exists(pledge_log_file):
                    #         with open(pledge_log_file, "r") as f:
                    #             pledge_log = f.read()
                    #         f.close()
                    #     pledge_log = json.loads(pledge_log or "[]")
                    #     pledge_log.append(log)
                    #     with open(pledge_log_file, "w") as f:
                    #         f.write(json.dumps(pledge_log))
                    #     f.close()
                    #     # Pledge LOG end

                    #     # if not res.ok or not data.get("Success"):
                    #         # cart.reload()
                    #         # cart.status = "Failure"
                    #         # cart.is_processed = 1
                    #         # cart.save(ignore_permissions=True)
                    #         # raise PledgeSetupFailureException(errors=res.text)
                    # except requests.RequestException as e:
                    #     raise utils.APIException(str(e))

                    data = loan_application_doc.dummy_pledge_response(
                        pledge_request.get("payload").get("ISINDTLS")
                    )
                    print(data, "dummy_pledge_response")
                    # TODO : process loan application items in batches
                    total_successful_pledge_count = loan_application_doc.process(
                        la_items_list, data
                    )
                    frappe.db.commit()
                    total_successful_pledge += total_successful_pledge_count

                frappe.db.begin()
                if not customer.pledge_securities:
                    customer.pledge_securities = 1
                    customer.save(ignore_permissions=True)

                # TODO : process loan application(handle collateral and eligible amount)
                # loan_application_doc.reload()
                loan_application_doc.total_collateral_value = round(
                    loan_application_doc.total_collateral_value, 2
                )
                loan_application_doc.drawing_power = round(
                    lms.round_down_amount_to_nearest_thousand(
                        (loan_application_doc.allowable_ltv / 100)
                        * loan_application_doc.total_collateral_value
                    ),
                    2,
                )

                # TODO : once done with all batches, mark LA as Pledge executed
                loan_application_doc.status = "Pledge executed"
                loan_application_doc.workflow_state = "Pledge executed"
                # TODO : In case of all failure mark status as "Rejected"

                # manage loan application doc pledge status
                if total_successful_pledge == len(loan_application_doc.items):
                    loan_application_doc.pledge_status = "Success"
                elif total_successful_pledge == 0:
                    loan_application_doc.pledge_status = "Failure"
                else:
                    loan_application_doc.pledge_status = "Partial Success"

                loan_application_doc.save(ignore_permissions=True)
                loan_application_doc.save_collateral_ledger()
                frappe.db.commit()

                # TODO : Approved/Rejected LA items by lender
                # TODO : esign by customer
                # TODO : esign by lender
                # TODO : Approved/Rejected LA by lender
                # TODO : if Approved - created loan - notify customer
                # TODO : if Rejected - notify customer
        else:
            return "pledge in progress"


def only_pdf_upload(doc, method):
    if doc.attached_to_doctype == "Loan Application":
        if doc.file_name.split(".")[-1].lower() != "pdf":
            frappe.throw("Kindly upload PDF files only.")
