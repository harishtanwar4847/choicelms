// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lender", {
  refresh: function (frm) {
    $("div.grid-heading-row span.hidden-xs").html("Level");
  },
});
