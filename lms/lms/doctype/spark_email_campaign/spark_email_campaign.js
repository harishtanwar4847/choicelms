// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spark Email Campaign", {
  refresh: function (frm) {
    $("div.grid-heading-row span.hidden-xs").html("Level");
    if (frm.doc.sender.length == 1) {
      $(".grid-add-row").hide();
    }
  },
  sender_on_form_rendered(frm, cdt, cdn) {
    frm.fields_dict["sender"].grid.wrapper.find(".grid-shortcuts").hide();
    if (frm.doc.sender.length == 1) {
      $(".grid-add-row").hide();
      frm.fields_dict["sender"].grid.wrapper.find(".grid-delete-row").hide();
      frm.fields_dict["sender"].grid.wrapper
        .find(".grid-insert-row-below")
        .hide();
      frm.fields_dict["sender"].grid.wrapper.find(".grid-insert-row").hide();
      frm.fields_dict["sender"].grid.wrapper.find(".grid-duplicate-row").hide();
      frm.fields_dict["sender"].grid.wrapper.find(".grid-append-row").hide();
    }
  },
});
frappe.ui.form.on("Sender", {
  sender_add(frm, cdt, cdn) {
    console.log(frm.fields_dict["sender"].grid.wrapper);
    if (frm.doc.sender.length == 1) {
      $(".grid-add-row").hide();
    }
    if (frm.doc.sender.length > 1) {
      frappe.msgprint(__("Maximum 1 level allowed"));
    }
  },
});
