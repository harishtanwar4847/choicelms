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
  if (frm.doc.unpledge_item.length == 0) {
    frm.add_custom_button(__("Fetch Unpledge Items"), function () {
      frappe.call({
        type: "POST",
        method:
          "lms.lms.doctype.unpledge_application.unpledge_application.get_collateral_details",
        args: { unpledge_application_name: frm.doc.name },
        freeze: true,
        freeze_message: "Fetching Collateral Details",
        callback: (res) => {
          frm.set_value("unpledge_item", res.message);
          show_fetch_items_button(frm);
        },
      });
    });
  } else {
    frm.clear_custom_buttons();
  }
}
