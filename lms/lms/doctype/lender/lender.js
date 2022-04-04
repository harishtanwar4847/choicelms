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
    console.log(frm.fields_dict["concentration_rule"].grid.wrapper);
    if (frm.doc.concentration_rule.length > 9) {
      $(".grid-add-row").hide();
      // frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-delete-row").hide();
      // frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-insert-row-below").hide();
      // frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-insert-row").hide();
      // frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-duplicate-row").hide();
    }
  },
  // concentration_rule_on_form_rendered(frm, cdt, cdn) {
  //     if (frm.doc.concentration_rule.length > 9) {
  //     $(".grid-add-row").hide();
  //     frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-delete-row").hide();
  //     frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-insert-row-below").hide();
  //     frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-insert-row").hide();
  //     frm.fields_dict["concentration_rule"].grid.wrapper.find(".grid-duplicate-row").hide();
  //   }
  // }
});
