context("Login API", () => {
  it("only post http method should be allowed", () => {
    cy.apicall("lms.auth.login", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("mobile number required", () => {
    cy.apicall("lms.auth.login", {}, "POST").then((res) => {
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
    cy.apicall(
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
    cy.apicall(
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
      cy.apicall("lms.user.set_pin", { pin: "1234" }, "POST", {
        Authorization: token,
      }).then((res) => {
        cy.apicall(
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
          cy.apicall(
            "frappe.client.delete",
            { doctype: "User", name: "0000000000@example.com" },
            "POST",
            {
              Authorization:
                "token " +
                Cypress.config("adminApiKey") +
                ":" +
                Cypress.config("adminApiSecret"),
            }
          );
        });
      });
    });
  });
});

context("Verify OTP Api", () => {
  it("only post http method should be allowed", () => {
    cy.apicall("lms.auth.verify_otp", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("valid otp", () => {
    cy.apicall(
      "lms.auth.login",
      { mobile: "9876543210", accept_terms: true },
      "POST"
    );
    cy.apicall(
      "frappe.client.get_list",
      { doctype: "User Token", fields: ["token"] },
      "POST",
      {
        Authorization:
          "token " +
          Cypress.config("adminApiKey") +
          ":" +
          Cypress.config("adminApiSecret"),
      }
    ).then((res) => {
      var otp = res.body.message[0].token;
      cy.apicall(
        "lms.auth.verify_otp",
        { mobile: "9876543210", otp: otp, firebase_token: "janabe" },
        "POST"
      ).then((res) => {
        expect(res.status).to.eq(404);
        expect(res.body).to.have.property("message", "Customer not found");
        expect(res.body.message).to.be.a("string");
        cy.screenshot();
      });
    });
  });
});

context("Register API", () => {
  it("only post http method should be allowed", () => {
    cy.apicall("lms.auth.login", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("first name required", () => {
    cy.apicall("lms.auth.register", { email: "" }, "POST").then((res) => {
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
    cy.apicall("lms.auth.register", { email: "" }, "POST").then((res) => {
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
    cy.apicall("lms.auth.register", { email: "" }, "POST").then((res) => {
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
    cy.apicall("lms.auth.register", { email: "" }, "POST").then((res) => {
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
    cy.apicall(
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
      cy.apicall(
        "frappe.client.delete",
        { doctype: "User", name: "1111111111@example.com" },
        "POST",
        {
          Authorization:
            "token " +
            Cypress.config("adminApiKey") +
            ":" +
            Cypress.config("adminApiSecret"),
        }
      );
    });
  });
});
