<h3>Dear {{ doc.full_name or "" }},</h3>

<h2>Congratulations!!</h2>

<p>Your loan amount has been credited in your account.</p>
<p>Check your balance - <a href="{{ frappe.utils.get_url() }}">Click Here</a> </p>
<p>Get account details - <a href="{{ frappe.utils.get_url() }}">Click Here</a></p>

<p>If you need any assistance please drop an e-mail to <a>reception@spark.loans.</a></p>

<p>We are happy to serve you.</p>

<p>Thanks,</p>
<p>The Spark Team	</p>
