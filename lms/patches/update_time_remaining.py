import frappe


def execute():
    frappe.db.sql(
        """
     CREATE OR REPLACE EVENT test_event_03
     ON SCHEDULE EVERY 1 SECOND
     DO
     update `tabLoan Margin Shortfall` set time_remaining = IF(status in ("Pending","Request Pending", "Sell Triggered"), SEC_TO_TIME(TIMESTAMPDIFF(second, CURRENT_TIMESTAMP, deadline)), "00:00:00") where deadline > CURRENT_TIMESTAMP;
     """
    )
    frappe.db.commit()
