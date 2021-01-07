context("Login API", () => {
  it("only post http method should be allowed", () => {
    cy.api_call("lms.auth.login", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("mobile number required", () => {
    cy.api_call("lms.auth.login", {}, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
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
      { mobile: Cypress.config("dummy_user").mobile, accept_terms: true },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "OTP Sent");
      cy.screenshot();
    });
  });

  it("valid hit with pin", () => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      cy.api_call(
        "lms.user.set_pin",
        { pin: Cypress.config("dummy_user").pin },
        "POST",
        {
          Authorization: res.body.data.token,
        }
      );
    });
    cy.api_call(
      "lms.auth.login",
      {
        mobile: Cypress.config("dummy_user").mobile,
        firebase_token: Cypress.config("dummy_user").firebase_token,
        pin: Cypress.config("dummy_user").pin,
        accept_terms: true,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "Logged in Successfully");
      cy.screenshot();
    });
  });
});

context("Verify OTP Api", () => {
  it("only post http method should be allowed", () => {
    cy.api_call("lms.auth.verify_otp", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("valid otp", () => {
    cy.delete_dummy_user();
    cy.api_call(
      "lms.auth.login",
      { mobile: Cypress.config("dummy_user").mobile, accept_terms: true },
      "POST"
    );
    cy.admin_api_call("frappe.client.get_list", {
      doctype: "User Token",
      fields: ["token"],
      filters: {
        entity: Cypress.config("dummy_user").mobile,
        token_type: "OTP",
        used: 0,
      },
    }).then((res) => {
      var otp = res.body.message[0].token;
      cy.api_call(
        "lms.auth.verify_otp",
        {
          mobile: Cypress.config("dummy_user").mobile,
          otp: otp,
          firebase_token: Cypress.config("dummy_user").firebase_token,
        },
        "POST"
      ).then((res) => {
        expect(res.status).to.eq(404);
        expect(res.body).to.have.property("message", "User not found.");
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
      cy.screenshot();
    });
  });

  it("first name required", () => {
    cy.api_call("lms.auth.register", { email: "" }, "POST").then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
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
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("firebase_token");
      expect(res.body.errors.firebase_token).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid hit with right credentials", () => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "Registered Successfully.");
      cy.screenshot();
    });
  });

  it("register using existing credentials", () => {
    cy.register_dummy_user().then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property(
        "mobile",
        "Mobile already taken"
      );
      expect(res.body.errors).to.have.property("email", "Email already taken");
      cy.screenshot();
    });
  });
});
