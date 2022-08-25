# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document

import lms
from lms.exceptions import PledgeSetupFailureException
from lms.lms.doctype.user_token.user_token import send_sms


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
            "renewal_charges": "350",
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
        # expiry = current.replace(year=current.year + 1)
        expiry = frappe.utils.add_years(current, 1) - timedelta(days=1)

        # Set application type
        approved_tnc = frappe.db.count(
            "Approved Terms and Conditions",
            filters={"application_doctype": "Cart", "application_name": self.name},
        )

        application_type = "New Loan"
        if self.loan and not self.loan_margin_shortfall:
            application_type = "Increase Loan"
        elif self.loan and self.loan_margin_shortfall:
            application_type = "Margin Shortfall"
        if not approved_tnc and self.loan and not self.loan_margin_shortfall:
            application_type = "Pledge More"

        items = []
        for item in self.items:
            amount = round(item.pledged_quantity, 3) * item.price
            item = frappe.get_doc(
                {
                    "doctype": "Loan Application Item",
                    "isin": item.isin,
                    "security_name": item.security_name,
                    "security_category": item.security_category,
                    "pledged_quantity": round(item.pledged_quantity, 3),
                    "requested_quantity": round(item.requested_quantity, 3),
                    "price": item.price,
                    "amount": amount,
                    "eligible_percentage": item.eligible_percentage,
                    "eligible_amount": (amount * item.eligible_percentage) / 100,
                    "type": item.type,
                    "folio": item.folio,
                    "amc_code": item.amc_code,
                    "amc_name": item.amc_name,
                    "scheme_code": item.scheme_code,
                    "prf_number": self.lien_reference_number,
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
                "application_type": application_type,
                "increased_sanctioned_limit": self.increased_sanctioned_limit,
                "instrument_type": self.instrument_type,
                "scheme_type": self.scheme_type,
            }
        ).insert(ignore_permissions=True)

        # mark cart as processed
        self.is_processed = 1
        self.save()

        if self.loan_margin_shortfall:
            loan_margin_shortfall = frappe.get_doc(
                "Loan Margin Shortfall", self.loan_margin_shortfall
            )
            if loan_margin_shortfall.status == "Pending":
                loan_margin_shortfall.status = "Request Pending"
                loan_margin_shortfall.save(ignore_permissions=True)
                frappe.db.commit()
            doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
            frappe.enqueue_doc(
                "Notification", "Margin Shortfall Action Taken", method="send", doc=doc
            )
            msg = "Dear Customer,\nThank you for taking action against the margin shortfall.\nYou can view the 'Action Taken' summary on the dashboard of the app under margin shortfall banner. Spark Loans"
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Margin shortfall – Action taken",
                fields=["*"],
            )
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=self.loan,
                customer=self.get_customer(),
            )
            receiver_list = [str(self.get_customer().phone)]
            if self.get_customer().get_kyc().mob_num:
                receiver_list.append(str(self.get_customer().get_kyc().mob_num))
            if self.get_customer().get_kyc().choice_mob_no:
                receiver_list.append(str(self.get_customer().get_kyc().choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)

        # if self.loan_margin_shortfall:
        #     loan_application.status = "Ready for Approval"
        #     loan_application.workflow_state = "Ready for Approval"
        #     loan_application.save(ignore_permissions=True)

        if not self.loan_margin_shortfall:
            customer = frappe.get_doc("Loan Customer", self.customer)
            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            doc["loan_application_name"] = loan_application.name
            doc["minimum_sanctioned_limit"] = loan_application.minimum_sanctioned_limit
            # frappe.enqueue_doc(
            #     "Notification", "Loan Application Creation", method="send", doc=doc
            # )
            if not loan_application.remarks:
                msg_type = "pledge"
                email_subject = "Pledge Application Success"
                if self.instrument_type == "Mutual Fund":
                    application_type = "Lien"
                    msg_type = "lien"
                    email_subject = "Lien Application Successful"

                frappe.enqueue_doc(
                    "Notification", email_subject, method="send", doc=doc
                )
                mess = "Dear Customer,\nYour {} request has been successfully received and is under process. We shall reach out to you very soon. Thank you for your patience -Spark Loans".format(
                    msg_type
                )
                # if mess:
                receiver_list = [str(self.get_customer().phone)]
                if doc.mob_num:
                    receiver_list.append(str(doc.mob_num))
                if doc.choice_mob_no:
                    receiver_list.append(str(doc.choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=mess)
        return loan_application

    def create_tnc_file(self):
        lender = self.get_lender()
        customer = self.get_customer()
        user_kyc = customer.get_kyc()
        if self.loan:
            loan = frappe.get_doc("Loan", self.loan)
            increased_sanctioned_limit = lms.round_down_amount_to_nearest_thousand(
                (self.total_collateral_value + loan.total_collateral_value)
                * self.allowable_ltv
                / 100
            )
            self.increased_sanctioned_limit = (
                increased_sanctioned_limit
                if increased_sanctioned_limit < lender.maximum_sanctioned_limit
                else lender.maximum_sanctioned_limit
            )
            self.save(ignore_permissions=True)

        from num2words import num2words

        if user_kyc.address_details:
            address_details = frappe.get_doc(
                "Customer Address Details", user_kyc.address_details
            )
            address = (
                str(address_details.perm_line1)
                + ", "
                + str(address_details.perm_line2)
                + ", "
                + str(address_details.perm_line3)
                + ", "
                + str(address_details.perm_city)
                + ", "
                + str(address_details.perm_dist)
                + ", "
                + str(address_details.perm_state)
                + ", "
                + str(address_details.perm_country)
                + ", "
                + str(address_details.perm_pin)
            )
        else:
            address = ""

        doc = {
            "esign_date": "__________",
            "loan_application_number": " ",
            "borrower_name": user_kyc.fullname,
            "borrower_address": address,
            "sanctioned_amount": lms.validate_rupees(
                self.increased_sanctioned_limit
                if self.loan and not self.loan_margin_shortfall
                else self.eligible_loan
            ),
            "sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees(
                    self.increased_sanctioned_limit
                    if self.loan and not self.loan_margin_shortfall
                    else self.eligible_loan,
                )
            ).title(),
            "rate_of_interest": lender.rate_of_interest,
            "default_interest": lender.default_interest,
            "rebait_threshold": lender.rebait_threshold,
            "renewal_charges": lms.validate_rupees(lender.renewal_charges)
            if lender.renewal_charge_type == "Fix"
            else lms.validate_percent(lender.renewal_charges),
            "renewal_charge_type": lender.renewal_charge_type,
            "renewal_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.renewal_charges)
            ).title()
            if lender.renewal_charge_type == "Fix"
            else "",
            # else num2words(lender.renewal_charges).title(),
            "renewal_min_amt": lms.validate_rupees(lender.renewal_minimum_amount),
            "renewal_max_amt": lms.validate_rupees(lender.renewal_maximum_amount),
            "documentation_charge": lms.validate_rupees(lender.documentation_charges)
            if lender.documentation_charge_type == "Fix"
            else lms.validate_percent(lender.documentation_charges),
            "documentation_charge_type": lender.documentation_charge_type,
            "documentation_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.documentation_charges)
            ).title()
            if lender.documentation_charge_type == "Fix"
            else "",
            "documentation_min_amt": lms.validate_rupees(
                lender.lender_documentation_minimum_amount
            ),
            "documentation_max_amt": lms.validate_rupees(
                lender.lender_documentation_maximum_amount
            ),
            "lender_processing_fees_type": lender.lender_processing_fees_type,
            "processing_charge": lms.validate_rupees(lender.lender_processing_fees)
            if lender.lender_processing_fees_type == "Fix"
            else lms.validate_percent(lender.lender_processing_fees),
            "processing_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.lender_processing_fees)
            ).title()
            if lender.lender_processing_fees_type == "Fix"
            else "",
            "processing_min_amt": lms.validate_rupees(
                lender.lender_processing_minimum_amount
            ),
            "processing_max_amt": lms.validate_rupees(
                lender.lender_processing_maximum_amount
            ),
            # "stamp_duty_charges": lms.validate_rupees(lender.lender_stamp_duty_minimum_amount),
            "transaction_charges_per_request": lms.validate_rupees(
                lender.transaction_charges_per_request
            ),
            "security_selling_share": lender.security_selling_share,
            "cic_charges": lms.validate_rupees(lender.cic_charges),
            "total_pages": lender.total_pages,
            "lien_initiate_charge_type": lender.lien_initiate_charge_type,
            "invoke_initiate_charge_type": lender.invoke_initiate_charge_type,
            "revoke_initiate_charge_type": lender.revoke_initiate_charge_type,
            "lien_initiate_charge_minimum_amount": lms.validate_rupees(
                lender.lien_initiate_charge_minimum_amount
            ),
            "lien_initiate_charge_maximum_amount": lms.validate_rupees(
                lender.lien_initiate_charge_maximum_amount
            ),
            "lien_initiate_charges": lms.validate_rupees(lender.lien_initiate_charges)
            if lender.lien_initiate_charge_type == "Fix"
            else lms.validate_percent(lender.lien_initiate_charges),
            "invoke_initiate_charges_minimum_amount": lms.validate_rupees(
                lender.invoke_initiate_charges_minimum_amount
            ),
            "invoke_initiate_charges_maximum_amount": lms.validate_rupees(
                lender.invoke_initiate_charges_maximum_amount
            ),
            "invoke_initiate_charges": lms.validate_rupees(
                lender.invoke_initiate_charges
            )
            if lender.invoke_initiate_charge_type == "Fix"
            else lms.validate_percent(lender.invoke_initiate_charges),
            "revoke_initiate_charges_minimum_amount": lms.validate_rupees(
                lender.revoke_initiate_charges_minimum_amount
            ),
            "revoke_initiate_charges_maximum_amount": lms.validate_rupees(
                lender.revoke_initiate_charges_maximum_amount
            ),
            "revoke_initiate_charges": lms.validate_rupees(
                lender.revoke_initiate_charges
            )
            if lender.revoke_initiate_charge_type == "Fix"
            else lms.validate_percent(lender.revoke_initiate_charges),
        }
        if self.loan and not self.loan_margin_shortfall:
            loan = frappe.get_doc("Loan", self.loan)
            doc["old_sanctioned_amount"] = lms.validate_rupees(loan.sanctioned_limit)
            doc["old_sanctioned_amount_in_words"] = lms.number_to_word(
                lms.validate_rupees(loan.sanctioned_limit)
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
            if self.instrument_type != "Mutual Fund":
                self.pledgee_boid = self.get_lender().demat_account_number
            isin = [i.isin for i in self.items]
            price_map = lms.get_security_prices(isin)
            allowed_securities = lms.get_allowed_securities(
                isin, self.lender, self.instrument_type
            )

            for i in self.items:
                security = allowed_securities.get(i.isin)
                i.security_category = security.security_category
                i.security_name = security.security_name
                i.eligible_percentage = security.eligible_percentage

                i.price = price_map.get(i.isin, 0)
                # i.amount = i.pledged_quantity * i.price
                amount = i.pledged_quantity * i.price
                i.amount = amount
                if i.type != "Shares":
                    i.amount = round(i.pledged_quantity, 3) * i.price
                    i.eligible_amount = (
                        round(i.pledged_quantity, 3)
                        * i.price
                        * security.eligible_percentage
                    ) / 100

    def process_cart(self):
        if not self.is_processed:
            lender = self.get_lender()
            self.total_collateral_value = 0
            allowable_ltv = 0
            eligible_loan = 0
            for item in self.items:
                self.total_collateral_value += item.amount
                allowable_ltv += item.eligible_percentage

            self.total_collateral_value = round(self.total_collateral_value, 2)
            if self.instrument_type == "Shares":
                self.allowable_ltv = float(allowable_ltv) / len(self.items)
                eligible_loan = (self.allowable_ltv / 100) * self.total_collateral_value

            else:
                for i in self.items:
                    eligible_loan += i.eligible_amount

            eligible_loan = round(
                lms.round_down_amount_to_nearest_thousand(eligible_loan),
                2,
            )

            self.eligible_loan = (
                eligible_loan
                if eligible_loan < lender.maximum_sanctioned_limit
                else lender.maximum_sanctioned_limit
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
