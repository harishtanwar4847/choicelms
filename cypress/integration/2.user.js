context("Set PIN", () => {
  before(() => {
    cy.delete_user(Cypress.config("dummy_user").email);
    cy.register_user(Cypress.config("dummy_user")).then((res) => {
      Cypress.config("token", res.body.data.token);
    });
  });

  it("auth method", () => {
    cy.api_call(
      "lms.user.set_pin",
      { pin: Cypress.config("dummy_user").pin },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("only post http method should be allowed", () => {
    cy.api_call(
      "lms.user.set_pin",
      { pin: Cypress.config("dummy_user").pin },
      "GET",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("invalid pin length", () => {
    cy.api_call("lms.user.set_pin", { pin: "11111" }, "POST", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property(
        "pin",
        "Should be atleast 4 in length."
      );
      cy.screenshot();
    });
  });

  it("valid hit", () => {
    cy.api_call(
      "lms.user.set_pin",
      { pin: Cypress.config("dummy_user").pin },
      "POST",
      {
        Authorization: Cypress.config("token"),
      }
    ).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "User PIN has been set");
      cy.screenshot();
    });
  });
});

context("KYC", () => {
  it("only get http method should be allowed", () => {
    cy.api_call("lms.user.kyc", {}, "POST", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.user.kyc", {}, "GET").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("field empty pan no", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "", birth_date: "12-12-1999", accept_terms: true },
      "GET",
      { Authorization: Cypress.config("token") }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("pan_no");
      expect(res.body.errors.pan_no).to.be.a("string");
      cy.screenshot();
    });
  });

  it("field empty birth date", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "ABCD2795", birth_date: "", accept_terms: true },
      "GET",
      { Authorization: Cypress.config("token") }
    ).then((res) => {
      expect(res.status).to.eq(422);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("birth_date");
      expect(res.body.errors.birth_date).to.be.a("string");
      cy.screenshot();
    });
  });

  it("accept terms false", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "ABCD2795", birth_date: "12-12-1999", accept_terms: false },
      "GET",
      { Authorization: Cypress.config("token") }
    ).then((res) => {
      expect(res.status).to.eq(401);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property(
        "message",
        "Please accept Terms and Conditions."
      );
      cy.screenshot();
    });
  });

  it("KYC not found", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "ABCD2795", birth_date: "12-12-1999", accept_terms: true },
      "GET",
      { Authorization: Cypress.config("token") }
    ).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "User KYC not found");
      cy.screenshot();
    });
  });

  it("Valid User KYC hit", () => {
    cy.valid_user_kyc_hit(Cypress.config("token")).then((res) => {
      // expect(res.body).to.eq({});
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "Success");
      cy.screenshot();
    });
  });
});

context("Securities", () => {
  it("only get http method should be allowed", () => {
    cy.api_call("lms.user.securities", {}, "POST", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("auth method", () => {
    cy.api_call("lms.user.securities", {}, "POST").then((res) => {
      expect(res.status).to.eq(403);
      cy.screenshot();
    });
  });

  it("Valid Securities hit", () => {
    cy.valid_user_kyc_hit(Cypress.config("token"));
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: Cypress.config("token"),
    }).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Success");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
});
