# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import datetime
from datetime import timedelta

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class SecurityExposureSummary(Document):
    pass


@frappe.whitelist()
def security_exposure_summary():
    try:
        total_sum = 0
        securities = frappe.get_all("Security", fields=["*"])
        creation_date = frappe.db.sql(
            """select distinct(isin),cast(creation as date)as c_date from `tabCollateral Ledger` where cast(creation as date) = '{created}' """.format(
                created=frappe.utils.now_datetime().strftime("%Y-%m-%d"),
            ),
            as_dict=True,
            debug=True,
        )
        for i in creation_date:
            price = frappe.db.sql(
                """select name,price,security_name from `tabSecurity` where isin = '{}'""".format(
                    i.isin
                ),
                as_dict=True,
            )
            qty = (("",),)
            if str(creation_date[0].c_date) == frappe.utils.now_datetime().strftime(
                "%Y-%m-%d"
            ):
                qty = frappe.db.sql(
                    """select sum(pledged_quantity) from `tabLoan Item` where isin = '{security}' and parenttype ='Loan' """.format(
                        security=i.isin,
                    )
                )

                quantity = qty[0][0]
                total = float(price[0].price) * float(quantity)
                total_sum += total
        for i in creation_date:
            price = frappe.db.sql(
                """select name,price,security_name from `tabSecurity` where isin = '{}'""".format(
                    i.isin
                ),
                as_dict=True,
            )
            qty = (("",),)
            if str(creation_date[0].c_date) == frappe.utils.now_datetime().strftime(
                "%Y-%m-%d"
            ):
                qty = frappe.db.sql(
                    """select sum(pledged_quantity) from `tabLoan Item` where isin = '{security}' and parenttype ='Loan' """.format(
                        security=i.isin,
                    )
                )
                quantity = qty[0][0]

            security_exposure_summary = frappe.get_doc(
                dict(
                    doctype="Security Exposure Summary",
                    isin=price[0].name,
                    security_name=price[0].security_name,
                    quantity=quantity,
                    rate=price[0].price,
                    value=(float(quantity) * float(price[0].price)),
                    exposure_=((float(quantity) * float(price[0].price)) / total_sum)
                    * 100,
                    creation_date=frappe.utils.now_datetime().date(),
                ),
            ).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=frappe._("Security Exposure Summary"),
        )


@frappe.whitelist()
def excel_generator(doc_filters):
    if len(doc_filters) == 2:
        doc_filters = {
            "creation_date": str(frappe.utils.now_datetime().date() - timedelta(days=1))
        }
    security_exposure_doc = frappe.get_all(
        "Security Exposure Summary",
        filters=doc_filters,
        fields=[
            "isin",
            "security_name",
            "quantity",
            "rate",
            "value",
            "exposure_",
        ],
    )
    if security_exposure_doc == []:
        frappe.throw(("Record does not exist"))
    final = pd.DataFrame([c.values() for c in security_exposure_doc], index=None)
    final.columns = security_exposure_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    report = final.sum(numeric_only=True)
    report = final.iloc[:, [2, 4, 5]].sum()
    final.loc["Grand Total"] = report
    final.loc[final["Isin"].isnull(), "Isin"] = "Total"
    final.fillna("")
    file_name = "security_exposure_{}".format(frappe.utils.now_datetime())
    sheet_name = "Security Exposure Summary"
    return lms.download_file(
        dataframe=final,
        file_name=file_name,
        file_extention="xlsx",
        sheet_name=sheet_name,
    )
