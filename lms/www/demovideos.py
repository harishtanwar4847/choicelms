import frappe
import utils

import lms


@frappe.whitelist(allow_guest=True)
def get_videos_list(page_no, latest_video, search_key=""):

    # latest video flag
    latest_video = int(latest_video)
    if latest_video:
        limit = 3
        # offset  = 0
    else:
        limit = 6
        offset = (int(page_no) - 1) * limit

    or_filters = {}
    if len(search_key.strip()) > 0:
        where = "where video_title LIKE '%{search_key}%' or video_description LIKE '%{search_key}%'".format(
            search_key=search_key
        )
    else:
        where = ""

    all_video_count = frappe.db.count("Youtube Id")
    # if latest_video:
    #     page_limit = "limit {}".format(limit)
    # else:
    #     page_limit = "limit {},{}".format(offset, limit)

    # videos_list = frappe.db.get_all("Youtube Id", fields=['*'], or_filters=or_filters, order_by="creation desc", start=offset, page_length=limit, debug=True)

    if latest_video:
        videos_list = frappe.db.sql(
            "SELECT * FROM (SELECT * FROM `tabYoutube Id` ORDER BY creation DESC LIMIT {}) sub {} ORDER BY creation DESC".format(
                limit, where
            ),
            as_dict=True,
        )
    else:
        videos_list = frappe.db.sql(
            "select * from `tabYoutube Id` {} order by creation desc limit {}, {}".format(
                where, offset, limit
            ),
            as_dict=True,
        )

    response = {
        "videos_list_response": videos_list,
        "page_no": page_no,
        "all_video_count": all_video_count if not latest_video else limit,
    }

    return utils.respondWithSuccess(data=response)
