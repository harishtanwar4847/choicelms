context("API => ping", () => {
  it("ping api hit", () => {
    cy.apicall("frappe.ping").then((res) => {
      expect(res.status).to.eq(200);
      expect(res.body).to.have.property("message", "pong");
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });

  it("ping api hit dusra", () => {
    cy.apicall("frappe.ping").then((res) => {
      expect(res.body).to.have.property("message", "pong");
      expect(res.status).to.eq(200);
      expect(res.body.message).to.be.a("string");
      cy.screenshot();
    });
  });
});
