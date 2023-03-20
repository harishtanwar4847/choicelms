// Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sell Collateral Application", {
  refresh: function (frm) {
    show_fetch_items_button(frm);
    // if (frm.doc.status != "Pending" || frappe.session.user != frm.doc.owner) {
    if (frm.doc.status != "Pending") {
      frm.set_df_property("items", "read_only", 1);
    }
    if (frm.doc.status == "Approved" || frm.doc.status == "Rejected") {
      frm.set_df_property("processed", "read_only", 1);
    }
    if (frm.doc.owner != frappe.session.user) {
      frm.set_df_property("loan_margin_shortfall", "read_only", 1);
    }
    if (frm.doc.status != "Pending") {
      frm.clear_custom_buttons();
    }
  },
});

frappe.ui.form.on("Sell Collateral Application", {
  loan: function (frm) {
    var is_true = frappe.user_roles.find((role) => role === "Loan Customer");
    if ((!is_true || frappe.session.user == "Administrator") && frm.doc.loan) {
      // if (frappe.session.user == frm.doc.owner) {
      frappe.db.get_value(
        "Loan Margin Shortfall",
        { loan: frm.doc.loan, status: "Sell Triggered" },
        ["name"],
        (res) => {
          frm.set_value("loan_margin_shortfall", res["name"]);
        }
      );
      frm.clear_table("items");
      frm.refresh_field("items");
      frappe.model.with_doc("Loan", frm.doc.loan, function () {
        var tabletransfer = frappe.model.get_doc("Loan", frm.doc.loan);
        $.each(tabletransfer.items, function (index, row) {
          if (row.pledged_quantity > 0) {
            var d = frm.add_child("items");
            d.isin = row.isin;
            d.quantity = row.pledged_quantity;
            d.folio = row.folio;
            d.psn = row.psn;
            frm.refresh_field("items");
          }
        });
      });
    }
  },
});

frappe.ui.form.on("Sell Collateral Application Sell Item", {
  sell_items_remove(frm) {
    show_fetch_items_button(frm);
  },
  sell_items_add(frm) {
    show_fetch_items_button(frm);
  },
});

function show_fetch_items_button(frm) {
  if (frm.doc.sell_items.length == 0) {
    frm.add_custom_button(__("Fetch Sell Items"), function () {
      frappe.call({
        type: "POST",
        method:
          "lms.lms.doctype.sell_collateral_application.sell_collateral_application.get_collateral_details",
        args: { sell_collateral_application_name: frm.doc.name },
        freeze: true,
        freeze_message: "Please wait",
        callback: (res) => {
          frm.set_value("sell_items", res.message);
          show_fetch_items_button(frm);
        },
      });
    });
  } else {
    if (frm.doc.instrument_type == "Mutual Fund") {
      if (!frm.doc.is_validated) {
        frm.clear_custom_buttons();
        frm.add_custom_button(__("Validate Sell Items"), function () {
          frappe.call({
            type: "POST",
            method:
              "lms.lms.doctype.sell_collateral_application.sell_collateral_application.validate_invoc",
            args: { sell_collateral_application_name: frm.doc.name },
            freeze: true,
            freeze_message: "Please wait",
            callback: (res) => {
              frm.reload_doc();
            },
          });
        });
      }
      if (!frm.doc.is_initiated && frm.doc.is_validated) {
        frm.clear_custom_buttons();
        frm.add_custom_button(__("Initiate Sell Items"), function () {
          frappe.call({
            type: "POST",
            method:
              "lms.lms.doctype.sell_collateral_application.sell_collateral_application.initiate_invoc",
            args: { sell_collateral_application_name: frm.doc.name },
            freeze: true,
            freeze_message: "Please wait",
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
