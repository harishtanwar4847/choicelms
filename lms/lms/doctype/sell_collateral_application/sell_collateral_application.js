// Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sell Collateral Application", {
  refresh: function (frm) {
    show_fetch_items_button(frm);
    if (frm.doc.status != "Pending")
    {
      frm.set_df_property("items", "read_only", 1);
    }
  },
});

frappe.ui.form.on("Sell Collateral Application", {
  loan: function(frm) {
    cur_frm.clear_table("items");
    cur_frm.refresh_field("items");
    if (frappe.session.user == cur_frm.doc.owner) {
      frappe.model.with_doc("Loan", cur_frm.doc.loan, function() {
        // frappe.db.get_value("Loan Margin Shortfall", {"loan": cur_frm.doc.loan,"status": "Sell Triggered"}, ["name"], (res) => {
        //   if (res && res.message) {
        //     frm.set_value('loan_margin_shortfall', res.message);
        //   }
        // });
        var tabletransfer = frappe.model.get_doc("Loan", cur_frm.doc.loan)
        $.each(tabletransfer.items, function(index,row) {
          var d = cur_frm.add_child("items")
          if (row.pledged_quantity > 0) {
          d.isin = row.isin;
          d.quantity = row.pledged_quantity;
          cur_frm.refresh_field("items");
          }
      });
    });
    }
  }
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
        freeze_message: "Fetching Collateral Details",
        callback: (res) => {
          frm.set_value("sell_items", res.message);
          show_fetch_items_button(frm);
        },
      });
    });
  } else {
    frm.clear_custom_buttons();
  }
}
