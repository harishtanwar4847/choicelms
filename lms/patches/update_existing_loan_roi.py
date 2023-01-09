import frappe


def execute():
    loans = frappe.get_all("Loan", fields=["name"])
    for l in loans:
        loan = frappe.get_doc("Loan", l.name)
        if loan.balance > 0:
            interest_configuration = frappe.db.get_value(
                "Interest Configuration",
                {
                    "lender": loan.lender,
                    "from_amount": ["<=", loan.balance],
                    "to_amount": [">=", loan.balance],
                },
                ["name", "base_interest", "rebait_interest"],
                as_dict=1,
            )
            loan.is_default = 1
            loan.custom_base_interest = interest_configuration["base_interest"]
            loan.base_interest = loan.custom_base_interest
            loan.custom_rebate_interest = interest_configuration["rebait_interest"]
            loan.rebate_interest = loan.custom_rebate_interest
            loan.save(ignore_permissions=True)
            frappe.db.commit()
