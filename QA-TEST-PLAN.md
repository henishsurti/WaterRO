# AquaFlow V9 QA Test Plan

## Smoke
- [ ] App loads with no console errors.
- [ ] Admin login succeeds.
- [ ] Technician login succeeds.
- [ ] Invalid credentials are rejected.
- [ ] Logout clears the session.
- [ ] Server/local mode indicator is accurate.

## Customers
- [ ] Create customer.
- [ ] Edit customer.
- [ ] Mark active/inactive.
- [ ] Delete customer with confirmation.
- [ ] Invalid phone/email/date values are blocked.

## RO
- [ ] Create/edit/delete RO.
- [ ] RO cannot reference a missing customer.
- [ ] Service form filters RO by customer.

## AMC
- [ ] Create/edit/delete AMC.
- [ ] AMC dates and amount validate.
- [ ] Expiry is visible in dashboard/notifications.

## Services
- [ ] Create service and assign active technician.
- [ ] Technician sees assigned work only.
- [ ] Start -> in progress -> complete workflow works.
- [ ] Parts/labour/discount totals are correct.
- [ ] Before/after photos can be captured on supported browsers.
- [ ] Completion updates RO service dates and AMC usage.

## Data
- [ ] Export JSON.
- [ ] Restore JSON.
- [ ] Diagnostics report no broken references.
- [ ] API sync rejects broken relationships.
- [ ] SQLite foreign key integrity check returns `ok`.

## Responsive/accessibility
- [ ] 360px phone width.
- [ ] 768px tablet.
- [ ] 1366px desktop.
- [ ] Keyboard focus visible.
- [ ] Escape closes dialogs.
- [ ] Reduced-motion preference respected.
