// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.listview_settings["Loan Margin Shortfall"] = {
  hide_name_column: true,

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
