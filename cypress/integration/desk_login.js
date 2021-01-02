context("Login", () => {
  beforeEach(() => {
    cy.request("/api/method/logout");
    cy.visit("/login");
    cy.location().should((loc) => {
      expect(loc.pathname).to.eq("/login");
    });
  });

  it("greets with login screen", () => {
    cy.get(".page-card-head").contains("Login");
    cy.screenshot();
  });

  it("validates password", () => {
    cy.get("#login_email").type("Administrator");
    cy.get(".btn-login").click();
    cy.location().should((loc) => {
      expect(loc.pathname).to.eq("/login");
    });
    cy.screenshot();
  });

  it("validates email", () => {
    cy.get("#login_password").type("qwe");
    cy.get(".btn-login").click();
    cy.location().should((loc) => {
      expect(loc.pathname).to.eq("/login");
    });
    cy.screenshot();
  });

  it("logs in using correct credentials", () => {
    cy.get("#login_email").type("Administrator");
    cy.get("#login_password").type(Cypress.config("adminPassword"));

    cy.get(".btn-login").click();
    cy.location().should((loc) => {
      expect(loc.pathname).to.eq("/desk");
    });
    cy.window().its("frappe.session.user").should("eq", "Administrator");
    cy.screenshot();
  });

  it("shows invalid login if incorrect credentials", () => {
    cy.get("#login_email").type("Administrator");
    cy.get("#login_password").type("qwer");

    cy.get(".btn-login").click();
    cy.get(".page-card-head").contains("Invalid Login. Try again.");
    cy.location().should((loc) => {
      expect(loc.pathname).to.eq("/login");
    });
    cy.screenshot();
  });
});
