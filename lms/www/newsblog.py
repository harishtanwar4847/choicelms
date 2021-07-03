import frappe


def get_context(context):
    context.blogs = frappe.db.sql(
        "select nb.title, nb.publishing_date, GROUP_CONCAT(bt.website_tags) as website_tags, nb.for_banner_view from `tabNews and Blog` as nb left join `tabBlog Tags` bt on (bt.parent = nb.name) where nb.name <> '{}' AND (website_tags in ('retain','Resources'))group by nb.name".format(
            frappe.form_dict.blog_name
        ),
        as_dict=True,
        debug=True,
    )
