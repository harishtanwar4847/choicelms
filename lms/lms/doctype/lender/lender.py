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

    def get_sanction_letter_template(self):
        file_name = frappe.db.get_value("File", {"file_url": self.sanction_letter})
        return frappe.get_doc("File", file_name)

    def validate_concentration_rule(self):
        security_category = [i.security_category for i in self.concentration_rule]
        if len(security_category) > len(set(security_category)):
            frappe.throw("Same Security Category can't be use")
        for i in self.concentration_rule:
            # if i.idx > 1:
            #     if (
            #         self.concentration_rule[i.idx - 1].security_category
            #         == self.concentration_rule[i.idx - 2].security_category
            #     ):
            #         frappe.throw(
            #             "Level " + str(i.idx) + ": Same Security Category can't be use"
            #         )

            if (
                i.single_scrip_numerical_limit != None
                and i.single_scrip_percentage_limit != None
            ):
                if (
                    int(i.single_scrip_numerical_limit) > 0
                    and float(i.single_scrip_percentage_limit) > 0
                ):
                    frappe.throw(
                        "Level "
                        + str(i.idx)
                        + ": Enter either Single Scrip numerical limit or Single Scrip percentage limit"
                    )
                if (
                    float(i.single_scrip_percentage_limit) == 0.0
                    and i.single_scrip_numerical_limit >= 0
                ):
                    if (
                        self.minimum_sanctioned_limit > i.single_scrip_numerical_limit
                    ) or (
                        self.maximum_sanctioned_limit < i.single_scrip_numerical_limit
                    ):
                        frappe.throw(
                            "Level "
                            + str(i.idx)
                            + ": Single Scrip Numerical limit has to be in between of minimum and maximum lending amount"
                        )
            if (
                i.category_numerical_limit != None
                and i.category_percentage_limit != None
            ):
                if (
                    int(i.category_numerical_limit) > 0
                    and float(i.category_percentage_limit) > 0
                ):
                    frappe.throw(
                        "Level "
                        + str(i.idx)
                        + ": Enter either Category numerical limit or Category percentage limit"
                    )
                if (
                    float(i.category_percentage_limit) == 0.0
                    and int(i.category_numerical_limit) >= 0
                ):
                    if (self.minimum_sanctioned_limit > i.category_numerical_limit) or (
                        self.maximum_sanctioned_limit < i.category_numerical_limit
                    ):
                        frappe.throw(
                            "Level "
                            + str(i.idx)
                            + ": Category Numerical limit has to be in between of minimum and maximum lending amount"
                        )
            if i.single_scrip_percentage_limit:
                if (
                    float(i.single_scrip_percentage_limit) > 100
                    or float(i.single_scrip_percentage_limit) < 0
                ):
                    frappe.throw(
                        "Level "
                        + str(i.idx)
                        + ": Single Scrip Percentage limit should be in between 0 and 100"
                    )
            if i.category_percentage_limit:
                if (
                    float(i.category_percentage_limit) > 100
                    or float(i.category_percentage_limit) < 0
                ):
                    frappe.throw(
                        "Level "
                        + str(i.idx)
                        + ": Category Percentage limit should be in between 0 and 100"
                    )
            if (
                i.minimum_scrip_limit or i.conditional_scrip_limit
            ) and not i.allow_single_category_lending:
                frappe.throw(
                    "Level "
                    + str(i.idx)
                    + ": Must allow single category lending "
                    + i.security_category
                )

    def validate(self):

        if len(self.concentration_rule) > 10:
            frappe.throw(_("Maximum 10 levels allowed."))

        if cint(self.interest_percentage_sharing) > 100:
            frappe.throw(
                _("Interest Percentage Sharing (%) value should not greater than 100.")
            )

        if (
            self.lender_processing_fees_type == "Percentage"
            and cint(self.lender_processing_fees) > 100
        ):
            frappe.throw(
                _("Lender Processing Fees (%) value should not greater than 100.")
            )

        if self.stamp_duty_type == "Percentage" and cint(self.stamp_duty) > 100:
            frappe.throw(_("Stamp Duty (%) value should not greater than 100."))

        if (
            self.documentation_charge_type == "Percentage"
            and cint(self.documentation_charges) > 100
        ):
            frappe.throw(
                _("Documentation Charges (%) value should not greater than 100.")
            )

        if (
            self.mortgage_charge_type == "Percentage"
            and cint(self.mortgage_charges) > 100
        ):
            frappe.throw(_("Mortgage Charges (%) value should not greater than 100."))

        if (
            self.lender_processing_fees_sharing_type == "Percentage"
            and cint(self.lender_processing_fees_sharing) > 100
        ):
            frappe.throw(
                _(
                    "Lender Processing Fees Sharing (%) value should not greater than 100."
                )
            )

        if (
            self.stamp_duty_sharing_type == "Percentage"
            and cint(self.stamp_duty_sharing) > 100
        ):
            frappe.throw(_("Stamp Duty Sharing (%) value should not greater than 100."))

        if (
            self.documentation_charge_sharing_type == "Percentage"
            and cint(self.documentation_charges_sharing) > 100
        ):
            frappe.throw(
                _(
                    "Documentation Charges Sharing (%) value should not greater than 100."
                )
            )

        if (
            self.mortgage_charge_sharing_type == "Percentage"
            and cint(self.mortgage_charges_sharing) > 100
        ):
            frappe.throw(
                _("Mortgage Charges Sharing (%) value should not greater than 100.")
            )

        if (
            self.lien_initiate_charge_type == "Percentage"
            and cint(self.lien_initiate_charges) > 100
        ):
            frappe.throw(
                _("Lien Initiate Charges (%) value should not greater than 100.")
            )

        if (
            self.invoke_initiate_charge_type == "Percentage"
            and cint(self.invoke_initiate_charges) > 100
        ):
            frappe.throw(
                _("Invoke Initiate Charges (%) value should not greater than 100.")
            )

        if (
            self.revoke_initiate_charge_type == "Percentage"
            and cint(self.revoke_initiate_charges) > 100
        ):
            frappe.throw(
                _("revoke Initiate Charges (%) value should not greater than 100.")
            )

        # Validate concentration rule Mapping
        self.validate_concentration_rule()

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
        file_name = frappe.db.get_value("File", {"file_url": self.lender_logo})
        return frappe.get_doc("File", file_name) if file_name else None

    def get_interest_letter_template(self):
        file_name = frappe.db.get_value("File", {"file_url": self.interest_letter})
        return frappe.get_doc("File", file_name)

    def get_lender_address_file(self):
        file_name = frappe.db.get_value("File", {"file_url": self.lender_address})
        return frappe.get_doc("File", file_name) if file_name else None

    def before_save(self):
        if (self.lender_logo and self.lender_header) or (
            self.lender_address and self.lender_footer
        ):
            frappe.throw(_("Please attach image or html charaters. Cannot use both."))
        elif self.lender_logo and self.is_html:
            frappe.throw(_("Please uncheck Is html checkbox."))
