// Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Unpledge Application", {
  refresh: function (frm) {
    show_fetch_items_button(frm);
  },
});

frappe.ui.form.on("Unpledge Application Unpledged Item", {
  sell_items_remove(frm) {
    show_fetch_items_button(frm);
  },
  sell_items_add(frm) {
    show_fetch_items_button(frm);
  },
});

function show_fetch_items_button(frm) {
  if (frm.doc.unpledge_items.length == 0) {
    frm.add_custom_button(__("Fetch Unpledge Items"), function () {
      frappe.call({
        type: "POST",
        method:
          "lms.lms.doctype.unpledge_application.unpledge_application.get_collateral_details",
        args: { unpledge_application_name: frm.doc.name },
        freeze: true,
        freeze_message: "Fetching Collateral Details",
        callback: (res) => {
          frm.set_value("unpledge_items", res.message);
          show_fetch_items_button(frm);
        },
      });
    });
  } else {
    if (frm.doc.instrument_type == "Mutual Fund") {
      if (!frm.doc.is_validated) {
        frm.clear_custom_buttons();
        frm.add_custom_button(__("Validate Revoke Items"), function () {
          frappe.call({
            type: "POST",
            method:
              "lms.lms.doctype.unpledge_application.unpledge_application.validate_revoc",
            args: { unpledge_application_name: frm.doc.name },
            freeze: true,
            freeze_message: "Validating Revoke Items",
            callback: (res) => {
              frm.reload_doc();
            },
          });
        });
      }
      if (!frm.doc.is_initiated && frm.doc.is_validated) {
        frm.clear_custom_buttons();
        frm.add_custom_button(__("Initiate Revoke Items"), function () {
          frappe.call({
            type: "POST",
            method:
              "lms.lms.doctype.unpledge_application.unpledge_application.initiate_revoc",
            args: { unpledge_application_name: frm.doc.name },
            freeze: true,
            freeze_message: "Initiating Revoke Items",
            callback: (res) => {
              frm.reload_doc();
            },
          });
        });
      }
    } else {
      frm.clear_custom_buttons();
    }
  }
}
