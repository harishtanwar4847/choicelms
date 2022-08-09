# Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import datetime

import frappe
import numpy as np
import pandas as pd
from frappe.model.document import Document

import lms


class ClientSanctionDetails(Document):
    pass


@frappe.whitelist()
def excel_generator(doc_filters):
    client_sanctioned_details_doc = frappe.get_all(
        "Client Sanction Details",
        filters=doc_filters,
        fields=[
            "client_code",
            "loan_no",
            "client_name",
            "pan_no",
            "start_date",
            "end_date",
            "sanctioned_amount",
            "roi",
            "sanction_date",
        ],
    )
    if client_sanctioned_details_doc == []:
        frappe.throw(("Record does not exist"))

    final = pd.DataFrame(
        [c.values() for c in client_sanctioned_details_doc], index=None
    )
    final.columns = client_sanctioned_details_doc[0].keys()
    final.columns = pd.Series(final.columns.str.replace("_", " ")).str.title()
    final.sort_values("Client Code", inplace=True)

    final.loc[final["Client Code"].duplicated(), "Client Code"] = ""
    final.loc[final["Loan No"].duplicated(), "Loan No"] = ""
    final.loc[final["Client Name"].duplicated(), "Client Name"] = ""
    final.loc[final["Pan No"].duplicated(), "Pan No"] = ""
    file_name = "client_santion_details_{}".format(frappe.utils.now_datetime())
    sheet_name = "Client Sanction Details"
    return lms.download_file(
        dataframe=final,
        file_name=file_name,
        file_extention="xlsx",
        sheet_name=sheet_name,
    )
