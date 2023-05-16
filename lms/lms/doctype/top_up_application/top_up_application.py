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
        loan.available_topup_amt = loan.max_topup_amount()
        loan.save(ignore_permissions=True)
        frappe.db.commit()

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

    def on_update(self):
        if self.status == "Esign Done" and self.lender_esigned_document != None:
            return
        self.notify_customer()

        loan = self.get_loan()
        lender = self.get_lender()
        if self.status == "Approved":
            renewal_list = frappe.get_all(
                "Spark Loan Renewal Application",
                filters={
                    "loan": loan.name,
                    "status": ["Not IN", ["Approved", "Rejected"]],
                },
                fields=["name"],
            )
            for doc in renewal_list:
                renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc.name)
                renewal_doc.status = "Rejected"
                renewal_doc.workflow_state = "Rejected"
                renewal_doc.remarks = (
                    "Rejected due to Approval of Top-up/Increase Loan Application"
                )
                renewal_doc.save(ignore_permissions=True)
                frappe.db.commit()

    def before_submit(self):
        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        user_role = []
        loan = self.get_loan()
        for i in list(user_roles):
            user_role.append(i[0])
        if not self.lender_esigned_document:
            frappe.throw("Please upload Lender Esigned Document")

        updated_top_up_amt = loan.max_topup_amount()
        if (self.top_up_amount + loan.sanctioned_limit) > self.maximum_sanctioned_limit:
            frappe.throw(
                "Can not Approve this Top up Application as Sanctioned limit will cross Maximum Sanctioned limit Cap"
            )
        if not updated_top_up_amt or updated_top_up_amt < self.top_up_amount:
            frappe.throw("Top up not available")
        if self.top_up_amount <= 0:
            frappe.throw("Top up can not be approved with Amount Rs. 0")

    def get_lender(self):
        return frappe.get_doc("Lender", self.lender)

    def esign_request(self):
        customer = self.get_customer()
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        lender = self.get_lender()
        loan = self.get_loan()
        logo_file_path_1 = lender.get_lender_logo_file()
        logo_file_path_2 = lender.get_lender_address_file()
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
        if self.loan:
            wef_date = loan.wef_date
            if type(wef_date) is str:
                wef_date = datetime.strptime(str(wef_date), "%Y-%m-%d").date()
            if (wef_date == frappe.utils.now_datetime().date() and self.is_default) or (
                not loan.is_default and wef_date > frappe.utils.now_datetime().date()
            ):  # custom
                base_interest = int_config.base_interest
                rebate_interest = int_config.rebait_interest
            elif (
                loan.is_default == 0 and wef_date == frappe.utils.now_datetime().date()
            ):
                base_interest = loan.custom_base_interest
                rebate_interest = loan.custom_rebate_interest
            else:
                base_interest = loan.old_interest
                rebate_interest = loan.old_rebate_interest
        else:
            base_interest = int_config.base_interest
            rebate_interest = int_config.rebait_interest
        roi_ = round((base_interest * 12), 2)
        charges = lms.charges_for_apr(
            lender.name, lms.validate_rupees(float(self.top_up_amount))
        )
        annual_default_interest = lender.default_interest * 12
        interest_charges_in_amount = int((float(increased_sanction_limit))) * (
            roi_ / 100
        )
        interest_per_month = float(interest_charges_in_amount / 12)
        final_payment = float(interest_per_month) + (increased_sanction_limit)
        apr = lms.calculate_irr(
            name_=self.name,
            sanction_limit=float(increased_sanction_limit),
            interest_per_month=interest_per_month,
            final_payment=final_payment,
            charges=charges.get("total"),
        )

        doc = {
            "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
            "loan_account_number": self.name,
            "borrower_name": customer.full_name,
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
            "logo_file_path_1": logo_file_path_1.file_url if logo_file_path_1 else "",
            "logo_file_path_2": logo_file_path_2.file_url if logo_file_path_2 else "",
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
            "rebate_interest": rebate_interest,
            "default_interest": annual_default_interest,
            "penal_charges": lender.renewal_penal_interest
            if lender.renewal_penal_interest
            else "",
            "rebait_threshold": lender.rebait_threshold,
            "interest_charges_in_amount": frappe.utils.fmt_money(
                interest_charges_in_amount
            ),
            "interest_per_month": frappe.utils.fmt_money(interest_per_month),
            "final_payment": frappe.utils.fmt_money(final_payment),
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

        # from frappe.utils.pdf import get_pdf

        agreement_pdf = lms.get_pdf(agreement)

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
        loan = self.get_loan()
        customer = self.get_customer()
        doc = frappe.get_doc("User KYC", self.get_customer().choice_kyc).as_dict()
        doc["top_up_application"] = {
            "status": self.status,
            "loan": self.loan,
            "top_up_amount": self.top_up_amount,
        }
        attachments = ""
        if doc.get("top_up_application").get("status") == "Approved":
            self.map_loan_agreement_file(loan)
            attachments = self.create_attachment()
            loan_email_message = frappe.db.sql(
                "select message from `tabNotification` where name ='Top up Application Approved';"
            )[0][0]
            loan_email_message = loan_email_message.replace("fullname", doc.fullname)
            loan_email_message = loan_email_message.replace(
                "logo_file",
                frappe.utils.get_url("/assets/lms/mail_images/logo.png"),
            )
            loan_email_message = loan_email_message.replace(
                "fb_icon",
                frappe.utils.get_url("/assets/lms/mail_images/fb-icon.png"),
            )
            loan_email_message = loan_email_message.replace(
                "inst_icon",
                frappe.utils.get_url("/assets/lms/mail_images/inst-icon.png"),
            )
            loan_email_message = loan_email_message.replace(
                "lin_icon",
                frappe.utils.get_url("/assets/lms/mail_images/lin-icon.png"),
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                sender=None,
                subject="Top up Application",
                message=loan_email_message,
                attachments=attachments,
            )
        else:
            frappe.enqueue_doc(
                "Notification", "Top up Application", method="send", doc=doc
            )
        mess = ""
        loan = ""
        fcm_notification = {}
        if doc.get("top_up_application").get("status") == "Pending":
            mess = 'Dear Customer,\nCongratulations! Your Top Up application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement to avail the loan now. For any help on e-sign please view our tutorial videos or reach out to us under "Contact Us" on the app -Spark Loans'

            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Application for top-up accepted",
                fields=["*"],
            )

        if doc.get("top_up_application").get("status") == "Approved":
            # mess = frappe.get_doc(
            #     "Spark SMS Notification", "Loan account topped up"
            # ).message
            mess = "Dear Customer,\nCongratulations! Your loan account has been topped up. Please check the app for details. -Spark Loans"

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Loan account topped up", fields=["*"]
            )
            loan = self.loan

        if doc.get("top_up_application").get("status") == "Rejected":
            # mess = frappe.get_doc("Spark SMS Notification", "Top Up rejected").message
            mess = "Dear Customer,\nSorry! Your top up request could not be executed due to technical reasons. We regret the inconvenience caused.Please try again after sometime or reach out to us through 'Contact Us' on the app  -Spark Loans"

            fcm_notification = frappe.get_doc(
                "Spark Push Notification", "Top up rejected", fields=["*"]
            )
            loan = self.loan

        if mess:
            # lms.send_sms_notification(customer=self.get_customer,msg=mess)
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

        loan_agreement_file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": loan_agreement_file_name,
                "content": loan_agreement.get_content(),
                "attached_to_doctype": "Loan",
                "attached_to_name": loan.name,
                "attached_to_field": "loan_agreement",
                "folder": "Home",
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
        lender = self.get_lender()
        self.actual_drawing_power = loan.actual_drawing_power
        self.instrument_type = loan.instrument_type
        self.scheme_type = loan.scheme_type
        self.sanctioned_limit = loan.sanctioned_limit
        self.minimum_sanctioned_limit = lender.minimum_sanctioned_limit
        self.maximum_sanctioned_limit = lender.maximum_sanctioned_limit
        user_roles = frappe.db.get_values(
            "Has Role", {"parent": frappe.session.user, "parenttype": "User"}, ["role"]
        )
        if self.lender_esigned_document and self.status in ["Esign Done", "Approved"]:
            file_name = frappe.db.get_value(
                "File", {"file_url": self.lender_esigned_document}
            )
            file_ = frappe.get_doc("File", file_name)
            if file_.is_private:
                file_.is_private = 0
                file_.save(ignore_permissions=True)
                frappe.db.commit()
                file_.reload()
            self.lender_esigned_document = file_.file_url
        user_role = []
        for i in list(user_roles):
            user_role.append(i[0])
        if "Loan Customer" not in user_role:
            updated_top_up_amt = loan.max_topup_amount()
            self.customer = loan.customer
            self.customer_name = loan.customer_name
            pending_loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "customer": self.customer,
                    "status": ["Not IN", ["Approved", "Rejected"]],
                },
                fields=["name"],
            )
            if pending_loan_application:
                pending_loan_app_link = """ <a target="_blank" rel="noreferrer noopener" href="/app/loan-application/{pending_loan_application}">{pending_loan_application}</a>""".format(
                    pending_loan_application=pending_loan_application[0].name
                )
                frappe.throw(
                    """Please approve/reject<br />\u2022 Loan Application {}""".format(
                        pending_loan_app_link
                    )
                )
            if (
                not updated_top_up_amt or updated_top_up_amt < self.top_up_amount
            ) and not self.status == "Rejected":
                frappe.throw("Top up not available")
            if self.top_up_amount <= 0 and not self.status == "Rejected":
                frappe.throw("Top up can not be approved with Amount Rs. 0")
        if self.status == "Approved":
            current = frappe.utils.now_datetime()
            expiry = frappe.utils.add_years(current, 1) - timedelta(days=1)
            self.expiry_date = datetime.strftime(expiry, "%Y-%m-%d")
        if self.status == "Pending":
            self.sanction_letter()

    def sanction_letter(self):
        try:
            customer = self.get_customer()
            user = frappe.get_doc("User", customer.user)
            user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
            lender = self.get_lender()
            loan = self.get_loan()
            logo_file_path_1 = lender.get_lender_logo_file()
            logo_file_path_2 = lender.get_lender_address_file()
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
            if self.loan:
                wef_date = loan.wef_date
                if type(wef_date) is str:
                    wef_date = datetime.strptime(str(wef_date), "%Y-%m-%d").date()
                if (
                    wef_date == frappe.utils.now_datetime().date() and self.is_default
                ) or (
                    not loan.is_default
                    and wef_date > frappe.utils.now_datetime().date()
                ):  # custom
                    base_interest = int_config.base_interest
                    rebate_interest = int_config.rebait_interest
                elif (
                    loan.is_default == 0
                    and wef_date == frappe.utils.now_datetime().date()
                ):
                    base_interest = loan.custom_base_interest
                    rebate_interest = loan.custom_rebate_interest
                else:
                    base_interest = loan.old_interest
                    rebate_interest = loan.old_rebate_interest
            else:
                base_interest = int_config.base_interest
                rebate_interest = int_config.rebait_interest
            roi_ = round((base_interest * 12), 2)
            charges = lms.charges_for_apr(
                lender.name, lms.validate_rupees(float(self.top_up_amount))
            )
            annual_default_interest = lender.default_interest * 12
            interest_charges_in_amount = int(
                lms.validate_rupees(float(increased_sanction_limit))
            ) * (roi_ / 100)
            interest_per_month = float(interest_charges_in_amount / 12)
            final_payment = float(interest_per_month) + (increased_sanction_limit)
            apr = lms.calculate_irr(
                name_=self.name,
                sanction_limit=float(increased_sanction_limit),
                interest_per_month=interest_per_month,
                final_payment=final_payment,
                charges=charges.get("total"),
            )

            doc = {
                "esign_date": "",
                "loan_account_no": loan.name if self.loan else "",
                "loan_account_number": loan.name if self.loan else "",
                "borrower_name": customer.full_name,
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
                "logo_file_path_1": logo_file_path_1.file_url
                if logo_file_path_1
                else "",
                "logo_file_path_2": logo_file_path_2.file_url
                if logo_file_path_2
                else "",
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
                "rebate_interest": rebate_interest,
                "default_interest": annual_default_interest,
                "penal_charges": lender.renewal_penal_interest
                if lender.renewal_penal_interest
                else "",
                "rebait_threshold": lender.rebait_threshold,
                "interest_charges_in_amount": frappe.utils.fmt_money(
                    interest_charges_in_amount
                ),
                "interest_per_month": frappe.utils.fmt_money(interest_per_month),
                "final_payment": frappe.utils.fmt_money(final_payment),
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
                "documentation_charge": lms.validate_rupees(
                    lender.documentation_charges
                )
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
                "lien_initiate_charges": lms.validate_rupees(
                    lender.lien_initiate_charges
                )
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

            s_letter = frappe.render_template(
                sanction_letter_template.get_content(), {"doc": doc}
            )

            pdf_file = open(sanctioned_leter_pdf_file_path, "wb")

            # from frappe.utils.pdf import get_pdf

            pdf = lms.get_pdf(s_letter)

            pdf_file.write(pdf)
            pdf_file.close()
            sL_letter = frappe.utils.get_url(
                "files/{}".format(sanctioned_letter_pdf_file)
            )
            sl = frappe.get_all(
                "Sanction Letter and CIAL Log",
                filters={"loan": self.loan},
                fields=["*"],
            )
            if not self.sl_entries:
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

            if self.status == "Approved":
                import os

                from PyPDF2 import PdfReader, PdfWriter

                lender_esign_file = self.lender_esigned_document
                lfile_name = lender_esign_file.split("files/", 1)
                l_file = lfile_name[1]
                pdf_file_path = frappe.utils.get_files_path(
                    l_file,
                )
                file_base_name = pdf_file_path.replace(".pdf", "")
                pdf = PdfReader(pdf_file_path)
                pages = [
                    23,
                    24,
                    25,
                    26,
                    27,
                    28,
                    29,
                    30,
                ]  # page 1, 3, 5
                pdfWriter = PdfWriter()
                for page_num in pages:
                    pdfWriter.addPage(pdf.getPage(page_num))
                sanction_letter_esign = "Sanction_letter_{0}.pdf".format(self.name)
                sanction_letter_esign_path = frappe.utils.get_files_path(
                    sanction_letter_esign
                )
                if os.path.exists(sanction_letter_esign_path):
                    os.remove(sanction_letter_esign_path)
                sanction_letter_esign_document = frappe.utils.get_url(
                    "files/{}".format(sanction_letter_esign)
                )
                sanction_letter_esign = frappe.utils.get_files_path(
                    sanction_letter_esign
                )

                with open(sanction_letter_esign, "wb") as f:
                    pdfWriter.write(f)
                    f.close()
                sl = frappe.get_all(
                    "Sanction Letter Entries",
                    filters={"topup_application_no": self.name},
                    fields=["*"],
                )
                sll = frappe.get_doc("Sanction Letter Entries", sl[0].name)
                sll.sanction_letter = sanction_letter_esign_document
                sll.save()
                frappe.db.commit()

            return
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nTop up Application : {}".format(self.name),
                title=(("Sanction Letter failed in Topup application")),
            )

    def create_attachment(self):
        try:
            attachments = []
            doc_name = self.lender_esigned_document
            fname = doc_name.split("files/", 1)
            file = fname[1].split(".", 1)
            file_name = file[0]
            log_file = frappe.utils.get_files_path("{}.pdf".format(file_name))
            with open(log_file, "rb") as fileobj:
                filedata = fileobj.read()

            sanction_letter = {"fname": fname[1], "fcontent": filedata}
            attachments.append(sanction_letter)
            return attachments

        except Exception:
            frappe.log_error(
                message=frappe.get_traceback()
                + "\nTop up Application : {}".format(self.name),
                title=(_("Create attachment failed in Topup application")),
            )


def only_pdf_upload(doc, method):
    if doc.attached_to_doctype == "Top up Application":
        if doc.file_name.split(".")[-1].lower() != "pdf":
            frappe.throw("Kindly upload PDF files only.")
