// Copyright (c) 2022, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Spark Email Campaign", {
  refresh: function (frm, cdt, cdn) {
    if (frm.doc.docstatus != 0) {
      frm.get_field("preview_html").$wrapper.html(frm.doc.template_html);
    }
    $("div.grid-heading-row span.hidden-xs").html("Level");
    if (frm.doc.sender_email.length > 0) {
      $(".grid-add-row").hide();
    }
  },
  sender_email_on_form_rendered(frm, cdt, cdn) {
    frm.fields_dict["sender_email"].grid.wrapper.find(".grid-shortcuts").hide();
    if (frm.doc.sender_email.length >= 1) {
      $(".grid-add-row").hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-delete-row")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-insert-row-below")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-insert-row")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-duplicate-row")
        .hide();
      frm.fields_dict["sender_email"].grid.wrapper
        .find(".grid-append-row")
        .hide();
    }
  },
});

frappe.ui.form.on("User Email", {
  sender_email_add(frm, cdt, cdn) {
    if (frm.doc.sender_email.length >= 1) {
      $(".grid-add-row").hide();
    }
    if (frm.doc.sender_email.length > 1) {
      frappe.msgprint(__("Maximum 1 level allowed"));
    }
  },
});
