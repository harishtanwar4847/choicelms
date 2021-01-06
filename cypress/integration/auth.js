context("Login API", () => {
  it("only post http method should be allowed", () => {
    cy.api_call("lms.auth.login", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("mobile number required", () => {
    cy.api_call("lms.auth.login", {}, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("mobile");
      expect(res.body.errors.mobile).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid hit with mobile number", () => {
    cy.api_call(
      "lms.auth.login",
      { mobile: "9876543210", accept_terms: true },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "OTP Sent");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid hit with pin", () => {
    cy.admin_api_call("frappe.client.delete", {
      doctype: "User",
      name: "0000000000@example.com",
    });
    cy.api_call(
      "lms.auth.register",
      {
        first_name: "abcd",
        last_name: "efgh",
        mobile: "0000000000",
        email: "0000000000@example.com",
        firebase_token: "asdf",
      },
      "POST"
    ).then((res) => {
      var token = res.body.data.token;
      cy.api_call("lms.user.set_pin", { pin: "1234" }, "POST", {
        Authorization: token,
      }).then((res) => {
        cy.api_call(
          "lms.auth.login",
          {
            mobile: "0000000000",
            firebase_token: "asdf",
            pin: "1234",
            accept_terms: true,
          },
          "POST"
        ).then((res) => {
          expect(res.status).to.eq(200);
          // expect(res.body).to.eq({})
          expect(res.body).to.have.property(
            "message",
            "Logged in Successfully"
          );
          expect(res.body.message).to.be.a("string");
          cy.screenshot();
        });
      });
    });
  });
});

context("Verify OTP Api", () => {
  it("only post http method should be allowed", () => {
    cy.api_call("lms.auth.verify_otp", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid otp", () => {
    cy.api_call(
      "lms.auth.login",
      { mobile: "9876543210", accept_terms: true },
      "POST"
    );
    cy.admin_api_call("frappe.client.get_list", {
      doctype: "User Token",
      fields: ["token"],
    }).then((res) => {
      var otp = res.body.message[0].token;
      cy.api_call(
        "lms.auth.verify_otp",
        { mobile: "9876543210", otp: otp, firebase_token: "janabe" },
        "POST"
      ).then((res) => {
        expect(res.status).to.eq(404);
        expect(res.body).to.have.property("message", "User not found.");
        expect(res.body.message).to.be.a("string");
        cy.screenshot();
      });
    });
  });
});

context("Register API", () => {
  it("only post http method should be allowed", () => {
    cy.api_call("lms.auth.login", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("first name required", () => {
    cy.api_call("lms.auth.register", { email: "" }, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("first_name");
      expect(res.body.errors.first_name).to.be.a("string");
      cy.screenshot();
    });
  });

  it("mobile number required", () => {
    cy.api_call("lms.auth.register", { email: "" }, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("mobile");
      expect(res.body.errors.mobile).to.be.a("string");
      cy.screenshot();
    });
  });

  it("email required", () => {
    cy.api_call("lms.auth.register", { email: "" }, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("email");
      expect(res.body.errors.email).to.be.a("string");
      cy.screenshot();
    });
  });

  it("firebase token required", () => {
    cy.api_call("lms.auth.register", { email: "" }, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body.message).to.be.a("string");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("firebase_token");
      expect(res.body.errors.firebase_token).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid hit with right credentials", () => {
    cy.admin_api_call("frappe.client.delete", {
      doctype: "User",
      name: "1111111111@example.com",
    });
    cy.api_call(
      "lms.auth.register",
      {
        first_name: "abcd",
        last_name: "efgh",
        mobile: "1111111111",
        email: "1111111111@example.com",
        firebase_token: "asdf",
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "Registered Successfully.");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
});
