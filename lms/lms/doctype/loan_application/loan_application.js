// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Application", {
  is_default: function (frm) {
    if (frm.doc.is_default == 0) {
      frm.set_value("custom_base_interest", 0);
      frm.set_value("custom_rebate_interest", 0);
    } else {
      frm.set_df_property("custom_base_interest", "read_only", 1);
      frm.set_df_property("custom_rebate_interest", "read_only", 1);
    }
  },

  on_load: function (frm) {
    frappe.call({
      method:
        "lms.lms.doctype.loan_application.loan_application.check_for_pledge_failure",
      freeze: true,
      args: {
        la_name: frm.doc.name,
      },
      callback: (res) => {
        if (res.message == "Pledge Failure") {
          frm.set_df_property("is_default", "read_only", 1);
          frm.set_df_property("custom_base_interest", "read_only", 1);
          frm.set_df_property("custom_rebate_interest", "read_only", 1);
        }
      },
    });
  },

  refresh: function (frm) {
    if (frm.doc.status != "Waiting to be pledged") {
      frm.get_field("items").grid.only_sortable();
      $(".grid-add-row").hide();
      $(".grid-remove-rows").hide();
      $(".grid-remove-all-rows").hide();
    }

    // enable/disable file inputs
    frm.attachments.parent.hide();
    if (["Esign Done", "Approved"].includes(frm.doc.status)) {
      if (frm.doc.customer_esigned_document) {
        frm
          .get_field("customer_esigned_document")
          .$input_wrapper.find("[data-action=clear_attachment]")
          .hide();
      }
      if (frm.doc.lender_esigned_document) {
        frm
          .get_field("lender_esigned_document")
          .$input_wrapper.find("[data-action=clear_attachment]")
          .hide();
      }
    }

    // enable/disable lender_approval_status field in LA items
    if (
      frm.doc.workflow_state == "Approved" ||
      frm.doc.workflow_state == "Rejected"
    ) {
      var df = frappe.meta.get_docfield(
        "Loan Application Item",
        "lender_approval_status",
        cur_frm.doc.name
      );
      df.read_only = 1;
    }

    // enable/disable custom btn to actions on LA items when status is Pledge executed
    if (
      frm.doc.status == "Pledge executed" &&
      frm.doc.instrument_type != "Mutual Fund"
    ) {
      frm.add_custom_button(
        __("Approve All ISIN"),
        function () {
          let selected = frm.get_selected();
          if (Object.keys(selected).length > 0) {
            frm.doc.items.forEach((x) => {
              if (x.pledge_status != "Failure") {
                if (selected.items.includes(x.name)) {
                  frappe.model.set_value(
                    "Loan Application Item",
                    x.name,
                    "lender_approval_status",
                    "Approved"
                  );
                }
              }
            });
            frm.refresh_fields();

            frappe.call({
              method:
                "lms.lms.doctype.loan_application.loan_application.actions_on_isin",
              freeze: true,
              args: {
                loan_application: frm.doc,
              },
              callback: function (res) {
                frm.set_value(
                  "total_collateral_value",
                  res.message.total_collateral_value
                );
                frm.set_value(
                  "total_collateral_value_str",
                  res.message.total_collateral_value_str
                );
                frm.set_value("drawing_power", res.message.drawing_power);
                frm.set_value(
                  "drawing_power_str",
                  res.message.drawing_power_str
                );
                frm.refresh_fields();
              },
            });
          }
        },
        __("Actions On ISIN")
      );

      frm.add_custom_button(
        __("Reject All ISIN"),
        function () {
          let selected = frm.get_selected();
          if (Object.keys(selected).length > 0) {
            frm.doc.items.forEach((x) => {
              if (x.pledge_status != "Failure") {
                if (selected.items.includes(x.name)) {
                  // x.lender_approval_status = "Rejected";
                  frappe.model.set_value(
                    "Loan Application Item",
                    x.name,
                    "lender_approval_status",
                    "Rejected"
                  );
                }
              }
            });
            frm.refresh_fields();

            frappe.call({
              method:
                "lms.lms.doctype.loan_application.loan_application.actions_on_isin",
              freeze: true,
              args: {
                loan_application: frm.doc,
              },
              callback: function (res) {
                frm.set_value(
                  "total_collateral_value",
                  res.message.total_collateral_value
                );
                frm.set_value(
                  "total_collateral_value_str",
                  res.message.total_collateral_value_str
                );
                frm.set_value("drawing_power", res.message.drawing_power);
                frm.set_value(
                  "drawing_power_str",
                  res.message.drawing_power_str
                );
                frm.refresh_fields();
              },
            });
          }
        },
        __("Actions On ISIN")
      );
    }
  },
});
