# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import datetime, time, timedelta

import frappe
import pandas as pd
from frappe import _
from frappe.model.document import Document

import lms
from lms import send_spark_push_notification
from lms.lms.doctype.user_token.user_token import send_sms


class SparkLoanRenewalApplication(Document):
    def before_save(self):
        las_settings = frappe.get_single("LAS Settings")
        loan = frappe.get_doc("Loan", self.loan)
        msg = ""
        current_year = int(frappe.utils.now_datetime().strftime("%Y"))
        if (
            (current_year % 400 == 0)
            or (current_year % 100 != 0)
            and (current_year % 4 == 0)
        ):
            no_of_days = 365
        # Else it is not a leap year
        else:
            no_of_days = 364

        if (
            self.status == "Approved"
            and not self.expiry_date
            and not self.lender_esigned_document
        ):
            frappe.throw(_("Please upload Lender esigned document."))

        if self.status == "Rejected" and not self.remarks:
            frappe.throw(_("Remarks field cannot be empty."))
        try:
            loan = frappe.get_doc("Loan", self.loan)
            customer = frappe.get_doc("Loan Customer", self.customer)

            doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            doc["loan_renewal_application"] = {
                "status": self.status,
                "lr_accepted_by_lender": self.lr_accepted_by_lender,
            }

            if self.status in [
                "Loan Renewal accepted by Lender",
                "Esign Done",
                "Approved",
                "Rejected",
            ]:
                frappe.enqueue_doc(
                    "Notification", "Loan Renewal Application", method="send", doc=doc
                )

            if (
                self.status == "Loan Renewal accepted by Lender"
                and not self.lr_accepted_by_lender
            ):
                self.lr_accepted_by_lender = 1
                msg = """Dear Customer,
Congratulations! Your loan renewal application has been accepted. Kindly check the app for details under e-sign banner on the dashboard. Please e-sign the loan agreement. For any help on e-sign, please view our tutorial videos or reach out to us under "Contact Us" on the app - {link} - Spark Loans""".format(
                    link=las_settings.contact_us
                )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal accepted",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )

            elif self.status == "Esign Done" and self.lender_esigned_document == None:
                msg = """Dear Customer,
Your E-sign process is completed. You shall soon receive a confirmation of loan renew approval. Thank you for your patience. - Spark Loans"""

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal E-signing was successful",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )

            elif self.status == "Approved":
                lender = frappe.get_doc("Lender", self.lender)
                loan_renewal_charges = lender.renewal_charges
                if lender.renewal_charge_type == "Percentage":
                    amount = (loan_renewal_charges / 100) * self.drawing_power
                    loan_renewal_charges = loan.validate_loan_charges_amount(
                        lender,
                        amount,
                        "renewal_minimum_amount",
                        "renewal_maximum_amount",
                    )
                loan.create_loan_transaction(
                    transaction_type="Account Renewal Charges",
                    amount=loan_renewal_charges,
                    approve=True,
                )

                self.expiry_date = loan.expiry_date + timedelta(days=no_of_days)
                loan.expiry_date = loan.expiry_date + timedelta(days=no_of_days)
                loan.save(ignore_permissions=True)
                frappe.db.commit()
                frappe.log_error(
                    message="Loan name :{}".format(str(loan))
                    + "\nLoan Document:{}".format(str(loan.expiry_date)),
                    title=_("before_save_renewal_doc_for_selected_customer"),
                )
                msg = """Dear Customer,
                Congratulations! Your loan renewal process is completed. Please visit the spark.loans app for details  - {link} -Spark Loans
                """.format(
                    link=las_settings.app_login_dashboard
                )

                fcm_notification = frappe.get_doc(
                    "Spark Push Notification",
                    "Loan Renewal approved",
                    fields=["*"],
                )
                send_spark_push_notification(
                    fcm_notification=fcm_notification,
                    loan=loan.name,
                    customer=customer,
                )

            elif self.status == "Rejected":
                if (
                    self.lr_accepted_by_lender == 1
                    and not self.customer_esigned_document
                ):
                    msg = """Dear Customer,
Your loan renew application was turned down, as per your request. Please try again or you can reach to us through 'Contact Us' on the app- ({link})-Spark Loans""".format(
                        link=las_settings.contact_us
                    )

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal rejected(in accepted by lender state)",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )

                else:
                    msg = """Dear Customer,
Sorry! Your loan renewal application was turned down. We regret the inconvenience caused. Please try again after sometime or reach out to us through 'Contact Us' on the app  - {link}- Spark Loans""".format(
                        link=las_settings.contact_us
                    )

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal rejected",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )

                existing_renewal_doc = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={
                        "name": ["!=", self.name],
                        "loan": loan.name,
                        "status": ["not IN", ["Approved", "Rejected"]],
                    },
                    fields=["name"],
                )
                if (
                    loan.expiry_date > frappe.utils.now_datetime().date()
                    and not existing_renewal_doc
                    and self.remarks
                    != "Rejected due to Approval of Top-up/Increase Loan Application"
                ):
                    self.tnc_complete = 0
                    self.updated_kyc_status = ""
                    if self.new_kyc_name:
                        kyc_doc = frappe.get_doc("User KYC", self.new_kyc_name)
                        kyc_doc.updated_kyc = 0
                        kyc_doc.save(ignore_permissions=True)
                    frappe.get_doc(
                        dict(
                            doctype="Spark Loan Renewal Application",
                            loan=loan.name,
                            lender=loan.lender,
                            old_kyc_name=customer.choice_kyc,
                            total_collateral_value=loan.total_collateral_value,
                            sanctioned_limit=loan.sanctioned_limit,
                            drawing_power=loan.drawing_power,
                            customer=customer.name,
                            customer_name=customer.full_name,
                        )
                    ).insert(ignore_permissions=True)
                    frappe.db.commit()
                if loan.expiry_date < frappe.utils.now_datetime().date():
                    renewal_list_expiring = frappe.get_all(
                        "Spark Loan Renewal Application",
                        filters={"loan": loan.name},
                        fields=["*"],
                    )
                    status_list = [i["status"] for i in renewal_list_expiring]
                    if status_list.count("Rejected") >= 2 and loan.name not in [
                        "SL000130",
                        "SL000133",
                        "SL000134",
                    ]:
                        self.is_expired = 1

                    if status_list.count("Rejected") >= 2 and loan.name in [
                        "SL000130",
                        "SL000133",
                        "SL000134",
                    ]:
                        if (
                            self.creation.date()
                            < frappe.utils.now_datetime().date() + timedelta(days=7)
                        ):
                            self.is_expired = 1

            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(method=send_sms, receiver_list=receiver_list, msg=msg)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=_("Loan Renewal Application - Customer Notification "),
            )

    def esign_request(self):
        customer = frappe.get_doc("Loan Customer", self.customer)
        user = frappe.get_doc("User", customer.user)
        user_kyc = frappe.get_doc("User KYC", customer.choice_kyc)
        loan = frappe.get_doc("Loan Customer", self.loan)
        lender = frappe.get_doc("Loan Customer", loan.lender)

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

        doc = {
            "esign_date": frappe.utils.now_datetime().strftime("%d-%m-%Y"),
            "loan_application_number": self.name,
            "borrower_name": user_kyc.fullname,
            "borrower_address": address,
            # "sanctioned_amount": self.top_up_amount,
            # "sanctioned_amount_in_words": num2words(
            #     self.top_up_amount, lang="en_IN"
            # ).title(),
            "sanctioned_amount": lms.validate_rupees(loan.sanctioned_limit),
            "sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees(loan.sanctioned_limit)
            ).title(),
            "old_sanctioned_amount": lms.validate_rupees(loan.sanctioned_limit),
            "old_sanctioned_amount_in_words": lms.number_to_word(
                lms.validate_rupees(loan.sanctioned_limit)
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


@frappe.whitelist()
def customer_reminder(doc_name):
    try:
        las_settings = frappe.get_single("LAS Settings")
        renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc_name)
        loan = frappe.get_doc("Loan", renewal_doc.loan)
        try:
            customer = frappe.get_doc("Loan Customer", renewal_doc.customer)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(_("Loan Customer {} not found".format(renewal_doc.customer))),
            )
        doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
        doc["loan_renewal_application"] = {"status": renewal_doc.status}

        if renewal_doc.status == "Pending":
            kyc_doc = frappe.get_doc("User KYC", customer.choice_kyc).as_dict()
            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Reminder';"
            )[0][0]
            exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").strftime(
                "%d-%m-%Y"
            )
            expiry = exp.replace("-", "/")
            email_expiry = email_expiry.replace("loan_name", str(loan.name))
            email_expiry = email_expiry.replace("expiry_date", str(expiry))
            email_expiry = email_expiry.replace(
                "dlt_link", las_settings.app_login_dashboard
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                sender=None,
                subject="Loan Renewal Reminder",
                message=email_expiry,
                queue="short",
                delayed=False,
                job_name="Loan Renewal Reminder",
            )
            msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans
""".format(
                loan_name=renewal_doc.loan,
                expiry_date=loan.expiry_date,
                link=las_settings.app_login_dashboard,
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal Reminder",
                fields=["*"],
            )
            send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=loan.name,
                customer=customer,
            )
            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))

                frappe.enqueue(
                    method=send_sms,
                    receiver_list=receiver_list,
                    msg=msg,
                )
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application - Notify Customer"),
        )


@frappe.whitelist()
def all_loans_renewal_update_doc():
    try:
        # Renewal Doc creation and 1st reminder
        loans = frappe.get_all("Loan", fields=["name"])
        for loan_name in loans:
            frappe.enqueue(
                method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.loan_renewal_update_doc",
                queue="long",
                loan_name=loan_name,
                job_name="{}-Loan Renewal Update Doc".format(loan_name),
            )
            frappe.enqueue(
                method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_penal_interest",
                queue="long",
                loan_name=loan_name,
                job_name="{}-Renewal Penal Interest".format(loan_name),
            )
        frappe.enqueue(
            method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_timer",
            queue="long",
            job_name="Renewal Timer",
        )
        frappe.enqueue(
            method="lms.lms.doctype.spark_loan_renewal_application.spark_loan_renewal_application.renewal_doc_for_selected_customer",
            queue="long",
            job_name="Renewal doc for Selected Customer",
        )

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("All Loans Renewal Update Doc Error"),
        )


@frappe.whitelist()
def renewal_penal_interest(loan_name):
    try:
        loan = frappe.get_doc("Loan", loan_name)
        existing_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={
                "loan": loan.name,
                "status": ["not IN", ["Rejected", "Pending"]],
            },
            fields=["*"],
        )
        pending_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )
        try:
            customer = frappe.get_doc("Loan Customer", loan.customer)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(_("Loan Customer {} not found".format(loan.customer))),
            )
        user_kyc = frappe.get_all(
            "User KYC",
            filters={
                "user": customer.user,
                "updated_kyc": 1,
                "kyc_status": "Pending",
            },
            fields=["*"],
        )
        user_kyc_approved = frappe.get_all(
            "User KYC",
            filters={
                "user": customer.user,
                "updated_kyc": 1,
                "kyc_status": "Approved",
            },
            fields=["*"],
        )
        applications = []

        current_date = frappe.utils.now_datetime().date()
        exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
        greater_than_7 = exp + timedelta(days=7)
        more_than_7 = greater_than_7 + timedelta(days=7)
        if (
            greater_than_7 > current_date or more_than_7 > current_date
        ) and exp < current_date:
            if (
                pending_renewal_doc_list and not user_kyc and not user_kyc_approved
            ) or (user_kyc_approved and pending_renewal_doc_list):
                top_up_application = frappe.get_all(
                    "Top up Application",
                    filters={
                        "loan": loan.name,
                        "status": ["IN", ["Pending", "Esign Done"]],
                    },
                    fields=["name"],
                )
                for i in top_up_application:
                    applications.append(i)
                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": loan.name,
                        "application_type": [
                            "IN",
                            ["Increase Loan", "Pledge More", "Margin Shortfall"],
                        ],
                    },
                    fields=["name"],
                )
                for i in loan_application:
                    applications.append(i)
                if not top_up_application:
                    if not loan_application:
                        current_year = frappe.utils.now_datetime().strftime("%Y")
                        current_year = int(current_year)
                        if (
                            (current_year % 400 == 0)
                            or (current_year % 100 != 0)
                            and (current_year % 4 == 0)
                        ):
                            no_of_days = 366
                        # Else it is not a leap year
                        else:
                            no_of_days = 365
                        renewal_penal_interest = frappe.get_doc("Lender", loan.lender)
                        daily_penal_interest = (
                            float(renewal_penal_interest.renewal_penal_interest)
                            / no_of_days
                        )
                        amount = loan.balance * (daily_penal_interest / 100)
                        penal_interest_transaction = frappe.get_doc(
                            {
                                "doctype": "Loan Transaction",
                                "loan": loan.name,
                                "lender": loan.lender,
                                "transaction_type": "Penal Interest",
                                "record_type": "DR",
                                "amount": round(amount, 2),
                                "unpaid_interest": round(amount, 2),
                                "time": current_date,
                            }
                        )
                        penal_interest_transaction.insert(ignore_permissions=True)
                        penal_interest_transaction.transaction_id = (
                            penal_interest_transaction.name
                        )
                        penal_interest_transaction.status = "Approved"
                        penal_interest_transaction.workflow_state = "Approved"
                        penal_interest_transaction.docstatus = 1
                        penal_interest_transaction.save(ignore_permissions=True)
                        frappe.db.commit()

        pending_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )
        is_expired_date = exp + timedelta(days=7)
        if pending_renewal_doc_list:
            for renewal_doc in pending_renewal_doc_list:
                doc = frappe.get_doc("Spark Loan Renewal Application", renewal_doc.name)
                if (
                    not user_kyc
                    and not user_kyc_approved
                    and is_expired_date < frappe.utils.now_datetime().date()
                ) or (
                    user_kyc_approved
                    and not user_kyc
                    and is_expired_date < frappe.utils.now_datetime().date()
                    and (is_expired_date + timedelta(days=7))
                    > frappe.utils.now_datetime().date()
                    and doc.status == "Pending"
                ):
                    doc.status = "Rejected"
                    doc.workflow_state = "Rejected"
                    doc.remarks = "Is Expired"
                if (
                    doc.new_kyc_name
                    and doc.kyc_approval_date
                    and frappe.utils.now_datetime() > doc.kyc_approval_date
                    and doc.tnc_show == 0
                    and (is_expired_date + timedelta(days=7))
                    < frappe.utils.now_datetime().date()
                ):
                    doc.tnc_show = 1
                doc.save(ignore_permissions=True)
                frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Penal Interest Error"),
        )


@frappe.whitelist()
def renewal_timer(loan_renewal_name=None):
    try:
        if loan_renewal_name:
            renewal_doc = frappe.get_doc(
                "Spark Loan Renewal Application", loan_renewal_name
            )
            loan = frappe.get_doc("Loan", renewal_doc.loan)
            try:
                customer = frappe.get_doc("Loan Customer", loan.customer)
            except Exception as e:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=(_("Loan Customer {} not found".format(loan.customer))),
                )
            if type(loan.expiry_date) is str:
                exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
            else:
                exp = loan.expiry_date
            loan_expiry = datetime.combine(exp, time.min)

            user_kyc = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                },
                fields=["*"],
            )
            user_kyc_pending = frappe.get_all(
                "User KYC",
                filters={
                    "user": customer.user,
                    "updated_kyc": 1,
                    "kyc_status": "Pending",
                },
                fields=["*"],
            )
            top_up_application = frappe.get_all(
                "Top up Application",
                filters={"loan": loan.name, "status": "Pending"},
                fields=["name"],
            )

            loan_application = frappe.get_all(
                "Loan Application",
                filters={
                    "loan": loan.name,
                    "application_type": [
                        "IN",
                        ["Increase Loan", "Pledge More", "Margin Shortfall"],
                    ],
                    "status": ["not IN", ["Approved", "Rejected"]],
                },
                fields=["name"],
            )
            if top_up_application or loan_application:
                action_status = "Pending"
            else:
                action_status = ""
            frappe.db.set_value(
                "Spark Loan Renewal Application",
                renewal_doc.name,
                "action_status",
                action_status,
                update_modified=False,
            )
            date_7after_expiry = loan_expiry + timedelta(days=8)
            if (
                frappe.utils.now_datetime().date() > exp
                and frappe.utils.now_datetime().date() <= (exp + timedelta(days=7))
                and renewal_doc.status not in ["Approved", "Rejected"]
                and loan.name not in ["SL000130", "SL000133", "SL000134"]
            ):
                seconds = abs(
                    date_7after_expiry - frappe.utils.now_datetime()
                ).total_seconds()
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)

            elif (
                frappe.utils.now_datetime().date() > renewal_doc.creation.date()
                and frappe.utils.now_datetime().date()
                <= (renewal_doc.creation.date() + timedelta(days=7))
                and renewal_doc.status not in ["Approved", "Rejected"]
                and loan.name in ["SL000130", "SL000133", "SL000134"]
            ):
                date_7after_expiry = renewal_doc.creation.date() + timedelta(days=14)
                seconds = abs(
                    date_7after_expiry - frappe.utils.now_datetime()
                ).total_seconds()
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)

            elif (
                frappe.utils.now_datetime().date() > (exp + timedelta(days=7))
                and frappe.utils.now_datetime().date() <= (exp + timedelta(days=14))
                and user_kyc_pending
            ):
                seconds = abs(
                    (date_7after_expiry + timedelta(days=7))
                    - frappe.utils.now_datetime()
                ).total_seconds()
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)

            else:
                seconds = 0
                renewal_timer = lms.convert_sec_to_hh_mm_ss(seconds, is_for_days=True)
            frappe.db.set_value(
                "Spark Loan Renewal Application",
                renewal_doc.name,
                "time_remaining",
                renewal_timer,
                update_modified=False,
            )

        else:
            loans = frappe.get_all("Loan", fields=["*"])
            for loan in loans:
                try:
                    customer = frappe.get_doc("Loan Customer", loan.customer)
                except Exception as e:
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=(_("Loan Customer {} not found".format(loan.customer))),
                    )
                user_kyc = frappe.get_all(
                    "User KYC",
                    filters={
                        "user": customer.user,
                        "updated_kyc": 1,
                    },
                    fields=["*"],
                )
                top_up_application = frappe.get_all(
                    "Top up Application",
                    filters={"loan": loan.name, "status": "Pending"},
                    fields=["name"],
                )

                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": loan.name,
                        "application_type": [
                            "IN",
                            ["Increase Loan", "Pledge More", "Margin Shortfall"],
                        ],
                    },
                    fields=["name"],
                )

                renewal_doc_list = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={
                        "loan": loan.name,
                        "status": ["NOT IN", ["Approved", "Rejected"]],
                    },
                    fields=["*"],
                )
                if top_up_application or loan_application and renewal_doc_list:
                    action_status = "Pending"
                else:
                    action_status = ""

                if renewal_doc_list:
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application", renewal_doc_list[0].name
                    )

                    frappe.db.set_value(
                        "Spark Loan Renewal Application",
                        renewal_doc.name,
                        "action_status",
                        action_status,
                        update_modified=False,
                    )

                user_kyc_pending = frappe.get_all(
                    "User KYC",
                    filters={
                        "user": customer.user,
                        "updated_kyc": 1,
                        "kyc_status": "Pending",
                    },
                    fields=["*"],
                )
                renewal_doc_pending_list = frappe.get_all(
                    "Spark Loan Renewal Application",
                    filters={"loan": loan.name, "status": "Pending"},
                    fields=["*"],
                )

                if type(loan.expiry_date) is str:
                    exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
                else:
                    exp = loan.expiry_date

                loan_expiry = datetime.combine(exp, time.min)
                date_7after_expiry = loan_expiry + timedelta(days=8)

                if (
                    frappe.utils.now_datetime().date() > loan.expiry_date
                    and frappe.utils.now_datetime().date()
                    <= (loan.expiry_date + timedelta(days=7))
                    and renewal_doc_list
                ):
                    seconds = abs(
                        date_7after_expiry - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )

                    frappe.db.set_value(
                        "Spark Loan Renewal Application",
                        renewal_doc.name,
                        "time_remaining",
                        renewal_timer,
                        update_modified=False,
                    )

                elif (
                    frappe.utils.now_datetime().date()
                    > (loan.expiry_date + timedelta(days=7))
                    and frappe.utils.now_datetime().date()
                    <= (loan.expiry_date + timedelta(days=14))
                    and user_kyc_pending
                    and renewal_doc_pending_list
                ):
                    seconds = abs(
                        (date_7after_expiry + timedelta(days=7))
                        - frappe.utils.now_datetime()
                    ).total_seconds()
                    renewal_timer = lms.convert_sec_to_hh_mm_ss(
                        seconds, is_for_days=True
                    )
                    renewal_doc = frappe.get_doc(
                        "Spark Loan Renewal Application",
                        renewal_doc_pending_list[0].name,
                    )

                    frappe.db.set_value(
                        "Spark Loan Renewal Application",
                        renewal_doc.name,
                        "time_remaining",
                        renewal_timer,
                        update_modified=False,
                    )

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application  - Timer Function"),
        )


def loan_renewal_update_doc(loan_name):
    try:
        loan = frappe.get_doc("Loan", loan_name)
        las_settings = frappe.get_single("LAS Settings")
        str_exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").strftime(
            "%d/%m/%Y"
        )
        renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": ["!=", "Rejected"]},
            fields=["name"],
        )

        for i in renewal_doc_list:
            doc = frappe.get_doc("Spark Loan Renewal Application", i.name)
            exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").date()
            if (
                exp < frappe.utils.now_datetime().date()
                and doc.is_expired == 0
                and loan.name not in ["SL000130", "SL000133", "SL000134"]
            ):
                doc.is_expired = 1
                doc.save(ignore_permissions=True)
                frappe.db.commit()

            if (
                doc.creation.date()
                < frappe.utils.now_datetime().date() + timedelta(days=7)
                and doc.is_expired == 0
                and loan.name in ["SL000130", "SL000133", "SL000134"]
            ):
                doc.is_expired = 1
                doc.save(ignore_permissions=True)
                frappe.db.commit()

        existing_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )

        try:
            customer = frappe.get_doc("Loan Customer", loan.customer)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(_("Loan Customer {} not found".format(loan.customer))),
            )
        user_kyc = frappe.get_all(
            "User KYC",
            filters={
                "user": customer.user,
                "updated_kyc": 1,
                "kyc_status": ["in", ["Pending", "Approved"]],
            },
            fields=["name"],
        )

        expiry_date = frappe.utils.now_datetime().date() + timedelta(days=29)
        if type(loan.expiry_date) == str:
            exp = datetime.strptime(loan.expiry_date, "%Y-%m-%d").date()
        else:
            exp = loan.expiry_date

        if (
            existing_renewal_doc_list
            and exp < frappe.utils.now_datetime().date()
            and frappe.utils.now_datetime().date() < exp + timedelta(days=2)
        ) or (
            existing_renewal_doc_list
            and user_kyc
            and (exp + timedelta(days=7)) < frappe.utils.now_datetime().date()
            and frappe.utils.now_datetime().date() < exp + timedelta(days=9)
        ):
            if frappe.utils.now_datetime().date() < exp + timedelta(days=2):
                expiry = exp
            else:
                expiry = exp + timedelta(days=7)

            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Extension';"
            )[0][0]
            email_expiry = email_expiry.replace("loan_name", loan.name)
            email_expiry = email_expiry.replace("expiry_date", str_exp)
            email_expiry = email_expiry.replace(
                "dlt_link", las_settings.app_login_dashboard
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                subject="Loan Renewal Extension",
                message=email_expiry,
                queue="short",
                job_name="Loan Renewal Extension",
            )
            msg = """Dear Customer,
You have received a loan renewal extension of 7 days from the current expiry date: {expiry_date}. Click here to continue {link} - Spark Loan""".format(
                expiry_date=str_exp,
                link=las_settings.app_login_dashboard,
            )

            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal Extension",
                fields=["*"],
            )
            send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=loan.name,
                customer=customer,
            )
            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))
                frappe.enqueue(
                    method=send_sms,
                    receiver_list=receiver_list,
                    msg=msg,
                )

        if (
            exp == expiry_date
            and loan.total_collateral_value > 0
            and len(loan.items) > 0
        ):
            renewal_doc = frappe.get_doc(
                dict(
                    doctype="Spark Loan Renewal Application",
                    loan=loan.name,
                    lender=loan.lender,
                    old_kyc_name=customer.choice_kyc,
                    total_collateral_value=loan.total_collateral_value,
                    sanctioned_limit=loan.sanctioned_limit,
                    drawing_power=loan.drawing_power,
                    customer=customer.name,
                    customer_name=customer.full_name,
                    remarks="",
                )
            ).insert(ignore_permissions=True)
            frappe.db.commit()
            email_expiry = frappe.db.sql(
                "select message from `tabNotification` where name='Loan Renewal Reminder';"
            )[0][0]
            email_expiry = email_expiry.replace("loan_name", str(loan.name))
            email_expiry = email_expiry.replace("expiry_date", str_exp)
            email_expiry = email_expiry.replace(
                "dlt_link", str(las_settings.app_login_dashboard)
            )
            frappe.enqueue(
                method=frappe.sendmail,
                recipients=[customer.user],
                subject="Loan Renewal Reminder",
                message=email_expiry,
                queue="short",
                job_name="Loan Renewal Reminder",
            )
            msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                loan_name=loan.name,
                expiry_date=str_exp,
                link=las_settings.app_login_dashboard,
            )
            fcm_notification = frappe.get_doc(
                "Spark Push Notification",
                "Loan Renewal Reminder",
                fields=["*"],
            )
            send_spark_push_notification(
                fcm_notification=fcm_notification,
                loan=loan.name,
                customer=customer,
            )
            if msg:
                receiver_list = [str(customer.phone)]
                if customer.get_kyc().mob_num:
                    receiver_list.append(str(customer.get_kyc().mob_num))
                if customer.get_kyc().choice_mob_no:
                    receiver_list.append(str(customer.get_kyc().choice_mob_no))

                receiver_list = list(set(receiver_list))
                frappe.enqueue(
                    method=send_sms,
                    receiver_list=receiver_list,
                    msg=msg,
                )

            renewal_doc.reminders = 1
            renewal_doc.save(ignore_permissions=True)
            frappe.db.commit()

        elif exp == frappe.utils.now_datetime().date() + timedelta(days=19):
            for doc in existing_renewal_doc_list:
                renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc.name)
                if doc.reminders == 1:
                    email_expiry = frappe.db.sql(
                        "select message from `tabNotification` where name='Loan Renewal Reminder';"
                    )[0][0]
                    email_expiry = email_expiry.replace("loan_name", str(loan.name))
                    email_expiry = email_expiry.replace("expiry_date", str_exp)
                    email_expiry = email_expiry.replace(
                        "dlt_link", str(las_settings.app_login_dashboard)
                    )
                    frappe.enqueue(
                        method=frappe.sendmail,
                        recipients=[customer.user],
                        sender=None,
                        subject="Loan Renewal Reminder",
                        message=email_expiry,
                        queue="short",
                        delayed=False,
                        job_name="Loan Renewal Reminder",
                    )
                    msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                        loan_name=loan.name,
                        expiry_date=str_exp,
                        link=las_settings.app_login_dashboard,
                    )
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal Reminder",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )
                    if msg:
                        receiver_list = [str(customer.phone)]
                        if customer.get_kyc().mob_num:
                            receiver_list.append(str(customer.get_kyc().mob_num))
                        if customer.get_kyc().choice_mob_no:
                            receiver_list.append(str(customer.get_kyc().choice_mob_no))

                        receiver_list = list(set(receiver_list))

                        frappe.enqueue(
                            method=send_sms,
                            receiver_list=receiver_list,
                            msg=msg,
                        )

                    renewal_doc.reminders = 2
                    renewal_doc.save(ignore_permissions=True)
                    frappe.db.commit()

        elif exp == frappe.utils.now_datetime().date() + timedelta(days=9):
            for doc in existing_renewal_doc_list:
                renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc.name)
                if doc.reminders == 2:
                    email_expiry = frappe.db.sql(
                        "select message from `tabNotification` where name='Loan Renewal Reminder';"
                    )[0][0]
                    email_expiry = email_expiry.replace("loan_name", str(loan.name))
                    email_expiry = email_expiry.replace("expiry_date", str_exp)
                    email_expiry = email_expiry.replace(
                        "dlt_link", str(las_settings.app_login_dashboard)
                    )
                    frappe.enqueue(
                        method=frappe.sendmail,
                        recipients=[customer.user],
                        sender=None,
                        subject="Loan Renewal Reminder",
                        message=email_expiry,
                        queue="short",
                        delayed=False,
                        job_name="Loan Renewal Reminder",
                    )
                    msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                        loan_name=loan.name,
                        expiry_date=str_exp,
                        link=las_settings.app_login_dashboard,
                    )
                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal Reminder",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )
                    if msg:
                        receiver_list = [str(customer.phone)]
                        if customer.get_kyc().mob_num:
                            receiver_list.append(str(customer.get_kyc().mob_num))
                        if customer.get_kyc().choice_mob_no:
                            receiver_list.append(str(customer.get_kyc().choice_mob_no))

                        receiver_list = list(set(receiver_list))

                        frappe.enqueue(
                            method=send_sms,
                            receiver_list=receiver_list,
                            msg=msg,
                        )

                    renewal_doc.reminders = 3
                    renewal_doc.save(ignore_permissions=True)
                    frappe.db.commit()

        elif exp == frappe.utils.now_datetime().date() + timedelta(days=2):
            for doc in existing_renewal_doc_list:
                renewal_doc = frappe.get_doc("Spark Loan Renewal Application", doc.name)
                if doc.reminders == 3:
                    email_expiry = frappe.db.sql(
                        "select message from `tabNotification` where name='Loan Renewal Reminder';"
                    )[0][0]
                    email_expiry = email_expiry.replace("loan_name", str(loan.name))
                    email_expiry = email_expiry.replace("expiry_date", str_exp)
                    email_expiry = email_expiry.replace(
                        "dlt_link", str(las_settings.app_login_dashboard)
                    )
                    frappe.enqueue(
                        method=frappe.sendmail,
                        recipients=[customer.user],
                        sender=None,
                        subject="Loan Renewal Reminder",
                        message=email_expiry,
                        queue="short",
                        delayed=False,
                        job_name="Loan Renewal Reminder",
                    )
                    msg = """Dear Customer,
Your loan account number {loan_name} is due for renewal on or before {expiry_date}. Click on the link {link} to submit your request - Spark Loans""".format(
                        loan_name=loan.name,
                        expiry_date=str_exp,
                        link=las_settings.app_login_dashboard,
                    )

                    fcm_notification = frappe.get_doc(
                        "Spark Push Notification",
                        "Loan Renewal Reminder",
                        fields=["*"],
                    )
                    send_spark_push_notification(
                        fcm_notification=fcm_notification,
                        loan=loan.name,
                        customer=customer,
                    )
                    if msg:
                        receiver_list = [str(customer.phone)]
                        if customer.get_kyc().mob_num:
                            receiver_list.append(str(customer.get_kyc().mob_num))
                        if customer.get_kyc().choice_mob_no:
                            receiver_list.append(str(customer.get_kyc().choice_mob_no))

                        receiver_list = list(set(receiver_list))

                        frappe.enqueue(
                            method=send_sms,
                            receiver_list=receiver_list,
                            msg=msg,
                        )

                    renewal_doc.reminders = 4
                    renewal_doc.save(ignore_permissions=True)
                    frappe.db.commit()
        else:
            pass

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=_("Loan Renewal Application - Update Doc"),
        )


def renewal_doc_for_selected_customer():
    loan_name_list = ["SL000133", "SL000130", "SL000134"]
    for i in loan_name_list:
        loan = frappe.get_doc("Loan", str(i))
        frappe.log_error(
            message="Loan name :{}".format(i) + "\nLoan Document:{}".format(str(loan)),
            title=_("renewal_doc_for_selected_customer"),
        )
        las_settings = frappe.get_single("LAS Settings")
        str_exp = datetime.strptime(str(loan.expiry_date), "%Y-%m-%d").strftime(
            "%d/%m/%Y"
        )
        renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": ["!=", "Rejected"]},
            fields=["name"],
        )
        pending_renewal_doc_list = frappe.get_all(
            "Spark Loan Renewal Application",
            filters={"loan": loan.name, "status": "Pending"},
            fields=["*"],
        )
        try:
            customer = frappe.get_doc("Loan Customer", loan.customer)
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=(_("Loan Customer {} not found".format(loan.customer))),
            )
        user_kyc = frappe.get_all(
            "User KYC",
            filters={
                "user": customer.user,
                "updated_kyc": 1,
                "kyc_status": "Pending",
            },
            fields=["*"],
        )
        user_kyc_approved = frappe.get_all(
            "User KYC",
            filters={
                "user": customer.user,
                "updated_kyc": 1,
                "kyc_status": "Approved",
            },
            fields=["*"],
        )
        existing_renewal_doc = frappe.get_all(
            "Spark Loan Renewal Application", filters={"loan": i}
        )
        if not existing_renewal_doc:
            renewal_doc = frappe.get_doc(
                dict(
                    doctype="Spark Loan Renewal Application",
                    loan=loan.name,
                    lender=loan.lender,
                    old_kyc_name=customer.choice_kyc,
                    total_collateral_value=loan.total_collateral_value,
                    sanctioned_limit=loan.sanctioned_limit,
                    drawing_power=loan.drawing_power,
                    customer=customer.name,
                    customer_name=customer.full_name,
                    remarks="",
                )
            ).insert(ignore_permissions=True)
            frappe.db.commit()
        else:
            renewal_doc = frappe.get_doc(
                "Spark Loan Renewal Application", existing_renewal_doc[0].name
            )

        # grace_7days = datetime.strftime(frappe.utils.now_datetime().date(), "%Y-%m-%d")
        grace_7days = (frappe.utils.now_datetime() + timedelta(days=8)).date()
        grace_7days = datetime.strftime(grace_7days, "%Y-%m-%d")
        if type(renewal_doc.creation) == str:
            print("abcd")
            grace_7th = datetime.strptime(renewal_doc.creation, "%Y-%m-%d %H:%M:%S.%f")
        else:
            grace_7th = renewal_doc.creation
        grace_7th_expiry = datetime.strftime(
            (grace_7th + timedelta(days=7)).date(), "%Y-%m-%d"
        )
        grace_14th_expiry = datetime.strftime(
            (grace_7th + timedelta(days=14)).date(), "%Y-%m-%d"
        )
        # grace_7th_expiry = datetime.strftime(grace_7th_expiry, "%Y-%m-%d") + timedelta(days=7)
        print("grace_7th_expiry", (grace_7th_expiry))
        print("grace_7days", (grace_7days))
        print("grace_14th_expiry", grace_14th_expiry)
        if grace_7days <= grace_7th_expiry:
            print("akash")

        elif grace_7days > grace_7th_expiry and grace_7days <= grace_14th_expiry:
            applications = []
            current_date = frappe.utils.now_datetime().date()
            if (
                pending_renewal_doc_list and not user_kyc and not user_kyc_approved
            ) or (user_kyc_approved and pending_renewal_doc_list):
                top_up_application = frappe.get_all(
                    "Top up Application",
                    filters={
                        "loan": loan.name,
                        "status": ["IN", ["Pending", "Esign Done"]],
                    },
                    fields=["name"],
                )
                for i in top_up_application:
                    applications.append(i)
                loan_application = frappe.get_all(
                    "Loan Application",
                    filters={
                        "loan": loan.name,
                        "application_type": [
                            "IN",
                            ["Increase Loan", "Pledge More", "Margin Shortfall"],
                        ],
                    },
                    fields=["name"],
                )
                for i in loan_application:
                    applications.append(i)
                if not top_up_application:
                    if not loan_application:
                        current_year = frappe.utils.now_datetime().strftime("%Y")
                        current_year = int(current_year)
                        if (
                            (current_year % 400 == 0)
                            or (current_year % 100 != 0)
                            and (current_year % 4 == 0)
                        ):
                            no_of_days = 366
                        # Else it is not a leap year
                        else:
                            no_of_days = 365
                        renewal_penal_interest = frappe.get_doc("Lender", loan.lender)
                        daily_penal_interest = (
                            float(renewal_penal_interest.renewal_penal_interest)
                            / no_of_days
                        )
                        amount = loan.balance * (daily_penal_interest / 100)
                        penal_interest_transaction = frappe.get_doc(
                            {
                                "doctype": "Loan Transaction",
                                "loan": loan.name,
                                "lender": loan.lender,
                                "transaction_type": "Penal Interest",
                                "record_type": "DR",
                                "amount": round(amount, 2),
                                "unpaid_interest": round(amount, 2),
                                "time": current_date,
                            }
                        )
                        penal_interest_transaction.insert(ignore_permissions=True)
                        penal_interest_transaction.transaction_id = (
                            penal_interest_transaction.name
                        )
                        penal_interest_transaction.status = "Approved"
                        penal_interest_transaction.workflow_state = "Approved"
                        penal_interest_transaction.docstatus = 1
                        penal_interest_transaction.save(ignore_permissions=True)
                        frappe.db.commit()
