# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document

import lms
from lms.exceptions import PledgeSetupFailureException


class Cart(Document):
    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

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

    def create_loan_application(self):
        if self.is_processed:
            return

        current = frappe.utils.now_datetime()
        expiry = current.replace(year=current.year + 5, day=1)

        items = []
        for item in self.items:
            item = frappe.get_doc(
                {
                    "doctype": "Loan Application Item",
                    "isin": item.isin,
                    "security_name": item.security_name,
                    "security_category": item.security_category,
                    "pledged_quantity": item.pledged_quantity,
                    "price": item.price,
                    "amount": item.amount,
                }
            )
            items.append(item)

        loan_application = frappe.get_doc(
            {
                "doctype": "Loan Application",
                "total_collateral_value": self.total_collateral_value,
                "pledged_total_collateral_value": self.total_collateral_value,
                "loan_margin_shortfall": self.loan_margin_shortfall,
                "drawing_power": self.eligible_loan,
                "lender": self.lender,
                "expiry_date": expiry,
                "allowable_ltv": self.allowable_ltv,
                "customer": self.customer,
                "customer_name": self.customer_name,
                "pledgor_boid": self.pledgor_boid,
                "pledgee_boid": self.pledgee_boid,
                "loan": self.loan,
                "workflow_state": "Waiting to be pledged",
                "items": items,
            }
        )
        loan_application.insert(ignore_permissions=True)

        # mark cart as processed
        self.is_processed = 1
        self.save()

        # if self.loan_margin_shortfall:
        #     loan_application.status = "Ready for Approval"
        #     loan_application.workflow_state = "Ready for Approval"
        #     loan_application.save(ignore_permissions=True)
        customer = frappe.get_doc("Loan Customer", self.customer)
        doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
        frappe.enqueue_doc(
            "Notification", "Loan Application Creation", method="send", doc=doc
        )
        return loan_application

    def create_tnc_file(self):
        lender = self.get_lender()
        customer = self.get_customer()
        user_kyc = customer.get_kyc()
        if self.loan and not self.loan_margin_shortfall:
            loan = frappe.get_doc("Loan", self.loan)

        from num2words import num2words

        doc = {
            "esign_date": "__________",
            "loan_application_number": " ",
            "borrower_name": user_kyc.investor_name,
            "borrower_address": user_kyc.address,
            "sanctioned_amount": lms.round_down_amount_to_nearest_thousand(
                (self.total_collateral_value + loan.total_collateral_value)
                * self.allowable_ltv
                / 100
            )
            if self.loan
            else self.eligible_loan,
            "sanctioned_amount_in_words": num2words(
                lms.round_down_amount_to_nearest_thousand(
                    (self.total_collateral_value + loan.total_collateral_value)
                    * self.allowable_ltv
                    / 100
                )
                if self.loan
                else self.eligible_loan,
                lang="en_IN",
            ).title(),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "account_renewal_charges": lender.account_renewal_charges,
            "documentation_charges": lender.documentation_charges,
            "stamp_duty_charges": (lender.stamp_duty / 100)
            * self.eligible_loan,  # CR loan agreement changes
            "processing_fee": lender.lender_processing_fees,
            "transaction_charges_per_request": lender.transaction_charges_per_request,
            "security_selling_share": lender.security_selling_share,
            "cic_charges": lender.cic_charges,
            "total_pages": lender.total_pages,
        }

        if self.loan and not self.loan_margin_shortfall:
            loan = frappe.get_doc("Loan", self.loan)
            doc["old_sanctioned_amount"] = loan.drawing_power
            doc["old_sanctioned_amount_in_words"] = num2words(
                loan.drawing_power, lang="en_IN"
            ).title()
            agreement_template = lender.get_loan_enhancement_agreement_template()
        else:
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
        self.eligible_loan_str = lms.amount_formatter(self.eligible_loan)

    def process_cart_items(self):
        if not self.is_processed:
            self.pledgee_boid = self.get_lender().demat_account_number
            isin = [i.isin for i in self.items]
            price_map = lms.get_security_prices(isin)
            allowed_securities = lms.get_allowed_securities(isin, self.lender)

            for i in self.items:
                security = allowed_securities.get(i.isin)
                i.security_category = security.security_category
                i.security_name = security.security_name
                i.eligible_percentage = security.eligible_percentage

                i.price = price_map.get(i.isin, 0)
                i.amount = i.pledged_quantity * i.price

    def process_cart(self):
        if not self.is_processed:
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
