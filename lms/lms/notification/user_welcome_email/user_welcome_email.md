<h3>Hi {{ doc.full_name or "" }}</h3>

<p>Thanks for creating an account on Spark.loans.</p>

<p> Your username is {{ doc.username }}.

<p>In order to enjoy our services, you need to first complete your KYC.</p>
<p>Complete KYC - <a href="{{ frappe.utils.get_url() }}">Click Here</a></p>

<b>You can access –</b>

<p>Our dashboard on <a href="{{ frappe.utils.get_url() }}">Click Here</a><p>
<p>Know more about LAS on <a href="{{ frappe.utils.get_url() }}">Click Here</a></p>
<p>Know our easy 3-step process to get loan - <a href="{{ frappe.utils.get_url() }}">Click Here</a> </p>

<p>We look forward to seeing you soon.</p>

<p>Thanks,</p>
<p>The Spark Team</p>
