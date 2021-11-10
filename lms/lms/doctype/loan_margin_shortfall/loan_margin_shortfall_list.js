// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.listview_settings["Loan Margin Shortfall"] = {
  hide_name_column: true,
  before_render() {
    frappe.call({
      type: "POST",
      method:
        "lms.lms.doctype.loan_margin_shortfall.loan_margin_shortfall.set_timer",
      args: { loan_margin_shortfall_name: "" },
    });
  },

  formatters: {
    shortfall_percentage(val) {
      if (val <= 15) {
        return (
          '<span style= "color: yellow;"><strong>' + val + "</strong></span>"
        );
      } else if (15 < val && val <= 25) {
        return (
          '<span style= "color: orange;"> <strong>' + val + "</strong></span>"
        );
      } else if (val > 25) {
        return '<span style= "color: red;"><strong>' + val + "</strong></span>";
      }
    },
  },
};
