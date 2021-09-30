import frappe

# Run it on mariadb console before migration
# SET GLOBAL event_scheduler=ON;


def execute():
    frappe.db.sql(
        """
     CREATE OR REPLACE EVENT day_past_due_update
     ON SCHEDULE EVERY 1 DAY
     DO
     update `tabLoan` set day_past_due = IF((select sum(unpaid_interest) as total_amount from `tabLoan Transaction` where transaction_type in ('Interest', 'Additional Interest', 'Penal Interest') and unpaid_interest >0 ),
     day_past_due+1, 0);
     """
    )
    frappe.db.commit()
