// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lender", {
  refresh: function (frm, cdt, cdn) {
    $("div.grid-heading-row span.hidden-xs").html("Level");
    if (frm.doc.concentration_rule.length > 9) {
      $(".grid-add-row").hide();
    }
  },
});
frappe.ui.form.on("Concentration Rule", {
  concentration_rule_add(frm, cdt, cdn) {
    if (frm.doc.concentration_rule.length > 9) {
      $(".grid-add-row").hide();
    }
  },
});
