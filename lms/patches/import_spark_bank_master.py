import frappe


def execute():
    frappe.db.sql("TRUNCATE `tabSpark Bank Master`")
    frappe.db.commit()
    frappe.db.sql(
        """
        LOAD DATA LOCAL INFILE '{file_path}'
        INTO TABLE `tabSpark Bank Master`
        FIELDS TERMINATED BY ','
        ENCLOSED BY '"'
        LINES TERMINATED BY \'\\n\'
        IGNORE 1 ROWS;
    """.format(
            file_path=frappe.get_app_path(
                "lms", "patches", "imports", "spark_bank_names.csv"
            )
        ),
        debug=True,
    )
