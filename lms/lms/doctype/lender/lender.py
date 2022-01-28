# -*- coding: utf-8 -*-
# Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

import lms


class Lender(Document):
    def get_loan_agreement_template(self):
        file_name = frappe.db.get_value("File", {"file_url": self.agreement_template})
        return frappe.get_doc("File", file_name)

    def get_loan_enhancement_agreement_template(self):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.enhancement_agreement_template}
        )
        return frappe.get_doc("File", file_name)

    def validate(self):
        if cint(self.interest_percentage_sharing) > 100:
            frappe.throw(
                _("Interest Percentage Sharing value should not greater than 100.")
            )

        if (
            self.lender_processing_fees_type == "Percentage"
            and cint(self.lender_processing_fees) > 100
        ):
            frappe.throw(_("Lender Processing Fees value should not greater than 100."))

        if self.stamp_duty_type == "Percentage" and cint(self.stamp_duty) > 100:
            frappe.throw(_("Stamp Duty value should not greater than 100."))

        if (
            self.documentation_charge_type == "Percentage"
            and cint(self.documentation_charges) > 100
        ):
            frappe.throw(_("Documentation Charges value should not greater than 100."))

        if (
            self.mortgage_charge_type == "Percentage"
            and cint(self.mortgage_charges) > 100
        ):
            frappe.throw(_("Mortgage Charges value should not greater than 100."))

        if (
            self.lender_processing_fees_sharing_type == "Percentage"
            and cint(self.lender_processing_fees_sharing) > 100
        ):
            frappe.throw(
                _("Lender Processing Fees Sharing value should not greater than 100.")
            )

        if (
            self.stamp_duty_sharing_type == "Percentage"
            and cint(self.stamp_duty_sharing) > 100
        ):
            frappe.throw(_("Stamp Duty Sharing value should not greater than 100."))

        if (
            self.documentation_charge_sharing_type == "Percentage"
            and cint(self.documentation_charges_sharing) > 100
        ):
            frappe.throw(
                _("Documentation Charges Sharing value should not greater than 100.")
            )

        if (
            self.mortgage_charge_sharing_type == "Percentage"
            and cint(self.mortgage_charges_sharing) > 100
        ):
            frappe.throw(
                _("Mortgage Charges Sharing value should not greater than 100.")
            )

    def get_approved_securities_template(self):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.approved_securities_template}
        )
        return frappe.get_doc("File", file_name)

    def get_loan_account_statement_template(self):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.loan_account_statement_template}
        )
        return frappe.get_doc("File", file_name)

    def get_pledged_security_statement_template(self):
        file_name = frappe.db.get_value(
            "File", {"file_url": self.pledged_security_statement_template}
        )
        return frappe.get_doc("File", file_name)

    def get_lender_logo_file(self):
        file_name = frappe.db.get_value("File", {"file_url": self.logo_file_1})
        return frappe.get_doc("File", file_name) if file_name else None


def father_job():
    """
    frappe.enqueue(method="lms.lms.doctype.lender.lender.father_job",queue="default",job_name="Father job")
    from datetime import datetime,timedelta
    start = datetime.strptime("2022-01-27 17:35:59.152473", "%Y-%m-%d %H:%M:%S.%f")
    end = datetime.strptime("2022-01-27 17:42:01.640181", "%Y-%m-%d %H:%M:%S.%f")
    time_used = lms.convert_sec_to_hh_mm_ss(abs(end-start).total_seconds())
    """
    for n in range(10):
        name_of_job = "Child_job_{}".format(n)
        frappe.enqueue(
            method="lms.lms.doctype.lender.lender.child_job",
            queue="short",
            job_name=name_of_job,
            name_of_file=name_of_job,
        )


def child_job(name_of_file):
    import time

    # m = 20
    o = 2

    for m in range(20):
        file = frappe.utils.get_files_path("{}.txt".format(name_of_file))

        with open(file, "a") as file1:
            file1.write(
                '"index": {}, "time": {}\n'.format(m, str(frappe.utils.now_datetime()))
            )
            time.sleep(o)
        file1.close()
