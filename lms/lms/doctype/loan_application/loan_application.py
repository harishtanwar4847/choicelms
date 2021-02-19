# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
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
from lms.firebase import FirebaseAdmin


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
                if i.lender_approval_status == "Approved":
                    approved_isin_list.append(i.isin)
                elif i.lender_approval_status == "Rejected":
                    rejected_isin_list.append(i.isin)

            if len(approved_isin_list) > 0:
                self.update_collateral_ledger(
                    {"lender_approval_status": "Approved"},
                    "loan_application = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(approved_isin_list)
                    ),
                )

            if len(rejected_isin_list) > 0:
                self.update_collateral_ledger(
                    {"lender_approval_status": "Rejected"},
                    "loan_application = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(rejected_isin_list)
                    ),
                )

            try:
                fa = FirebaseAdmin()
                fa.send_data(
                    data={
                        "event": "Esign Pending",
                    },
                    tokens=lms.get_firebase_tokens(self.user),
                )
            except Exception:
                pass
            finally:
                fa.delete_app()

        # self.notify_customer()

    def before_save(self):
        if (
            self.status == "Approved"
            and not self.lender_esigned_document
            and not self.loan_margin_shortfall
        ):
            frappe.throw("Please upload Lender Esigned Document")

        elif self.status == "Pledge accepted by Lender":
            if self.pledge_status == "Failure":
                frappe.throw("Sorry! Pledge for this Loan Application is failed.")

            total_approved = 0
            total_collateral_value = 0

            for i in self.items:
                if len(i.error_code) > 0 and i.lender_approval_status in [
                    "Approved",
                    "Rejected",
                ]:
                    frappe.throw(
                        "Pledge failed for ISIN - {}, can't Approve or Reject".format(
                            i.isin
                        )
                    )

                elif len(i.psn) > 0:
                    if i.lender_approval_status == "Pledge Failure":
                        frappe.throw(
                            "Already pledge success for {}, not allowed to set Pledge Failure.".format(
                                i.isin
                            )
                        )

                    elif i.lender_approval_status == "":
                        frappe.throw("Please Approve/Reject {}".format(i.isin))

                    if i.lender_approval_status == "Approved":
                        total_approved += 1
                        total_collateral_value += i.amount

            if total_approved == 0:
                frappe.throw(
                    "Please Approve atleast one item or Reject the Loan Application"
                )

            # TODO : manage loan application and its item's as per lender approval
            self.total_collateral_value = round(total_collateral_value, 2)
            self.drawing_power = round(
                lms.round_down_amount_to_nearest_thousand(
                    (self.allowable_ltv / 100) * self.total_collateral_value
                ),
                2,
            )

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
            if item.lender_approval_status == "Approved":
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
            {"loan": loan.name},
            "loan_application = '{}' and isin in {}".format(
                self.name,
                lms.convert_list_to_tuple_string([i.isin for i in loan.items]),
            ),
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
            {"loan": loan.name},
            "loan_application = '{}' and isin in {}".format(
                self.name,
                lms.convert_list_to_tuple_string([i.isin for i in loan.items]),
            ),
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
        # print(last_col)
        if len(set_values.keys()) == len(set_values.values()):
            for col, val in set_values.items():
                set_values_str += "{} = '{}'".format(col, val)
                if len(set_values.keys()) > 0 and col != last_col:
                    set_values_str += ", "

        sql = """update `tabCollateral Ledger` set {} """.format(set_values_str)

        if len(where) > 0:
            sql += " where {}".format(where)

        frappe.db.sql(sql)

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

        # error_flag = 1
        error_flag = bool(random.getrandbits(1))
        if error_flag:
            return {
                "Success": False,
                "PledgeSetupResponse": {
                    "ErrorId": "ERR007",
                    "ErrorMessage": "Invalid Pledgor BOID.",
                },
            }
        else:
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

        total_successful_pledge = 0
        if isin_details_:
            isin_details = {}
            for i in isin_details_:
                isin_details[i.get("ISIN")] = i

            # self.approved_total_collateral_value = 0
            total_collateral_value = 0

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
                    #      if self.status == "Not Processed":
                    #         self.status = "Failure"
                    #     elif self.status == "Success":
                    #         self.status = "Partial Success"

            self.total_collateral_value += total_collateral_value
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
        else:
            ErrorId = pledge_response.get("PledgeSetupResponse").get("ErrorId")
            for i in self.items:
                if i.get("isin") in security_list:
                    i.error_code = ErrorId
                    i.pledge_executed = 1
                    i.pledge_status = "Failure"
                    i.lender_approval_status = "Pledge Failure"

        self.save(ignore_permissions=True)
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
                    "is_success": 1 if i.get("psn") and len(i.get("psn")) > 0 else 0,
                    "lender_approval_status": "Pledge Failure"
                    if i.get("error_code") and len(i.get("error_code")) > 0
                    else "",
                }
            )
            collateral_ledger.save(ignore_permissions=True)
        # print("coll save done")

    def notify_customer(self):
        customer = self.get_customer()
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        doc = frappe.get_doc("User", customer.user).as_dict()
        doc["loan_application"] = {
            "status": self.status,
            "pledge_status": self.pledge_status,
            "current_total_collateral_value": self.total_collateral_value_str,
            "requested_total_collateral_value": self.pledged_total_collateral_value_str,
            "drawing_power": self.drawing_power_str,
        }
        frappe.enqueue_doc("Notification", "Loan Application", method="send", doc=doc)

        if doc.get("loan_application").get("pledge_status") == "Failure":
            mess = "Sorry! Your loan application was turned down since the pledge was not successful. We regret the inconvenience caused."

        if doc.get("loan_application").get("status") == "Pledge accepted by Lender":
            mess = "Congratulations! Your application is being considered favourably by our lending partner\nand finally accepted at Rs. {current_total_collateral_value} against the request value of Rs. {requested_total_collateral_value}.\nAccordingly the final Drawing power is Rs. {drawing_power}. Please e-sign the loan agreement to avail the loan now.".format(
                current_total_collateral_value=doc.get("loan_application").get(
                    "current_total_collateral_value"
                ),
                requested_total_collateral_value=doc.get("loan_application").get(
                    "requested_total_collateral_value"
                ),
                drawing_power=doc.get("loan_application").get("drawing_power"),
            )

        if doc.get("loan_application").get("status") == "Approved":
            mess = "Congratulations! Your loan application is Approved."
        if doc.get("loan_application").get("status") == "Rejected":
            mess = "Sorry! Your loan application was turned down. We regret the inconvenience caused."

        receiver_list = list(set([str(customer.phone), str(user_kyc.mobile_number)]))
        from frappe.core.doctype.sms_settings.sms_settings import send_sms

        frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=mess)


def check_for_pledge(loan_application_doc):
    # frappe.logger().info("process_pledge Call")
    frappe.logger().info(
        "in check_for_pldege call enqueue START---- "
        + datetime.now().strftime("%I:%M:%S:%f %p")
    )

    # TODO : Workers assigned for this cron can be set in las and we can apply (fetch records)limit as per no. of workers assigned
    frappe.db.begin()
    loan_application_doc.status = "Executing pledge"
    loan_application_doc.workflow_state = "Executing pledge"
    loan_application_doc.total_collateral_value = 0
    loan_application_doc.save(ignore_permissions=True)
    frappe.db.commit()

    customer = loan_application_doc.get_customer()
    # print(customer, "customer LA")
    count_la_items = frappe.db.count(
        "Loan Application Item", {"parent": loan_application_doc.name}
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
            filters={"parent": loan_application_doc.name},
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
        try:
            res = requests.post(
                pledge_request.get("url"),
                headers=pledge_request.get("headers"),
                json=pledge_request.get("payload"),
            )
            data = res.json()

            # Pledge LOG
            log = {
                "url": pledge_request.get("url"),
                "headers": pledge_request.get("headers"),
                "request": pledge_request.get("payload"),
                "response": data,
            }

            import json
            import os

            pledge_log_file = frappe.utils.get_files_path("pledge_log.json")
            pledge_log = None
            if os.path.exists(pledge_log_file):
                with open(pledge_log_file, "r") as f:
                    pledge_log = f.read()
                f.close()
            pledge_log = json.loads(pledge_log or "[]")
            pledge_log.append(log)
            with open(pledge_log_file, "w") as f:
                f.write(json.dumps(pledge_log))
            f.close()
            # Pledge LOG end

        except requests.RequestException as e:
            frappe.logger().info(str(e))
            frappe.logger().info("request exception catched")

        # data = loan_application_doc.dummy_pledge_response(
        #     pledge_request.get("payload").get("ISINDTLS")
        # )
        # frappe.logger().info("{} dummy_pledge_response".format(data))

        # if not res.ok or not data.get("Success"):
        # if data.get("Success"):
        frappe.logger().info("batch pledge sucess")
        # TODO : process loan application items in batches
        total_successful_pledge_count = loan_application_doc.process(
            la_items_list, data
        )
        total_successful_pledge += total_successful_pledge_count

        frappe.db.commit()

    frappe.db.begin()
    frappe.logger().info("{} total_successful_pledge".format(total_successful_pledge))
    # manage loan application doc pledge status
    loan_application_doc.status = "Pledge executed"
    if total_successful_pledge == len(loan_application_doc.items):
        loan_application_doc.pledge_status = "Success"
    elif total_successful_pledge == 0:
        loan_application_doc.reload()
        loan_application_doc.status = "Pledge Failure"
        loan_application_doc.pledge_status = "Failure"
        # loan_application_doc.workflow_state = "Pledge executed"
        # loan_application_doc.save(ignore_permissions=True)
    else:
        loan_application_doc.pledge_status = "Partial Success"

    # TODO : once done with all batches, mark LA as Pledge executed
    loan_application_doc.workflow_state = "Pledge executed"

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

    loan_application_doc.save(ignore_permissions=True)
    loan_application_doc.save_collateral_ledger()

    if not customer.pledge_securities:
        customer.pledge_securities = 1
        customer.save(ignore_permissions=True)

    frappe.db.commit()

    frappe.logger().info(
        "in check_for_pldege call enqueue done- "
        + datetime.now().strftime("%I:%M:%S:%f %p")
    )
    frappe.logger().info(
        "in check_for_pldege call - process pledge by enqueue - "
        + datetime.now().strftime("%I:%M:%S:%f %p")
    )
    frappe.enqueue(
        method="lms.lms.doctype.loan_application.loan_application.process_pledge"
    )
    # TODO : Approved/Rejected LA items by lender
    # TODO : esign by customer
    # TODO : esign by lender
    # TODO : Approved/Rejected LA by lender
    # TODO : if Approved - created loan - notify customer
    # TODO : if Rejected - notify customer


@frappe.whitelist()
def process_pledge(loan_application_name=""):
    # print(loan_application_name)
    frappe.logger().info(loan_application_name)
    # current_hour = datetime.now().hour
    from frappe import utils

    current_hour = int(utils.nowtime().split(":")[0])

    frappe.logger().info(current_hour)
    las_settings = frappe.get_single("LAS Settings")
    frappe.logger().info(las_settings.scheduler_from_time)
    frappe.logger().info(las_settings.scheduler_to_time)

    if (
        las_settings.scheduler_from_time
        <= current_hour
        < las_settings.scheduler_to_time
    ):
        frappe.logger().info("call enqueue for pledge")

        # check if pledge is already in progress
        is_pledge_executing = frappe.get_all(
            "Loan Application",
            fields=["count(name) as count", "status"],
            filters={"status": "Executing pledge"},
            debug=True,
        )
        frappe.logger().info(
            "{} is_pledge_executing cnt".format(is_pledge_executing[0].count)
        )

        if is_pledge_executing[0].count == 0:
            frappe.logger().info("is_pledge_executing")

            filters_query = {"status": "Waiting to be pledged"}
            if loan_application_name:
                filters_query["name"] = loan_application_name
            frappe.logger().info(filters_query)

            loan_application = frappe.get_all(
                "Loan Application",
                fields="name, creation",
                filters=filters_query,
                order_by="creation asc",
                start=0,
                page_length=1,
                debug=True,
            )
            frappe.logger().info(loan_application)

            if loan_application:
                loan_application_doc = frappe.get_doc(
                    "Loan Application", loan_application[0].name
                )
                frappe.logger().info(loan_application_doc)
                frappe.enqueue(
                    method="lms.lms.doctype.loan_application.loan_application.check_for_pledge",
                    timeout=7200,
                    job_name="loan_application_pledge",
                    loan_application_doc=loan_application_doc,
                )
        else:
            frappe.logger().info("pledge failed")
    else:
        frappe.logger().info("call enqueue for pledge - failed")


def only_pdf_upload(doc, method):
    if doc.attached_to_doctype == "Loan Application":
        if doc.file_name.split(".")[-1].lower() != "pdf":
            frappe.throw("Kindly upload PDF files only.")
