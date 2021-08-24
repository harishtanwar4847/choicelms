import frappe


def execute():
    frappe.db.sql(
        """CREATE TABLE IF NOT EXISTS `tabSpark Push Notification` (
    `name` varchar(140) COLLATE utf8mb4_unicode_ci NOT NULL,
    `creation` datetime(6) DEFAULT NULL,
    `modified` datetime(6) DEFAULT NULL,
    `modified_by` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `owner` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `docstatus` int(1) NOT NULL DEFAULT 0,
    `parent` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `parentfield` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `parenttype` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `idx` int(8) NOT NULL DEFAULT 0,
    `title` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `screen_to_open` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `notification_type` varchar(140) COLLATE utf8mb4_unicode_ci DEFAULT 'Success',
    `message` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `_user_tags` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `_comments` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `_assign` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `_liked_by` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    PRIMARY KEY (`name`),
    KEY `parent` (`parent`),
    KEY `modified` (`modified`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci ROW_FORMAT=COMPRESSED"""
    )

    frappe.db.commit()
    path = frappe.get_app_path(
        "lms", "patches", "imports", "spark_push_notification.csv"
    )
    frappe.core.doctype.data_import.data_import.import_file(
        "Spark Push Notification", path, "Insert"
    )
