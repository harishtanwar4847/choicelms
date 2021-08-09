# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json
from datetime import datetime, timedelta

import frappe
import requests
import utils
from frappe import _
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.model.document import Document
from num2words import num2words

import lms
from lms.exceptions import PledgeSetupFailureException
from lms.firebase import FirebaseAdmin
from lms.lms.doctype.collateral_ledger.collateral_ledger import CollateralLedger


class LoanApplication(Document):
    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def esign_request(self, increase_loan):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()
        if self.loan:
            loan = self.get_loan()

        doc = {
            "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
            "loan_application_number": self.name,
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            "sanctioned_amount": lms.round_down_amount_to_nearest_thousand(
                (self.total_collateral_value + loan.total_collateral_value)
                * self.allowable_ltv
                / 100
            )
            if self.loan and not self.loan_margin_shortfall
            else self.drawing_power,
            "sanctioned_amount_in_words": num2words(
                lms.round_down_amount_to_nearest_thousand(
                    (self.total_collateral_value + loan.total_collateral_value)
                    * self.allowable_ltv
                    / 100
                )
                if self.loan and not self.loan_margin_shortfall
                else self.drawing_power,
                lang="en_IN",
            ).title(),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "rebait_threshold": lender.rebait_threshold,
            "account_renewal_charges": lender.account_renewal_charges,
            "documentation_charges": int(lender.lender_documentation_minimum_amount),
            "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
            "processing_fee": lender.lender_processing_fees,
            "transaction_charges_per_request": int(
                lender.transaction_charges_per_request
            ),
            "security_selling_share": lender.security_selling_share,
            "cic_charges": int(lender.cic_charges),
            "total_pages": lender.total_pages,
        }

        if increase_loan:
            doc["old_sanctioned_amount"] = loan.sanctioned_limit
            doc["old_sanctioned_amount_in_words"] = num2words(
                loan.sanctioned_limit, lang="en_IN"
            ).title()
            agreement_template = lender.get_loan_enhancement_agreement_template()
            loan_agreement_file = "loan-enhancement-aggrement.pdf"
            coordinates = lender.enhancement_coordinates.split(",")
            esign_page = lender.enhancement_esign_page
        else:
            agreement_template = lender.get_loan_agreement_template()
            loan_agreement_file = "loan-aggrement.pdf"
            coordinates = lender.coordinates.split(",")
            esign_page = lender.esign_page

        agreement = frappe.render_template(
            agreement_template.get_content(), {"doc": doc}
        )

        from frappe.utils.pdf import get_pdf

        agreement_pdf = get_pdf(agreement)

        las_settings = frappe.get_single("LAS Settings")
        headers = {"userId": las_settings.choice_user_id}
        files = {"file": (loan_agreement_file, agreement_pdf)}

        return {
            "file_upload_url": "{}{}".format(
                las_settings.esign_host, las_settings.esign_upload_file_uri
            ),
            "headers": headers,
            "files": files,
            "esign_url_dict": {
                "x": coordinates[0],
                "y": coordinates[1],
                "page_number": esign_page,
            },
            "esign_url": "{}{}".format(
                las_settings.esign_host, las_settings.esign_request_uri
            ),
        }

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
                if i.get("pledge_status") == "Failure" and i.lender_approval_status in [
                    "Approved",
                    "Rejected",
                ]:
                    frappe.throw(
                        "Pledge failed for ISIN - {}, can't Approve or Reject".format(
                            i.isin
                        )
                    )

                elif i.get("pledge_status") == "Success":
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

        if self.status == "Pledge executed":
            total_collateral_value = 0
            for i in self.items:
                if i.pledge_status == "Success" or i.pledge_status == "":
                    if (
                        i.lender_approval_status == "Approved"
                        or i.lender_approval_status == ""
                    ):
                        total_collateral_value += i.amount
                        self.total_collateral_value = round(total_collateral_value, 2)
                        self.drawing_power = round(
                            lms.round_down_amount_to_nearest_thousand(
                                (self.allowable_ltv / 100) * self.total_collateral_value
                            ),
                            2,
                        )
                    # elif (
                    #     i.lender_approval_status == "Rejected"
                    #     or i.lender_approval_status == "Pledge Failure"
                    # ):
                    #     if (
                    #         total_collateral_value > 0
                    #         and total_collateral_value >= i.amount
                    #     ):
                    #         total_collateral_value -= i.amount
                    #     self.total_collateral_value = round(total_collateral_value, 2)
                    #     self.drawing_power = round(
                    #         lms.round_down_amount_to_nearest_thousand(
                    #             (self.allowable_ltv / 100) * self.total_collateral_value
                    #         ),
                    #         2,
                    #     )

        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.drawing_power_str = lms.amount_formatter(self.drawing_power)
        self.pledged_total_collateral_value_str = lms.amount_formatter(
            self.pledged_total_collateral_value
        )

    def on_update(self):
        if self.status == "Approved":
            if not self.loan:
                loan = self.create_loan()
            else:
                loan = self.update_existing_loan()

            frappe.db.commit()

            if not self.loan:
                # new loan agreement mapping
                self.map_loan_agreement_file(loan)
            elif (
                self.loan
                and self.lender_esigned_document
                and not self.loan_margin_shortfall
            ):
                # increase loan agreement mapping
                self.map_loan_agreement_file(loan, increase_loan=True)

            if self.loan_margin_shortfall:
                # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
                under_process_la = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": self.loan,
                        "status": [
                            "not IN",
                            ["Approved", "Rejected", "Pledge Failure"],
                        ],
                        "pledge_status": ["!=", "Failure"],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_loan_transaction = frappe.get_all(
                    "Loan Transaction",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_sell_collateral_application = frappe.get_all(
                    "Sell Collateral Application",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                if (
                    (
                        not pending_loan_transaction
                        and not pending_sell_collateral_application
                        and not under_process_la
                    )
                    and loan_margin_shortfall.status == "Request Pending"
                    and loan_margin_shortfall.shortfall_percentage > 0
                ):
                    loan_margin_shortfall.status = "Pending"
                    loan_margin_shortfall.save(ignore_permissions=True)
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
                    "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(approved_isin_list)
                    ),
                )

            if len(rejected_isin_list) > 0:
                self.update_collateral_ledger(
                    {"lender_approval_status": "Rejected"},
                    "application_doctype = 'Loan Application' and application_name = '{}' and isin IN {}".format(
                        self.name, lms.convert_list_to_tuple_string(rejected_isin_list)
                    ),
                )
            try:
                fa = FirebaseAdmin()
                fa.send_data(
                    data={
                        "event": "Esign Pending",
                    },
                    tokens=lms.get_firebase_tokens(self.get_customer().user),
                )
            except Exception:
                pass
            finally:
                fa.delete_app()

        elif self.status == "Rejected":
            if self.loan_margin_shortfall:
                # if shortfall is not recoverd then margin shortfall status will change from request pending to pending
                loan_margin_shortfall = frappe.get_doc(
                    "Loan Margin Shortfall", self.loan_margin_shortfall
                )
                under_process_la = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": self.loan,
                        "status": [
                            "not IN",
                            ["Approved", "Rejected", "Pledge Failure"],
                        ],
                        "pledge_status": ["!=", "Failure"],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_loan_transaction = frappe.get_all(
                    "Loan Transaction",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                pending_sell_collateral_application = frappe.get_all(
                    "Sell Collateral Application",
                    filters={
                        "loan": self.loan,
                        "status": ["not IN", ["Approved", "Rejected"]],
                        "loan_margin_shortfall": loan_margin_shortfall.name,
                    },
                )
                if (
                    (
                        not pending_loan_transaction
                        and not pending_sell_collateral_application
                        and not under_process_la
                    )
                    and loan_margin_shortfall.status == "Request Pending"
                    and loan_margin_shortfall.shortfall_percentage > 0
                ):
                    loan_margin_shortfall.status = "Pending"
                    loan_margin_shortfall.save(ignore_permissions=True)
                    frappe.db.commit()

            if not self.loan and not self.loan_margin_shortfall:
                customer = self.get_customer()
                if customer.pledge_securities:
                    customer.pledge_securities = 0
                    customer.save(ignore_permissions=True)
                    frappe.db.commit()

        self.notify_customer()

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
        # self.map_loan_agreement_file(loan)

        # File code here #S

        customer = frappe.get_doc("Loan Customer", self.customer)
        if not customer.loan_open:
            customer.loan_open = 1
            customer.save(ignore_permissions=True)

        self.update_collateral_ledger(
            {"loan": loan.name},
            "application_doctype = 'Loan Application' and application_name = '{}'".format(
                self.name,
            ),
        )

        loan.reload()
        loan.update_items()
        loan.fill_items()
        loan.save(ignore_permissions=True)

        # customer = frappe.db.get_value("Loan Customer", {"name": self.customer}, "user")
        """changes as per latest email notification list-sent by vinayak - email verification final 2.0"""
        # doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc)
        # frappe.enqueue_doc("Notification", "Loan Sanction", method="send", doc=doc)

        # mobile = frappe.db.get_value("Loan Customer", {"name": self.customer}, "phone")
        # mess = _(
        #     "Dear "
        #     + doc.investor_name
        #     + ", Congratulations! Your loan account is active now! Current available limit - "
        #     + str(loan.drawing_power)
        #     + "."
        # )
        # mess = _(
        #     "Congratulations! Your loan account is active now! Current available limit - "
        #     + str(loan.drawing_power)
        #     + "."
        # )
        # frappe.enqueue(method=send_sms, receiver_list=[doc.mobile_number], msg=mess)

        return loan

    def map_loan_agreement_file(self, loan, increase_loan=False):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.lender_esigned_document}
        )

        loan_agreement = frappe.get_doc("File", file_name)

        event = "New loan"
        if increase_loan:
            loan_agreement_file_name = "{}-loan-enhancement-aggrement.pdf".format(
                loan.name
            )
            event = "Increase loan"
        else:
            loan_agreement_file_name = "{}-loan-aggrement.pdf".format(loan.name)

        is_private = 0
        loan_agreement_file_url = frappe.utils.get_files_path(
            loan_agreement_file_name, is_private=is_private
        )

        frappe.db.begin()
        loan_agreement_file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": loan_agreement_file_name,
                "content": loan_agreement.get_content(),
                "attached_to_doctype": "Loan",
                "attached_to_name": loan.name,
                "attached_to_field": "loan_agreement",
                "folder": "Home",
                # "file_url": loan_agreement_file_url,
                "is_private": is_private,
            }
        )
        loan_agreement_file.insert(ignore_permissions=True)
        frappe.db.commit()

        frappe.db.set_value(
            "Loan",
            loan.name,
            "loan_agreement",
            loan_agreement_file.file_url,
            update_modified=False,
        )
        # save loan sanction history
        loan.save_loan_sanction_history(loan_agreement_file.name, event)

    def update_existing_loan(self):
        self.update_collateral_ledger(
            {"loan": self.loan},
            "application_doctype = 'Loan Application' and application_name = '{}'".format(
                self.name
            ),
        )

        loan = frappe.get_doc("Loan", self.loan)

        # apply processing fees on new sanctioned limit(loan application drawing power)
        # apply renewal charges on existing loan sanctioned limit
        if not self.loan_margin_shortfall:
            self.apply_renewal_charges(loan)

        loan.reload()
        loan.update_items()
        loan.fill_items()
        # loan.check_for_shortfall()

        # for item in self.items:
        #     if item.lender_approval_status == "Approved":
        #         loan.append(
        #             "items",
        #             {
        #                 "isin": item.isin,
        #                 "security_name": item.security_name,
        #                 "security_category": item.security_category,
        #                 "pledged_quantity": item.pledged_quantity,
        #                 "price": item.price,
        #                 "amount": item.amount
        #             },
        #         )

        # loan.total_collateral_value += self.total_collateral_value
        loan.drawing_power = (loan.allowable_ltv / 100) * loan.total_collateral_value
        # loan.drawing_power += self.drawing_power

        if not self.loan_margin_shortfall:
            loan.drawing_power = round(
                lms.round_down_amount_to_nearest_thousand(loan.drawing_power), 2
            )
            loan.sanctioned_limit = loan.drawing_power
            # TODO : manage expiry date
            loan.expiry_date = self.expiry_date
            loan.save(ignore_permissions=True)

        if self.loan_margin_shortfall:
            if loan.drawing_power > loan.sanctioned_limit:
                loan.drawing_power = loan.sanctioned_limit

            loan.save(ignore_permissions=True)
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            loan_margin_shortfall.fill_items()
            # if not loan_margin_shortfall.margin_shortfall_action:
            if loan_margin_shortfall.shortfall_percentage == 0:
                loan_margin_shortfall.status = "Pledged Securities"
                loan_margin_shortfall.action_time = frappe.utils.now_datetime()
            loan_margin_shortfall.save(ignore_permissions=True)

        return loan

    def apply_renewal_charges(self, loan):
        lender = loan.get_lender()

        # renewal charges
        import calendar

        date = frappe.utils.now_datetime()
        days_in_year = 366 if calendar.isleap(date.year) else 365
        renewal_charges = lender.renewal_charges
        if lender.renewal_charge_type == "Percentage":
            la_expiry_date = (
                (datetime.strptime(self.expiry_date, "%Y-%m-%d")).date()
                if type(self.expiry_date) == str
                else self.expiry_date
            )
            loan_expiry_date = loan.expiry_date + timedelta(days=1)
            days_left_to_expiry = (la_expiry_date - loan_expiry_date).days + 1
            amount = (
                (renewal_charges / 100)
                * loan.sanctioned_limit
                / days_in_year
                * days_left_to_expiry
            )
            renewal_charges = loan.validate_loan_charges_amount(
                lender, amount, "renewal_minimum_amount", "renewal_maximum_amount"
            )

        if renewal_charges > 0:
            loan.create_loan_transaction(
                "Renewal Charges", renewal_charges, approve=True
            )

        # Processing fees
        processing_fees = lender.lender_processing_fees
        if lender.lender_processing_fees_type == "Percentage":
            days_left_to_expiry = days_in_year
            amount = (
                (processing_fees / 100)
                * self.drawing_power
                / days_in_year
                * days_left_to_expiry
            )
            processing_fees = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_processing_minimum_amount",
                "lender_processing_maximum_amount",
            )

        if processing_fees > 0:
            loan.create_loan_transaction(
                "Processing Fees",
                processing_fees,
                approve=True,
            )

        # Stamp Duty
        stamp_duty = lender.stamp_duty
        if lender.stamp_duty_type == "Percentage":
            amount = (stamp_duty / 100) * self.drawing_power
            stamp_duty = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_stamp_duty_minimum_amount",
                "lender_stamp_duty_maximum_amount",
            )

        if stamp_duty > 0:
            loan.create_loan_transaction(
                "Stamp Duty",
                stamp_duty,
                approve=True,
            )

        # Documentation Charges
        documentation_charges = lender.documentation_charges
        if lender.documentation_charge_type == "Percentage":
            amount = (documentation_charges / 100) * self.drawing_power
            documentation_charges = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_documentation_minimum_amount",
                "lender_documentation_maximum_amount",
            )

        if documentation_charges > 0:
            loan.create_loan_transaction(
                "Documentation Charges",
                documentation_charges,
                approve=True,
            )

        # Mortgage Charges
        mortgage_charges = lender.mortgage_charges
        if lender.mortgage_charge_type == "Percentage":
            amount = (mortgage_charges / 100) * self.drawing_power
            mortgage_charges = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_mortgage_minimum_amount",
                "lender_mortgage_maximum_amount",
            )

        if mortgage_charges > 0:
            loan.create_loan_transaction(
                "Mortgage Charges",
                mortgage_charges,
                approve=True,
            )

    def update_collateral_ledger(self, set_values={}, where=""):
        set_values_str = ""
        last_col = sorted(set_values.keys())[-1]
        if len(set_values.keys()) == len(set_values.values()):
            for col, val in set_values.items():
                set_values_str += "{} = '{}'".format(col, val)
                if len(set_values.keys()) > 0 and col != last_col:
                    set_values_str += ", "

        sql = """update `tabCollateral Ledger` set {} """.format(set_values_str)

        if len(where) > 0:
            sql += " where {}".format(where)

        frappe.db.sql(sql)

    # hit pledge request as per batch items
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
            "ExpiryDate": self.expiry_date.strftime("%d%m%Y"),
            "ISINDTLS": securities_array,
        }

        headers = las_settings.cdsl_headers()

        return {"url": API_URL, "headers": headers, "payload": payload}

    # dummy pledge response for pledge
    def dummy_pledge_response(self, security_list):
        import random

        error_flag = 0
        # error_flag = bool(random.getrandbits(1))
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
                # flag = bool(random.getrandbits(1))
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

    # handle pledge response(process loan application items)
    def process(self, security_list, pledge_response):
        isin_details_ = pledge_response.get("PledgeSetupResponse").get("ISINstatusDtls")

        total_successful_pledge = 0
        if isin_details_:
            isin_details = {}
            for i in isin_details_:
                isin_details[i.get("ISIN")] = i

            total_collateral_value = 0
            for i in self.items:
                if i.get("isin") in security_list:
                    cur = isin_details.get(i.get("isin"))

                    i.pledge_executed = 1

                    success = len(cur.get("PSN")) > 0

                    if success:
                        # TODO : manage individual LA item pledge status
                        i.pledge_status = "Success"
                        total_collateral_value += i.amount
                        total_successful_pledge += 1
                        collateral_ledger_data = {
                            "prf": i.get("prf_number"),
                            "expiry": self.expiry_date,
                            "pledgor_boid": self.pledgor_boid,
                            "pledgee_boid": self.pledgee_boid,
                        }
                        collateral_ledger_input = {
                            "doctype": "Loan Application",
                            "docname": self.name,
                            "request_type": "Pledge",
                            "isin": i.get("isin"),
                            "quantity": i.get("pledged_quantity"),
                            "data": collateral_ledger_data,
                            "psn": cur.get("PSN"),
                        }
                        CollateralLedger.create_entry(**collateral_ledger_input)
                    else:
                        i.pledge_status = "Failure"
                        i.lender_approval_status = "Pledge Failure"

            self.total_collateral_value += total_collateral_value
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

    def notify_customer(self):
        from frappe.core.doctype.sms_settings.sms_settings import send_sms

        doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
        doc["loan_application"] = {
            "status": self.status,
            "pledge_status": self.pledge_status,
            "current_total_collateral_value": self.total_collateral_value_str,
            "requested_total_collateral_value": self.pledged_total_collateral_value_str,
            "drawing_power": self.drawing_power_str,
        }
        doc["margin_shortfall"] = self.loan_margin_shortfall
        if self.status in [
            "Pledge Failure",
            "Pledge accepted by Lender",
            "Approved",
            "Rejected",
        ]:
            if self.loan and not self.loan_margin_shortfall:
                frappe.enqueue_doc(
                    "Notification", "Increase Loan Application", method="send", doc=doc
                )
            else:
                frappe.enqueue_doc(
                    "Notification", "Loan Application", method="send", doc=doc
                )

        msg = ""
        if doc.get("loan_application").get("status") == "Pledge Failure":
            msg = (
                "Dear Customer,\nSorry! Your Increase loan application was turned down since the pledge was not successful due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app -Spark Loans"
                if self.loan and not self.loan_margin_shortfall
                else "Dear Customer,\nSorry! Your loan application was turned down since the pledge was not successful due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"
            )

        elif (
            doc.get("loan_application").get("status") == "Pledge accepted by Lender"
            and not self.loan_margin_shortfall
        ):
            msg = (
                'Dear Customer,\nCongratulations! Your Increase loan application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans'
                if self.loan and not self.loan_margin_shortfall
                else 'Dear Customer,\nCongratulations! Your loan application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans'
            )

        elif (
            doc.get("loan_application").get("status") == "Approved"
            and not self.loan_margin_shortfall
        ):
            msg = (
                "Dear Customer,\nCongratulations! Your loan limit has been successfully increased. Kindly check the app. You may now withdraw funds as per your convenience. -Spark Loans"
                if self.loan and not self.loan_margin_shortfall
                else "Dear Customer,\nCongratulations! Your loan account is open. Kindly check the app. You may now withdraw funds as per your convenience. -Spark Loans"
            )

        elif (
            doc.get("loan_application").get("status") == "Rejected"
            and not self.loan_margin_shortfall
        ):
            msg = (
                "Dear Customer,\nSorry! Your Increase loan application was turned down due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"
                if self.loan and not self.loan_margin_shortfall
                else "Dear Customer,\nSorry! Your loan application was turned down due to technical reasons. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"
            )

        elif (
            doc.get("loan_application").get("status") == "Esign Done"
            and self.lender_esigned_document == None
            and not self.loan_margin_shortfall
        ):
            msg = "Dear Customer,\nYour E-sign process is completed. You shall soon receive a confirmation of loan approval. Thank you for your patience. - Spark Loans"

        if (
            (
                (self.pledge_status == "Partial Success")
                or (self.total_collateral_value < self.pledged_total_collateral_value)
            )
            and doc.get("loan_application").get("status") == "Pledge accepted by Lender"
            and not self.loan_margin_shortfall
        ):
            msg = "Dear Customer,\nCongratulations! Your pledge request was successfully considered and was partially accepted for Rs. {} due to technical reasons. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. -Spark Loans".format(
                self.total_collateral_value_str
            )

        if msg:
            receiver_list = list(
                set([str(self.get_customer().phone), str(doc.mobile_number)])
            )
            from frappe.core.doctype.sms_settings.sms_settings import send_sms

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

    def validate(self):
        for i, item in enumerate(
            sorted(self.items, key=lambda item: item.security_name), start=1
        ):
            item.idx = i


def check_for_pledge(loan_application_doc):
    # TODO : Workers assigned for this cron can be set in las and we can apply (fetch records)limit as per no. of workers assigned
    frappe.db.begin()
    loan_application_doc.status = "Executing pledge"
    loan_application_doc.workflow_state = "Executing pledge"
    loan_application_doc.total_collateral_value = 0
    loan_application_doc.save(ignore_permissions=True)
    frappe.db.commit()

    customer = loan_application_doc.get_customer()
    count_la_items = frappe.db.count(
        "Loan Application Item", {"parent": loan_application_doc.name}
    )
    no_of_batches = 1
    if count_la_items > 10:
        import math

        no_of_batches = math.ceil(count_la_items / 10)

    # loop as per no of batches
    start = 0
    page_length = 10
    total_successful_pledge = 0
    for b_no in range(no_of_batches):
        frappe.db.begin()
        # fetch loan application items
        if b_no > 0:
            start += page_length

        la_items = frappe.get_all(
            "Loan Application Item",
            fields="*",
            filters={"parent": loan_application_doc.name},
            start=start,
            page_length=page_length,
        )
        la_items_list = [item.isin for item in la_items]

        # TODO : generate prf number and assign to items in batch
        pledge_request = loan_application_doc.pledge_request(la_items_list)
        # TODO : pledge request hit for all batches
        debug_mode = frappe.db.get_single_value("LAS Settings", "debug_mode")
        if debug_mode:
            data = loan_application_doc.dummy_pledge_response(
                pledge_request.get("payload").get("ISINDTLS")
            )
        else:
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
                pass

        # TODO : process loan application items in batches
        total_successful_pledge_count = loan_application_doc.process(
            la_items_list, data
        )
        total_successful_pledge += total_successful_pledge_count
        frappe.db.commit()

    frappe.db.begin()
    # manage loan application doc pledge status
    loan_application_doc.status = "Pledge executed"
    pledge_securities = 0
    if total_successful_pledge == len(loan_application_doc.items):
        loan_application_doc.pledge_status = "Success"
        pledge_securities = 1
    elif total_successful_pledge == 0:
        loan_application_doc.reload()
        loan_application_doc.status = "Pledge Failure"
        loan_application_doc.pledge_status = "Failure"
    else:
        loan_application_doc.pledge_status = "Partial Success"
        pledge_securities = 1
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
    # loan_application_doc.save_collateral_ledger()

    if not customer.pledge_securities:
        # customer.pledge_securities = 1
        customer.pledge_securities = pledge_securities
        customer.save(ignore_permissions=True)

    frappe.db.commit()
    frappe.enqueue(
        method="lms.lms.doctype.loan_application.loan_application.process_pledge"
    )


@frappe.whitelist()
def process_pledge(loan_application_name=""):
    from frappe import utils

    current_hour = int(utils.nowtime().split(":")[0])
    las_settings = frappe.get_single("LAS Settings")

    if (
        las_settings.scheduler_from_time
        <= current_hour
        < las_settings.scheduler_to_time
    ):
        # check if pledge is already in progress
        is_pledge_executing = frappe.get_all(
            "Loan Application",
            fields=["count(name) as count", "status"],
            filters={"status": "Executing pledge"},
        )

        if is_pledge_executing[0].count == 0:
            filters_query = {"status": "Waiting to be pledged"}
            if loan_application_name:
                filters_query["name"] = loan_application_name

            loan_application = frappe.get_all(
                "Loan Application",
                fields="name, creation",
                filters=filters_query,
                order_by="creation asc",
                start=0,
                page_length=1,
            )

            if loan_application:
                loan_application_doc = frappe.get_doc(
                    "Loan Application", loan_application[0].name
                )
                frappe.enqueue(
                    method="lms.lms.doctype.loan_application.loan_application.check_for_pledge",
                    timeout=7200,
                    job_name="loan_application_pledge",
                    loan_application_doc=loan_application_doc,
                )


def only_pdf_upload(doc, method):
    if doc.attached_to_doctype == "Loan Application":
        if doc.file_name.split(".")[-1].lower() != "pdf":
            frappe.throw("Kindly upload PDF files only.")


@frappe.whitelist()
def actions_on_isin(loan_application):
    loan_application = json.loads(loan_application)
    loan_application_doc = frappe.get_doc("Loan Application", loan_application["name"])
    if loan_application_doc.status == "Pledge executed":
        total_collateral_value = 0
        drawing_power = 0
        for i in loan_application["items"]:
            if i["pledge_status"] == "Success" or i["pledge_status"] == "":
                if (
                    i["lender_approval_status"] == "Approved"
                    or i["lender_approval_status"] == ""
                ):
                    total_collateral_value += i["amount"]
                    total_collateral_value = round(total_collateral_value, 2)
                    drawing_power = round(
                        lms.round_down_amount_to_nearest_thousand(
                            (loan_application["allowable_ltv"] / 100)
                            * total_collateral_value
                        ),
                        2,
                    )
                # elif (
                #     i["lender_approval_status"] == "Rejected"
                #     or i["lender_approval_status"] == "Pledge Failure"
                # ):
                #     if (
                #         total_collateral_value > 0
                #         and total_collateral_value >= i["amount"]
                #     ):
                #         total_collateral_value -= i["amount"]
                #     total_collateral_value = round(total_collateral_value, 2)
                #     drawing_power = round(
                #         lms.round_down_amount_to_nearest_thousand(
                #             (loan_application["allowable_ltv"] / 100)
                #             * total_collateral_value
                #         ),
                #         2,
                #     )

        response = {
            "total_collateral_value": total_collateral_value,
            "drawing_power": drawing_power,
            "total_collateral_value_str": lms.amount_formatter(total_collateral_value),
            "drawing_power_str": lms.amount_formatter(drawing_power),
            "pledged_total_collateral_value_str": lms.amount_formatter(
                loan_application["pledged_total_collateral_value"]
            ),
        }

        return response
