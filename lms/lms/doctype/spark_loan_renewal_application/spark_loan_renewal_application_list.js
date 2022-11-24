// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.listview_settings["Spark Loan Renewal Application"] = {
  hide_name_column: true,
  before_render() {
    frappe.call({
      type: "POST",
      method:
        "lms.lms.doctype.loan_margin_shortfall.loan_margin_shortfall.set_timer",
      args: { loan_margin_shortfall_name: "" },
    });
  },
};
