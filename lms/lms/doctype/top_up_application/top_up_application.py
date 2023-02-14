# -*- coding: utf-8 -*-
# Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import datetime, timedelta

import frappe
from frappe.model.document import Document
from num2words import num2words

import lms
from lms.lms.doctype.user_token.user_token import send_sms


class TopupApplication(Document):
    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def get_loan(self):
        return frappe.get_doc("Loan", self.loan)

    def on_submit(self):
        loan = self.get_loan()

        # apply loan charges
        self.apply_loan_charges(loan)
        loan.reload()

        loan.drawing_power += self.top_up_amount
        loan.sanctioned_limit += self.top_up_amount
        loan.expiry_date = self.expiry_date
        loan.save(ignore_permissions=True)
        frappe.db.commit()

        self.map_loan_agreement_file(loan)
        # self.notify_customer()

        date = frappe.utils.now_datetime().date()
        lms.client_sanction_details(loan, date)

    def apply_loan_charges(self, loan):
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
            renewal_charges_reference = loan.create_loan_transaction(
                "Account Renewal Charges", renewal_charges, approve=True
            )
            # if lender.cgst_on_account_renewal_charges > 0:
            #     cgst = renewal_charges * (lender.cgst_on_account_renewal_charges / 100)
            #     gst_percent = (lender.cgst_on_account_renewal_charges,)
            #     loan.create_loan_transaction(
            #         "CGST on Account renewal charges",
            #         cgst,
            #         gst_percent,
            #         charge_reference=renewal_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_account_renewal_charges > 0:
            #     sgst = renewal_charges * (lender.sgst_on_account_renewal_charges / 100)
            #     gst_percent = (lender.sgst_on_account_renewal_charges,)
            #     loan.create_loan_transaction(
            #         "SGST on Account renewal charges",
            #         sgst,
            #         gst_percent,
            #         charge_reference=renewal_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_account_renewal_charges > 0:
            #     igst = renewal_charges * (lender.igst_on_account_renewal_charges / 100)
            #     gst_percent = lender.igst_on_account_renewal_charges
            #     loan.create_loan_transaction(
            #         "IGST on Account renewal charges",
            #         igst,
            #         gst_percent,
            #         charge_reference=renewal_charges_reference.name,
            #         approve=True,
            #     )

        # Processing fees
        processing_fees = lender.lender_processing_fees
        if lender.lender_processing_fees_type == "Percentage":
            days_left_to_expiry = days_in_year
            amount = (
                (processing_fees / 100)
                * self.top_up_amount
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
            processing_fees_reference = loan.create_loan_transaction(
                "Processing Fees",
                processing_fees,
                approve=True,
            )
            # if lender.cgst_on_processing_fees > 0:
            #     cgst = processing_fees * (lender.cgst_on_processing_fees / 100)
            #     gst_percent = lender.cgst_on_processing_fees
            #     loan.create_loan_transaction(
            #         "CGST on Processing Fees",
            #         cgst,
            #         gst_percent,
            #         charge_reference=processing_fees_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_processing_fees > 0:
            #     sgst = processing_fees * (lender.sgst_on_processing_fees / 100)
            #     gst_percent = lender.sgst_on_processing_fees
            #     loan.create_loan_transaction(
            #         "SGST on Processing Fees",
            #         sgst,
            #         gst_percent,
            #         charge_reference=processing_fees_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_processing_fees > 0:
            #     igst = processing_fees * (lender.igst_on_processing_fees / 100)
            #     gst_percent = lender.igst_on_processing_fees
            #     loan.create_loan_transaction(
            #         "IGST on Processing Fees",
            #         igst,
            #         gst_percent,
            #         charge_reference=processing_fees_reference.name,
            #         approve=True,
            #     )

        # Stamp Duty
        stamp_duty = lender.stamp_duty
        if lender.stamp_duty_type == "Percentage":
            amount = (stamp_duty / 100) * self.top_up_amount
            stamp_duty = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_stamp_duty_minimum_amount",
                "lender_stamp_duty_maximum_amount",
            )

        if stamp_duty > 0:
            stamp_duty_reference = loan.create_loan_transaction(
                "Stamp Duty",
                stamp_duty,
                approve=True,
            )
            # StampDuty changes for GST
            # if lender.cgst_on_stamp_duty > 0:
            #     cgst = stamp_duty * (lender.cgst_on_stamp_duty / 100)
            #     gst_percent = lender.cgst_on_stamp_duty
            #     loan.create_loan_transaction(
            #         "CGST on Stamp Duty",
            #         cgst,
            #         gst_percent,
            #         charge_reference=stamp_duty_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_stamp_duty > 0:
            #     sgst = stamp_duty * (lender.sgst_on_stamp_duty / 100)
            #     gst_percent = lender.sgst_on_stamp_duty
            #     loan.create_loan_transaction(
            #         "SGST on Stamp Duty",
            #         sgst,
            #         gst_percent,
            #         charge_reference=stamp_duty_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_stamp_duty > 0:
            #     igst = stamp_duty * (lender.igst_on_stamp_duty / 100)
            #     gst_percent = lender.igst_on_stamp_duty
            #     loan.create_loan_transaction(
            #         "IGST on Stamp Duty",
            #         igst,
            #         gst_percent,
            #         charge_reference=stamp_duty_reference.name,
            #         approve=True,
            #     )

        # Documentation Charges
        documentation_charges = lender.documentation_charges
        if lender.documentation_charge_type == "Percentage":
            amount = (documentation_charges / 100) * self.top_up_amount
            documentation_charges = loan.validate_loan_charges_amount(
                lender,
                amount,
                "lender_documentation_minimum_amount",
                "lender_documentation_maximum_amount",
            )

        if documentation_charges > 0:
            documentation_charges_reference = loan.create_loan_transaction(
                "Documentation Charges",
                documentation_charges,
                approve=True,
            )
            # Charges on GST
            # if lender.cgst_on_documentation_charges > 0:
            #     cgst = documentation_charges * (
            #         lender.cgst_on_documentation_charges / 100
            #     )
            #     gst_percent = lender.cgst_on_documentation_charges
            #     loan.create_loan_transaction(
            #         "CGST on Documentation Charges",
            #         cgst,
            #         gst_percent,
            #         charge_reference=documentation_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.sgst_on_documentation_charges > 0:
            #     sgst = documentation_charges * (
            #         lender.sgst_on_documentation_charges / 100
            #     )
            #     gst_percent = lender.sgst_on_documentation_charges
            #     loan.create_loan_transaction(
            #         "SGST on Documentation Charges",
            #         sgst,
            #         gst_percent,
            #         charge_reference=documentation_charges_reference.name,
            #         approve=True,
            #     )
            # if lender.igst_on_documentation_charges > 0:
            #     igst = documentation_charges * (
            #         lender.igst_on_documentation_charges / 100
            #     )
            #     gst_percent = lender.igst_on_documentation_charges
            #     loan.create_loan_transaction(
            #         "IGST on Documentation Charges",
            #         igst,
            #         gst_percent,
            #         charge_reference=documentation_charges_reference.name,
            #         approve=True,
            #     )

    def on_update(self):
        if self.status == "Esign Done" and self.lender_esigned_document != None:
            return
        self.notify_customer()

    def before_submit(self):
        if not self.lender_esigned_document:
            frappe.throw("Please upload Lender Esigned Document")

        loan = self.get_loan()
        updated_top_up_amt = loan.max_topup_amount()
        if (self.top_up_amount + loan.sanctioned_limit) > self.maximum_sanctioned_limit:
            frappe.throw(
                "Can not Approve this Top up Application as Sanctioned limit will cross Maximum Sanctioned limit Cap"
            )
        if not updated_top_up_amt or updated_top_up_amt < self.top_up_amount:
            frappe.throw("Top up not available")
        if self.top_up_amount <= 0:
            frappe.throw("Top up can not be approved with Amount Rs. 0")
        if self.status == "Approved":
            current = frappe.utils.now_datetime()
            expiry = frappe.utils.add_years(current, 1) - timedelta(days=1)
            self.expiry_date = datetime.strftime(expiry, "%Y-%m-%d")

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    # def create_tnc_file(self):
    #     lender = self.get_lender()
    #     customer = self.get_customer()
    #     user_kyc = customer.get_kyc()
    #     loan = self.get_loan()

    #     doc = {
    #         "esign_date": "__________",
    #         "loan_application_number": self.loan,
    #         "borrower_name": user_kyc.investor_name,
    #         "borrower_address": user_kyc.address,
    #         # "sanctioned_amount": self.top_up_amount,
    #         # "sanctioned_amount_in_words": num2words(
    #         #     self.top_up_amount, lang="en_IN"
    #         # ).title(),
    #         "sanctioned_amount": (self.top_up_amount + loan.sanctioned_limit),
    #         "sanctioned_amount_in_words": num2words(
    #             (self.top_up_amount + loan.sanctioned_limit), lang="en_IN"
    #         ).title(),
    #         "old_sanctioned_amount": loan.sanctioned_limit,
    #         "old_sanctioned_amount_in_words": num2words(
    #             loan.sanctioned_limit, lang="en_IN"
    #         ).title(),
    #         "rate_of_interest": lender.rate_of_interest,
    #         "default_interest": lender.default_interest,
    #         "account_renewal_charges": lender.account_renewal_charges,
    #         "documentation_charges": lender.documentation_charges,
    #         # "stamp_duty_charges": (lender.stamp_duty / 100)
    #         # * self.sanctioned_limit,  # CR loan agreement changes
    #         "processing_fee": lender.lender_processing_fees,
    #         "transaction_charges_per_request": lender.transaction_charges_per_request,
    #         "security_selling_share": lender.security_selling_share,
    #         "cic_charges": lender.cic_charges,
    #         "total_pages": lender.total_pages,
    #     }

    #     agreement_template = lender.get_loan_enhancement_agreement_template()

    #     agreement = frappe.render_template(
    #         agreement_template.get_content(), {"doc": doc}
    #     )

    #     from frappe.utils.pdf import get_pdf

    #     agreement_pdf = get_pdf(agreement)

    #     tnc_dir_path = frappe.utils.get_files_path("tnc")
    #     import os

    #     if not os.path.exists(tnc_dir_path):
    #         os.mkdir(tnc_dir_path)
    #     tnc_file = "tnc/{}.pdf".format(self.loan)
    #     tnc_file_path = frappe.utils.get_files_path(tnc_file)

    #     with open(tnc_file_path, "wb") as f:
    #         f.write(agreement_pdf)
    #     f.close()

    def esign_request(self):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()
        loan = self.get_loan()

        if user_kyc.address_details:
            address_details = frappe.get_doc(
                "Customer Address Details", user_kyc.address_details
            )
            address = (
                (
                    (str(address_details.perm_line1) + ", ")
                    if address_details.perm_line1
                    else ""
                )
                + (
                    (str(address_details.perm_line2) + ", ")
                    if address_details.perm_line2
                    else ""
                )
                + (
                    (str(address_details.perm_line3) + ", ")
                    if address_details.perm_line3
                    else ""
                )
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

        if user_kyc.address_details:
            address_details = frappe.get_doc(
                "Customer Address Details", user_kyc.address_details
            )

            line1 = str(address_details.perm_line1)
            if line1:
                addline1 = "{},<br/>".format(line1)
            else:
                addline1 = ""

            line2 = str(address_details.perm_line2)
            if line2:
                addline2 = "{},<br/>".format(line2)
            else:
                addline2 = ""

            line3 = str(address_details.perm_line3)
            if line3:
                addline3 = "{},<br/>".format(line3)
            else:
                addline3 = ""

            perm_city = str(address_details.perm_city)
            perm_dist = str(address_details.perm_dist)
            perm_state = str(address_details.perm_state)
            perm_pin = str(address_details.perm_pin)

        else:
            address_details = ""

        increased_sanction_limit = self.top_up_amount + loan.sanctioned_limit
        interest_config = frappe.get_value(
            "Interest Configuration",
            {
                "to_amount": [
                    ">=",
                    lms.validate_rupees(float(increased_sanction_limit)),
                ],
            },
            order_by="to_amount asc",
        )
        int_config = frappe.get_doc("Interest Configuration", interest_config)
        roi_ = round((int_config.base_interest * 12), 2)
        charges = lms.charges_for_apr(
            lender.name, lms.validate_rupees(float(increased_sanction_limit))
        )
        apr = round(
            lms.calculate_apr(
                self.name,
                roi_,
                12,
                int(lms.validate_rupees(float(increased_sanction_limit))),
                charges.get("total"),
            ),
            2,
        )
        annual_default_interest = lender.default_interest * 12
        interest_charges_in_amount = int((float(increased_sanction_limit))) * (
            roi_ / 100
        )

        doc = {
            "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
            "loan_account_number": self.name,
            "borrower_name": user_kyc.fullname,
            "borrower_address": address,
            "addline1": addline1,
            "addline2": addline2,
            "addline3": addline3,
            "city": perm_city,
            "district": perm_dist,
            "state": perm_state,
            "pincode": perm_pin,
            "sanctioned_amount": frappe.utils.fmt_money(
                float(increased_sanction_limit)
            ),
            # "sanctioned_amount": (float(increased_sanction_limit)),
            "sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees(float(increased_sanction_limit))
            ).title(),
            "old_sanctioned_amount": frappe.utils.fmt_money(loan.sanctioned_limit),
            "old_sanctioned_amount_in_words": num2words(
                loan.sanctioned_limit, lang="en_IN"
            ).title(),
            "roi": roi_,
            "apr": apr,
            "documentation_charges_kfs": frappe.utils.fmt_money(
                charges.get("documentation_charges")
            ),
            "processing_charges_kfs": frappe.utils.fmt_money(
                charges.get("processing_fees")
            ),
            "net_disbursed_amount": frappe.utils.fmt_money(
                float(increased_sanction_limit) - charges.get("total")
            ),
            "total_amount_to_be_paid": frappe.utils.fmt_money(
                float(increased_sanction_limit)
                + charges.get("total")
                + interest_charges_in_amount
            ),
            "loan_application_no": self.name,
            "rate_of_interest": lender.rate_of_interest,
            "rebate_interest": int_config.rebait_interest,
            "default_interest": annual_default_interest,
            "rebait_threshold": lender.rebait_threshold,
            "interest_charges_in_amount": frappe.utils.fmt_money(
                interest_charges_in_amount
            ),
            "renewal_charges": lms.validate_rupees(lender.renewal_charges)
            if lender.renewal_charge_type == "Fix"
            else lms.validate_percent(lender.renewal_charges),
            "renewal_charge_type": lender.renewal_charge_type,
            "renewal_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.renewal_charges)
            ).title()
            if lender.renewal_charge_type == "Fix"
            else "",
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
            # "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
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

        agreement_template = lender.get_loan_enhancement_agreement_template()
        loan_agreement_file = "loan-enhancement-aggrement.pdf"
        coordinates = lender.enhancement_coordinates.split(",")
        esign_page = lender.enhancement_esign_page
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

    def notify_customer(self):
        doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
        doc["top_up_application"] = {
            "status": self.status,
            "loan": self.loan,
            "top_up_amount": self.top_up_amount,
        }
        # if self.status in ["Pending", "Approved", "Rejected"]:
        frappe.enqueue_doc("Notification", "Top up Application", method="send", doc=doc)
        mess = ""
        loan = ""
        fcm_notification = {}
        if doc.get("top_up_application").get("status") == "Pending":
            # mess = "Your request has been successfully received. You will be notified when your new OD limit is approved by our banking partner."
            mess = 'Dear Customer,\nCongratulations! Your Top Up application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans'

            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Application for top-up accepted",
                fields=["*"],
            )

        if doc.get("top_up_application").get("status") == "Approved":
            mess = "Dear Customer,\nCongratulations! Your loan account has been topped up. Please check the app for details. -Spark Loans"

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Loan account topped up", fields=["*"]
            )
            loan = self.loan

        if doc.get("top_up_application").get("status") == "Rejected":
            # mess = "Sorry! Your Top up application was turned down. We regret the inconvenience caused."

            mess = "Dear Customer,\nSorry! Your top up request could not be executed due to technical reasons. We regret the inconvenience caused.Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Top up rejected", fields=["*"]
            )
            loan = self.loan

        if mess:
            receiver_list = [str(self.get_customer().phone)]
            if doc.mob_num:
                receiver_list.append(str(doc.mob_num))
            if doc.choice_mob_no:
                receiver_list.append(str(doc.choice_mob_no))

            receiver_list = list(set(receiver_list))

            frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=mess)

        if fcm_notification:
            lms.send_spark_push_notification(
                fcm_notification=fcm_notification,
                message=fcm_notification.message,
                loan=loan,
                customer=self.get_customer(),
            )

    def map_loan_agreement_file(self, loan):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.lender_esigned_document}
        )

        loan_agreement = frappe.get_doc("File", file_name)

        loan_agreement_file_name = "{}-loan-enhancement-aggrement.pdf".format(loan.name)
        event = "Top up"

        is_private = 0

        # loan_agreement_file_url = frappe.utils.get_files_path(
        #     loan_agreement_file_name, is_private=is_private
        # )

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

    def before_save(self):
        loan = self.get_loan()
        self.actual_drawing_power = loan.actual_drawing_power
        self.instrument_type = loan.instrument_type
        self.scheme_type = loan.scheme_type
        self.sanctioned_limit = loan.sanctioned_limit
        lender = self.get_lender()
        self.minimum_sanctioned_limit = lender.minimum_sanctioned_limit
        self.maximum_sanctioned_limit = lender.maximum_sanctioned_limit
        if self.status == "Pending":
            self.sanction_letter()

    def get_customer(self):
        return frappe.get_doc("Loan Customer", self.customer)

    def sanction_letter(self):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()
        loan = self.get_loan()
        if user_kyc.address_details:
            address_details = frappe.get_doc(
                "Customer Address Details", user_kyc.address_details
            )

            line1 = str(address_details.perm_line1)
            if line1:
                addline1 = "{},<br/>".format(line1)
            else:
                addline1 = ""

            line2 = str(address_details.perm_line2)
            if line2:
                addline2 = "{},<br/>".format(line2)
            else:
                addline2 = ""

            line3 = str(address_details.perm_line3)
            if line3:
                addline3 = "{},<br/>".format(line3)
            else:
                addline3 = ""

            perm_city = str(address_details.perm_city)
            perm_dist = str(address_details.perm_dist)
            perm_state = str(address_details.perm_state)
            perm_pin = str(address_details.perm_pin)

        else:
            address = ""

        increased_sanction_limit = self.top_up_amount + loan.sanctioned_limit
        interest_config = frappe.get_value(
            "Interest Configuration",
            {
                "to_amount": [
                    ">=",
                    lms.validate_rupees(float(increased_sanction_limit)),
                ],
            },
            order_by="to_amount asc",
        )
        int_config = frappe.get_doc("Interest Configuration", interest_config)
        roi_ = round((int_config.base_interest * 12), 2)
        charges = lms.charges_for_apr(
            lender.name, lms.validate_rupees(float(increased_sanction_limit))
        )
        apr = round(
            lms.calculate_apr(
                self.name,
                roi_,
                12,
                int(lms.validate_rupees(float(increased_sanction_limit))),
                charges.get("total"),
            ),
            2,
        )
        annual_default_interest = lender.default_interest * 12
        interest_charges_in_amount = int(
            lms.validate_rupees(float(increased_sanction_limit))
        ) * (roi_ / 100)

        doc = {
            "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
            "loan_account_no": loan.name if self.loan else "",
            "borrower_name": user_kyc.fullname,
            "addline1": addline1,
            "addline2": addline2,
            "addline3": addline3,
            "city": perm_city,
            "district": perm_dist,
            "state": perm_state,
            "pincode": perm_pin,
            # "sanctioned_amount": frappe.utils.fmt_money(float(self.drawing_power)),
            "sanctioned_amount": frappe.utils.fmt_money(
                float(increased_sanction_limit)
            ),
            "sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees(float(increased_sanction_limit))
            ).title(),
            "roi": roi_,
            "apr": apr,
            "documentation_charges_kfs": frappe.utils.fmt_money(
                charges.get("documentation_charges")
            ),
            "processing_charges_kfs": frappe.utils.fmt_money(
                charges.get("processing_fees")
            ),
            "net_disbursed_amount": frappe.utils.fmt_money(
                float(increased_sanction_limit) - charges.get("total")
            ),
            "total_amount_to_be_paid": frappe.utils.fmt_money(
                float(increased_sanction_limit)
                + charges.get("total")
                + interest_charges_in_amount
            ),
            "loan_application_no": self.name,
            "rate_of_interest": lender.rate_of_interest,
            "rebate_interest": int_config.rebait_interest,
            "default_interest": annual_default_interest,
            "rebait_threshold": lender.rebait_threshold,
            "interest_charges_in_amount": frappe.utils.fmt_money(
                interest_charges_in_amount
            ),
            "renewal_charges": lms.validate_rupees(lender.renewal_charges)
            if lender.renewal_charge_type == "Fix"
            else lms.validate_percent(lender.renewal_charges),
            "renewal_charge_type": lender.renewal_charge_type,
            "renewal_charge_in_words": lms.number_to_word(
                lms.validate_rupees(lender.renewal_charges)
            ).title()
            if lender.renewal_charge_type == "Fix"
            else "",
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
            # "stamp_duty_charges": int(lender.lender_stamp_duty_minimum_amount),
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

        sanctioned_letter_pdf_file = "{}-{}-sanctioned_letter.pdf".format(
            self.name, frappe.utils.now_datetime().date()
        )
        sll_name = sanctioned_letter_pdf_file

        sanctioned_leter_pdf_file_path = frappe.utils.get_files_path(
            sanctioned_letter_pdf_file
        )

        sanction_letter_template = lender.get_sanction_letter_template()

        # sanction_letter = frappe.render_template(
        #     sanction_letter_template.get_content(), {"doc": doc}
        # )

        s_letter = frappe.render_template(
            sanction_letter_template.get_content(), {"doc": doc}
        )

        pdf_file = open(sanctioned_leter_pdf_file_path, "wb")

        from frappe.utils.pdf import get_pdf

        pdf = get_pdf(s_letter)

        pdf_file.write(pdf)
        pdf_file.close()
        sL_letter = frappe.utils.get_url("files/{}".format(sanctioned_letter_pdf_file))
        sl = frappe.get_all(
            "Sanction Letter and CIAL Log", filters={"loan": self.loan}, fields=["*"]
        )
        if not sl:
            sl = frappe.get_doc(
                dict(
                    doctype="Sanction Letter and CIAL Log",
                    loan_application=self.name,
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
            self.sl_entries = sl.name
            sanction_letter_table = frappe.get_all(
                "Sanction Letter Entries",
                filters={"topup_application_no": self.name},
                fields=["*"],
            )
            if not sanction_letter_table:
                sll = frappe.get_doc(
                    {
                        "doctype": "Sanction Letter Entries",
                        "parent": sl.name,
                        "parentfield": "sl_table",
                        "parenttype": "Sanction Letter and CIAL Log",
                        "sanction_letter": sL_letter,
                        "topup_application_no": self.name,
                        "date_of_acceptance": frappe.utils.now_datetime().date(),
                        "rebate_interest": lender.rebait_threshold,
                    }
                ).insert(ignore_permissions=True)
                frappe.db.commit()

        else:
            print("status", self.status)
            sl = frappe.get_all(
                "Sanction Letter and CIAL Log",
                filters={"loan": self.loan},
                fields=["*"],
            )
            self.sl_entries = sl[0].name
            sanction_letter_table = frappe.get_all(
                "Sanction Letter Entries",
                filters={"topup_application_no": self.name},
                fields=["*"],
            )
            print("sanction_letter_table", sanction_letter_table)
            if not sanction_letter_table:
                sll = frappe.get_doc(
                    {
                        "doctype": "Sanction Letter Entries",
                        "parent": sl[0].name,
                        "parentfield": "sl_table",
                        "parenttype": "Sanction Letter and CIAL Log",
                        "sanction_letter": sL_letter,
                        "topup_application_no": self.name,
                        "date_of_acceptance": frappe.utils.now_datetime().date(),
                        "rebate_interest": lender.rebait_threshold,
                    }
                ).insert(ignore_permissions=True)
                frappe.db.commit()

        return


def only_pdf_upload(doc, method):
    if doc.attached_to_doctype == "Top up Application":
        if doc.file_name.split(".")[-1].lower() != "pdf":
            frappe.throw("Kindly upload PDF files only.")
