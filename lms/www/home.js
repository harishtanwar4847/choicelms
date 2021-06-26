frappe.ready(function () {
  $(".btn-send")
    .off("click")
    .on("click", function () {
      var firstname = $('[name="firstname"]').val();
      var lastname = $('[name="lastname"]').val();
      var email = $('[name="email"]').val();
      var mobile = $('[name="mobile"]').val();
      console.log(firstname, lastname, mobile, email);
      if (
        !(project == "") &&
        !(prfile == "") &&
        !(prbudget == "") &&
        !(prdesc == "")
      ) {
        frappe.call({
          method: "lms.www.home.servercallmethod",
          args: {
            firstname: firstname,
            lastname: lastname,
            email: email,
            mobile: mobile,
          },
          callback: function (r) {
            console.log("here is r.message");
            console.log();
            if (r.message === "Project uploaded successfully.") {
              alert(
                "{{ _('Thank you for your input, our team will get back to you soon..') }}"
              );
              window.location.href = "/";
            } else {
              alert("{{ _('There were errors') }}");
              console.log(r.exc);
            }
            $(":input").val("");
          },
        });
      } else {
        alert("Every field is required.");
      }
    });
});
