import frappe
import utils

import lms


@frappe.whitelist(allow_guest=True)
def get_videos_list(page_no, latest_video, search_key=""):
    latest_video = int(latest_video)
    if latest_video:
        limit = 3
        offset = 0
    else:
        limit = 6
        offset = (int(page_no) - 1) * limit

    if len(search_key.strip()) > 0:
        where = "where video_title LIKE '%{search_key}%' or video_description LIKE '%{search_key}%'".format(
            search_key=search_key
        )
    else:
        where = ""

    if latest_video:
        # latest = latest created 3 records, also apply search in between recent 3 only.
        videos_list = frappe.db.sql(
            "SELECT * FROM (SELECT * FROM `tabYoutube Id` ORDER BY creation DESC LIMIT {}) sub {} ORDER BY creation DESC".format(
                limit, where
            ),
            as_dict=True,
        )

        all_video_count = len(videos_list)
    else:
        videos_list = frappe.db.sql(
            "select * from `tabYoutube Id` {} order by creation desc limit {}, {}".format(
                where, offset, limit
            ),
            as_dict=True,
        )

        all_video_count = frappe.db.sql(
            "select count(name) as total_video from `tabYoutube Id` {}".format(where),
            as_dict=True,
        )[0]["total_video"]

    response = {
        "videos_list_response": videos_list,
        "page_no": page_no,
        "all_video_count": all_video_count,
    }

    return utils.respondWithSuccess(data=response)
