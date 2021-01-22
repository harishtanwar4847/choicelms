# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document

import lms


class Cart(Document):
    def get_customer(self):
        return frappe.get_doc("Customer", self.customer)

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def loan_agreement(self):
        doc = {
            "full_name": "John Doe",
            "address": "Canada, North America",
            "sanctioned_credit_limit": "25000",
            "rate_of_interest1": "15",
            "rate_of_interest2": "18",
            "processing_fee": "257",
            "account_renewal_charges": "350",
            "documentation_charges": "160",
            "processing_charges_per_req": "130",
        }
        agreement_form = frappe.render_template(
            "templates/loan_agreement_form.html", {"doc": doc}
        )
        from frappe.utils.pdf import get_pdf

        agreement_form_pdf = get_pdf(agreement_form)

        from PyPDF2 import PdfFileMerger

        merger = PdfFileMerger()

        from io import BytesIO

        pdfs = [frappe.get_app_path("lms", "loan_tnc.pdf"), BytesIO(agreement_form_pdf)]

        for i in pdfs:
            merger.append(i)

        loan_agreement_pdf = frappe.utils.get_files_path("{}.pdf".format(self.name))
        merger.write(loan_agreement_pdf)

        with open(loan_agreement_pdf, "rb") as f:
            return f.read()

    def pledge_request(self):
        las_settings = frappe.get_single("LAS Settings")
        API_URL = "{}{}".format(las_settings.cdsl_host, las_settings.pledge_setup_uri)

        securities_array = []
        for i in self.items:
            j = {
                "ISIN": i.isin,
                "Quantity": str(float(i.pledged_quantity)),
                "Value": str(float(i.price)),
            }
            securities_array.append(j)

        payload = {
            "PledgorBOID": self.pledgor_boid,
            "PledgeeBOID": self.pledgee_boid,
            "PRFNumber": "SL{}".format(self.name),
            "ExpiryDate": self.expiry.strftime("%d%m%Y"),
            "ISINDTLS": securities_array,
        }

        headers = las_settings.cdsl_headers()

        return {"url": API_URL, "headers": headers, "payload": payload}

    def process(self, pledge_response):
        if self.status != "Not Processed":
            return

        isin_details_ = pledge_response.get("PledgeSetupResponse").get("ISINstatusDtls")
        isin_details = {}
        for i in isin_details_:
            isin_details[i.get("ISIN")] = i

        self.approved_total_collateral_value = 0
        total_successful_pledge = 0

        for i in self.items:
            cur = isin_details.get(i.get("isin"))
            i.psn = cur.get("PSN")
            i.error_code = cur.get("ErrorCode")

            success = len(i.psn) > 0

            if success:
                if self.status == "Not Processed":
                    self.status = "Success"
                elif self.status == "Failure":
                    self.status = "Partial Success"
                self.approved_total_collateral_value += i.amount
                total_successful_pledge += 1
            else:
                if self.status == "Not Processed":
                    self.status = "Failure"
                elif self.status == "Success":
                    self.status = "Partial Success"

        if total_successful_pledge == 0:
            self.is_processed = 1
            self.save(ignore_permissions=True)
            raise lms.PledgeSetupFailureException(
                "Pledge Setup failed.", errors=pledge_response
            )

        self.approved_total_collateral_value = round(
            self.approved_total_collateral_value, 2
        )
        self.approved_eligible_loan = round(
            lms.round_down_amount_to_nearest_thousand(
                (self.allowable_ltv / 100) * self.approved_total_collateral_value
            ),
            2,
        )
        self.is_processed = 1

    def save_collateral_ledger(self, loan_application_name=None):
        for i in self.items:
            collateral_ledger = frappe.get_doc(
                {
                    "doctype": "Collateral Ledger",
                    "cart": self.name,
                    "customer": self.customer,
                    "lender": self.lender,
                    "loan_application": loan_application_name,
                    "request_type": "Pledge",
                    "request_identifier": self.prf_number,
                    "expiry": self.expiry,
                    "pledgor_boid": self.pledgor_boid,
                    "pledgee_boid": self.pledgee_boid,
                    "isin": i.isin,
                    "quantity": i.pledged_quantity,
                    "psn": i.psn,
                    "error_code": i.error_code,
                    "is_success": len(i.psn) > 0,
                }
            )
            collateral_ledger.save(ignore_permissions=True)

    def create_loan_application(self):
        if self.status == "Not Processed":
            return

        items = []
        for item in self.items:
            if len(item.psn) > 0:
                item = frappe.get_doc(
                    {
                        "doctype": "Loan Application Item",
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
                items.append(item)

        loan_application = frappe.get_doc(
            {
                "doctype": "Loan Application",
                "total_collateral_value": self.approved_total_collateral_value,
                "pledged_total_collateral_value": self.total_collateral_value,
                "loan_margin_shortfall": self.loan_margin_shortfall,
                "pledge_status": self.status,
                "drawing_power": self.approved_eligible_loan,
                "lender": self.lender,
                "expiry_date": self.expiry,
                "allowable_ltv": self.allowable_ltv,
                "customer": self.customer,
                "customer_name": self.customer_name,
                "loan": self.loan,
                "items": items,
            }
        )
        loan_application.insert(ignore_permissions=True)
        if self.loan_margin_shortfall:
            loan_application.status = "Ready for Approval"
            loan_application.workflow_state = "Ready for Approval"
            loan_application.save(ignore_permissions=True)
        self.save_collateral_ledger(loan_application.name)
        return loan_application

    def notify_customer(self):
        customer = self.get_customer()
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        doc = frappe.get_doc("User", customer.username).as_dict()
        doc["loan_application"] = {
            "status": self.status,
            "current_total_collateral_value": self.approved_total_collateral_value_str,
            "requested_total_collateral_value": self.total_collateral_value_str,
            "sanctioned_amount": self.approved_eligible_loan_str,
        }
        frappe.enqueue_doc("Notification", "Loan Application", method="send", doc=doc)
        if doc.get("loan_application").get("status") == "Failure":
            mess = "Sorry! Your loan application was turned down since the pledge was not successful. We regret the inconvenience caused."
        elif doc.get("loan_application").get("status") == "Success":
            mess = "Congratulations! Your loan application has been approved. Please e-sign the loan agreement to avail the loan now."
        elif doc.get("loan_application").get("status") == "Partial Success":
            mess = "Congratulations! Your application is being considered favourably by our lending partner\nHowever, the pledge request was partially succesful and finally accepted at Rs. {current_total_collateral_value} against the request value of Rs. {requested_total_collateral_value}.\nAccordingly the final loan amount sanctioned is Rs. {sanctioned_amount}. Please e-sign the loan agreement to avail the loan now.".format(
                current_total_collateral_value=doc.get("loan_application").get(
                    "current_total_collateral_value"
                ),
                requested_total_collateral_value=doc.get("loan_application").get(
                    "requested_total_collateral_value"
                ),
                sanctioned_amount=doc.get("loan_application").get("sanctioned_amount"),
            )
        receiver_list = list(set([str(customer.user), str(user_kyc.mobile_number)]))
        from frappe.core.doctype.sms_settings.sms_settings import send_sms

        frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=mess)

    def on_update(self):
        if self.is_processed:
            self.notify_customer()
        # frappe.enqueue_doc("Cart", self.name, method="create_tnc_file")

    def create_tnc_file(self):
        lender = self.get_lender()
        customer = self.get_customer()
        user_kyc = customer.get_kyc()

        from num2words import num2words

        doc = {
            "esign_date": "__________",
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            "sanctioned_amount": self.eligible_loan,
            "sanctioned_amount_in_words": num2words(self.eligible_loan, lang="en_IN"),
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

        tnc_dir_path = frappe.utils.get_files_path("tnc")
        import os

        if not os.path.exists(tnc_dir_path):
            os.mkdir(tnc_dir_path)
        tnc_file = "tnc/{}.pdf".format(self.name)
        tnc_file_path = frappe.utils.get_files_path(tnc_file)

        with open(tnc_file_path, "wb") as f:
            f.write(agreement_pdf)
        f.close()

    def before_save(self):
        self.process_cart_items()
        self.process_cart()
        self.total_collateral_value_str = lms.amount_formatter(
            self.total_collateral_value
        )
        self.approved_total_collateral_value_str = lms.amount_formatter(
            self.approved_total_collateral_value
        )
        self.eligible_loan_str = lms.amount_formatter(self.eligible_loan)
        self.approved_eligible_loan_str = lms.amount_formatter(
            self.approved_eligible_loan
        )

    def process_cart_items(self):
        if self.status == "Not Processed":
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
        if self.status == "Not Processed":
            self.total_collateral_value = 0
            self.allowable_ltv = 0
            for item in self.items:
                self.total_collateral_value += item.amount
                self.allowable_ltv += item.eligible_percentage

            self.total_collateral_value = round(self.total_collateral_value, 2)
            self.allowable_ltv = float(self.allowable_ltv) / len(self.items)
            self.eligible_loan = round(
                lms.round_down_amount_to_nearest_thousand(
                    (self.allowable_ltv / 100) * self.total_collateral_value
                ),
                2,
            )

    def process_bre(self):
        las_settings = frappe.get_single("LAS Settings")
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
                        rule_type="single_script_threshold",
                        total=self.total,
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
                            rule_type="per_script_threshold",
                            total=self.total,
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
                            rule_type="group_script_threshold",
                            total=self.total,
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
                            rule_type="group_script_max_limit",
                            total=self.total,
                        )

        self.bre_passing = all([item.bre_passing for item in self.items])

    def get_interest_configuration(self):
        base_interest, collateral_value = frappe.db.get_value(
            "Interest Configuration",
            {
                "lender": self.lender,
                "from_amount": ["<=", self.total_collateral_value],
                "to_amount": [">=", self.total_collateral_value],
            },
            ["base_interest", "total_collateral_value"],
            as_dict=1,
        )
        return {"base_interest": base_interest, "collateral_value": collateral_value}


def process_concentration_rule(item, amount, rule, rule_type, total):
    threshold = rule.get(rule_type)
    threshold_type = rule.get("{}_type".format(rule_type))
    threshold_amt = (
        threshold if threshold_type == "Amount" else (threshold / 100.0) * total
    )

    if amount > threshold_amt:
        item.bre_passing = 0
        item.bre_validation_message = "Script Amount should not exceed {}.".format(
            threshold_amt
        )
