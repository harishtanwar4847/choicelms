frappe.listview_settings['Security Price'] = {
	onload: function(listview) {
		listview.page.add_inner_button(__("Update Prices"), function() {
			frappe.call({
                method: 'lms.lms.doctype.security_price.security_price.update_all_security_prices',
                args: {
                    show_progress: true
                },
                freeze: true,
            })
		});
	}
};