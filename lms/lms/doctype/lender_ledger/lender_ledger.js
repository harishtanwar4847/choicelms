// Copyright (c) 2020, Atrina Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Lender Ledger', {
	// refresh: function(frm) {

	// }
	validate:function(frm) {
		frm.set_df_property('lender', 'reqd', frm.doc.share_owner==='Lender');
	}
});
