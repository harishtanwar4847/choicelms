import frappe


def execute():
    site_name = frappe.utils.get_site_base_path()
    site_name = site_name.replace("./", "")

    frappe.utils.execute_in_shell(
        "bench --site {site_name} set-config hostname spark.loans".format(
            site_name=site_name
        )
    )
