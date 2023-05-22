// Copyright (c) 2023, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sanction Letter and CIAL Log", {
  refresh: function (frm) {
    frm.refresh_field("interest_letter_table");
  },
});
