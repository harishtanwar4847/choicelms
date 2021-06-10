// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Concentration Rule", {
  refresh: function (frm) {
    // single script threshold mandatory
    frm.set_df_property("single_script_threshold", "reqd", 0);
    frm.set_df_property("single_script_threshold_type", "reqd", 0);
    if (frm.doc.is_single_script_allowed) {
      frm.set_df_property("single_script_threshold", "reqd", 1);
      frm.set_df_property("single_script_threshold_type", "reqd", 1);
    }

    // group script threshold mandatory
    frm.set_df_property("per_script_threshold", "reqd", 0);
    frm.set_df_property("per_script_threshold_type", "reqd", 0);
    frm.set_df_property("group_script_threshold", "reqd", 0);
    frm.set_df_property("group_script_threshold_type", "reqd", 0);
    if (frm.doc.is_group_script_limited) {
      frm.set_df_property("per_script_threshold", "reqd", 1);
      frm.set_df_property("per_script_threshold_type", "reqd", 1);
      frm.set_df_property("group_script_threshold", "reqd", 1);
      frm.set_df_property("group_script_threshold_type", "reqd", 1);
    }

    // group script max mandatory
    frm.set_df_property("group_script_max_limit", "reqd", 0);
    frm.set_df_property("group_script_max_limit_type", "reqd", 0);
    if (frm.doc.is_group_script_max_limited) {
      frm.set_df_property("group_script_max_limit", "reqd", 1);
      frm.set_df_property("group_script_max_limit_type", "reqd", 1);
    }
  },
  is_single_script_allowed: function (frm) {
    frm.set_df_property(
      "single_script_threshold",
      "reqd",
      frm.doc.is_single_script_allowed
    );
    frm.set_df_property(
      "single_script_threshold_type",
      "reqd",
      frm.doc.is_single_script_allowed
    );
  },
  is_group_script_limited: function (frm) {
    frm.set_df_property(
      "per_script_threshold",
      "reqd",
      frm.doc.is_group_script_limited
    );
    frm.set_df_property(
      "per_script_threshold_type",
      "reqd",
      frm.doc.is_group_script_limited
    );
    frm.set_df_property(
      "group_script_threshold",
      "reqd",
      frm.doc.is_group_script_limited
    );
    frm.set_df_property(
      "group_script_threshold_type",
      "reqd",
      frm.doc.is_group_script_limited
    );
  },
  is_group_script_max_limited: function (frm) {
    frm.set_df_property(
      "group_script_max_limit",
      "reqd",
      frm.doc.is_group_script_max_limited
    );
    frm.set_df_property(
      "group_script_max_limit_type",
      "reqd",
      frm.doc.is_group_script_max_limited
    );
  },
});
