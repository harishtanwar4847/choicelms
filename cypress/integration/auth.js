context("Login API - login with OTP", () => {
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

  it("invalid mobile number length", () => {
    cy.api_call("lms.auth.login", { mobile: "12345678912" }, "POST").then(
      (res) => {
        expect(res.status).to.eq(422);
        expect(res.body).to.have.property("message", "Validation Error");
        expect(res.body).to.have.property("errors");
        expect(res.body.errors).to.be.a("object");
        expect(res.body.errors).to.have.property("mobile");
        expect(res.body.errors.mobile).to.be.a("string");
        expect(res.body.errors.mobile).to.eq("Should be atleast 10 in length.");
        cy.screenshot();
      }
    );
  });

  it("accept terms required", () => {
    cy.api_call(
      "lms.auth.login",
      { mobile: Cypress.config("dummy_user").mobile },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(401);
      expect(res.body).to.have.property(
        "message",
        "Please accept Terms of Use and Privacy Policy."
      );
      expect(res.body.message).to.be.a("string");
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
});

context("Login Api - login with PIN", () => {
  it("firebase token required", () => {
    cy.api_call(
      "lms.auth.login",
      {
        mobile: Cypress.config("dummy_user").mobile,
        pin: Cypress.config("dummy_user").pin,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("firebase_token");
      expect(res.body.errors.firebase_token).to.be.a("string");
      cy.screenshot();
    });
  });

  it("invalid pin length", () => {
    cy.api_call(
      "lms.auth.login",
      {
        mobile: Cypress.config("dummy_user").mobile,
        pin: "11111",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("pin");
      expect(res.body.errors.pin).to.be.a("string");
      expect(res.body.errors.pin).to.eq("Should be atleast 4 in length.");
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

  it("invalid pin - attempt 1", () => {
    cy.api_call(
      "lms.auth.login",
      {
        mobile: Cypress.config("dummy_user").mobile,
        pin: "1111",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(401);
      expect(res.body).to.have.property(
        "message",
        "Incorrect PIN. 1 invalid attempt."
      );
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("invalid pin - attempt 2", () => {
    cy.api_call(
      "lms.auth.login",
      {
        mobile: Cypress.config("dummy_user").mobile,
        pin: "1111",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(401);
      expect(res.body).to.have.property(
        "message",
        "Incorrect PIN. 2 invalid attempts."
      );
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("invalid pin - attempt 3", () => {
    cy.api_call(
      "lms.auth.login",
      {
        mobile: Cypress.config("dummy_user").mobile,
        pin: "1111",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(401);
      expect(res.body).to.have.property(
        "message",
        "Incorrect PIN. 3 invalid attempts."
      );
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("invalid pin - attempt 4", () => {
    cy.api_call(
      "lms.auth.login",
      {
        mobile: Cypress.config("dummy_user").mobile,
        pin: "1111",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(401);
      expect(res.body).to.have.property(
        "message",
        "Your account has been locked and will resume after 60 seconds"
      );
      expect(res.body.message).to.be.a("string");
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

  it("otp required", () => {
    cy.api_call(
      "lms.auth.verify_otp",
      {
        mobile: Cypress.config("dummy_user").mobile,
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("otp");
      expect(res.body.errors.otp).to.be.a("string");
      cy.screenshot();
    });
  });

  it("firebase token required", () => {
    cy.api_call(
      "lms.auth.verify_otp",
      { mobile: Cypress.config("dummy_user").mobile, otp: "1111" },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("firebase_token");
      expect(res.body.errors.firebase_token).to.be.a("string");
      cy.screenshot();
    });
  });

  it("invalid otp length", () => {
    cy.api_call(
      "lms.auth.verify_otp",
      {
        mobile: Cypress.config("dummy_user").mobile,
        otp: "11111",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("otp");
      expect(res.body.errors.otp).to.be.a("string");
      expect(res.body.errors.otp).to.eq("Should be atleast 4 in length.");
      cy.screenshot();
    });
  });

  it("invalid otp attempts", () => {
    cy.delete_dummy_user();
    cy.api_call(
      "lms.auth.login",
      { mobile: Cypress.config("dummy_user").mobile, accept_terms: true },
      "POST"
    );
    cy.api_call(
      "lms.auth.verify_otp",
      {
        mobile: Cypress.config("dummy_user").mobile,
        otp: "1111",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(401);
      expect(res.body).to.have.property("message", "Invalid OTP.");
      expect(res.body.message).to.be.a("string");
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
      cy.api_call(
        "lms.auth.verify_otp",
        {
          mobile: Cypress.config("dummy_user").mobile,
          otp: res.body.message[0].token,
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
  before(() => {
    cy.delete_dummy_user();
  });

  it("only post http method should be allowed", () => {
    cy.api_call("lms.auth.login", {}, "GET").then((res) => {
      expect(res.status).to.eq(405);
      expect(res.body).to.have.property("message", "Method not allowed");
      cy.screenshot();
    });
  });

  it("first name required", () => {
    cy.api_call(
      "lms.auth.register",
      {
        first_name: "",
        last_name: Cypress.config("dummy_user").last_name,
        mobile: Cypress.config("dummy_user").mobile,
        email: Cypress.config("dummy_user").email,
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("first_name");
      expect(res.body.errors.first_name).to.be.a("string");
      cy.screenshot();
    });
  });

  it("first name all characters to be alphabetic", () => {
    cy.api_call(
      "lms.auth.register",
      {
        first_name: "Iccha11",
        last_name: Cypress.config("dummy_user").last_name,
        mobile: Cypress.config("dummy_user").mobile,
        email: Cypress.config("dummy_user").email,
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
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
    cy.api_call(
      "lms.auth.register",
      {
        first_name: Cypress.config("dummy_user").first_name,
        last_name: Cypress.config("dummy_user").last_name,
        mobile: "",
        email: Cypress.config("dummy_user").email,
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
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
    cy.api_call(
      "lms.auth.register",
      {
        first_name: Cypress.config("dummy_user").first_name,
        last_name: Cypress.config("dummy_user").last_name,
        mobile: Cypress.config("dummy_user").mobile,
        email: "",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
      expect(res.status).to.eq(422);
      expect(res.body).to.have.property("message", "Validation Error");
      expect(res.body).to.have.property("errors");
      expect(res.body.errors).to.be.a("object");
      expect(res.body.errors).to.have.property("email");
      expect(res.body.errors.email).to.be.a("string");
      cy.screenshot();
    });
  });

  it("Invalid email", () => {
    cy.api_call(
      "lms.auth.register",
      {
        first_name: Cypress.config("dummy_user").first_name,
        last_name: Cypress.config("dummy_user").last_name,
        mobile: Cypress.config("dummy_user").mobile,
        email: "test@ddd",
        firebase_token: Cypress.config("dummy_user").firebase_token,
      },
      "POST"
    ).then((res) => {
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
    cy.api_call(
      "lms.auth.register",
      {
        first_name: Cypress.config("dummy_user").first_name,
        last_name: Cypress.config("dummy_user").last_name,
        mobile: Cypress.config("dummy_user").mobile,
        email: Cypress.config("dummy_user").email,
        firebase_token: "",
      },
      "POST"
    ).then((res) => {
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
