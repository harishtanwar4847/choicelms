// Copyright (c) 2021, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Unpledge Application", {
  refresh: function (frm) {
    show_fetch_items_button(frm);
    if (frm.doc.status != "Pending") {
      frm.clear_custom_buttons();
    }
    // console.log(frm.fields_dict["items"].grid.wrapper);
    // $(".grid-add-row").hide();
    // $(".grid-remove-rows").hide();
    // $(".grid-remove-all-rows").hide();
  },
  // items_on_form_rendered(frm, cdt, cdn) {
  //   frm.fields_dict["items"].grid.wrapper.find(".grid-shortcuts").hide();
  //   frm.fields_dict["items"].grid.wrapper.find(".grid-delete-row").hide();
  //   frm.fields_dict["items"].grid.wrapper.find(".grid-insert-row-below").hide();
  //   frm.fields_dict["items"].grid.wrapper.find(".grid-insert-row").hide();
  //   frm.fields_dict["items"].grid.wrapper.find(".grid-duplicate-row").hide();
  //   frm.fields_dict["items"].grid.wrapper.find(".grid-append-row").hide();
  // },
  // unpledge_items_on_form_rendered(frm, cdt, cdn) {
  //   frm.fields_dict["unpledge_items"].grid.wrapper
  //     .find(".grid-shortcuts")
  //     .hide();
  //   frm.fields_dict["unpledge_items"].grid.wrapper
  //     .find(".grid-delete-row")
  //     .hide();
  //   frm.fields_dict["unpledge_items"].grid.wrapper
  //     .find(".grid-insert-row-below")
  //     .hide();
  //   frm.fields_dict["unpledge_items"].grid.wrapper
  //     .find(".grid-insert-row")
  //     .hide();
  //   frm.fields_dict["unpledge_items"].grid.wrapper
  //     .find(".grid-duplicate-row")
  //     .hide();
  //   frm.fields_dict["unpledge_items"].grid.wrapper
  //     .find(".grid-append-row")
  //     .hide();
  // },
});

frappe.ui.form.on("Unpledge Application Unpledged Item", {
  sell_items_remove(frm) {
    show_fetch_items_button(frm);
  },
  sell_items_add(frm) {
    show_fetch_items_button(frm);
  },
});

frappe.ui.form.on("Unpledge Application", {
  loan: function (frm) {
    var is_true = frappe.user_roles.find((role) => role === "Loan Customer");
    if ((!is_true || frappe.session.user == "Administrator") && frm.doc.loan) {
      // if (frappe.session.user == frm.doc.owner) {
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

function show_fetch_items_button(frm) {
  if (frm.doc.unpledge_items.length == 0) {
    frm.add_custom_button(__("Fetch Unpledge Items"), function () {
      frappe.call({
        type: "POST",
        method:
          "lms.lms.doctype.unpledge_application.unpledge_application.get_collateral_details",
        args: { unpledge_application_name: frm.doc.name },
        freeze: true,
        freeze_message: "Please wait",
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
            freeze_message: "Please wait",
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
