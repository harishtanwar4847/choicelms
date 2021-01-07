context("Set PIN", () => {
  var token = null;
  before(() => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      token = res.body.data.token;
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
        Authorization: token,
      }
    ).then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("valid hit", () => {
    cy.api_call(
      "lms.user.set_pin",
      { pin: Cypress.config("dummy_user").pin },
      "POST",
      {
        Authorization: token,
      }
    ).then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "User PIN has been set");
      cy.screenshot();
    });
  });
});

context("KYC", () => {
  var token = null;
  before(() => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      token = res.body.data.token;
    });
  });

  it("only get http method should be allowed", () => {
    cy.api_call("lms.user.kyc", {}, "POST", { Authorization: token }).then(
      (res) => {
        expect(res.status).to.eq(405);
        expect(res.body).to.have.property("message", "Method not allowed");
        cy.screenshot();
      }
    );
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
      { Authorization: token }
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
      { Authorization: token }
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
      { Authorization: token }
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
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(404);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "User KYC not found");
      cy.screenshot();
    });
  });

  it("Valid User KYC hit", () => {
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "AAKHR7426K", birth_date: "01-01-1970", accept_terms: true },
      "GET",
      { Authorization: token }
    ).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Success");
      cy.screenshot();
    });
  });
});

context("Securities", () => {
  var token = null;
  before(() => {
    cy.delete_dummy_user();
    cy.register_dummy_user().then((res) => {
      token = res.body.data.token;
    });
  });

  it("only get http method should be allowed", () => {
    cy.api_call("lms.user.securities", {}, "POST", {
      Authorization: token,
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
    cy.api_call(
      "lms.user.kyc",
      { pan_no: "AAKHR7426K", birth_date: "01-01-1970", accept_terms: true },
      "GET",
      { Authorization: token }
    );
    cy.api_call("lms.user.securities", {}, "GET", {
      Authorization: token,
    }).then((res) => {
      expect(res.status).to.eq(200);
      // expect(res.body).to.eq({});
      expect(res.body).to.have.property("message", "Success");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
});
