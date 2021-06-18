<h3>Dear {{ doc.full_name or "" }},</h3>
<p>Your {{doc.get("otp_info").get("token_type")}} for Spark.Loans is {{doc.get("otp_info").get("token")}}. Do not share your {{doc.get("otp_info").get("token_type")}} with anyone.<p>
<p>Thanks,</p>
<p>The Spark Team	</p>
