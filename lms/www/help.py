from datetime import datetime

import frappe


def get_context(context):
    context.marginmax = frappe.get_all(
        "Margin Shortfall Action",
        fields=["*"],
        filters={"sell_off_deadline_eod": ("!=", 0)},
        order_by="creation",
    )[0]
    context.marginmax.sell_off_deadline_eod = datetime.strptime(
        "{}".format(context.marginmax.sell_off_deadline_eod), "%H"
    ).strftime("%I:%M %p")
    print(context.marginmax.sell_off_deadline_eod)

    context.marginmin = frappe.get_all(
        "Margin Shortfall Action",
        fields=["*"],
        filters={"sell_off_after_hours": ("!=", 0)},
        order_by="creation",
    )[0]

    context.intrupto5 = frappe.get_all(
        "Interest Configuration",
        fields=["*"],
        filters={"from_amount": ("=", 0)},
        order_by="creation",
    )[0]

    context.lenderCharges = frappe.get_last_doc("Lender")
