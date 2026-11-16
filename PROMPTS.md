# PROMPTS.md — AI Usage Log

This file is the record of AI use on this codebase. At the end of every
agent session, direct the agent to write the session log with this prompt:

> Append a session log to PROMPTS.md at the repo root, under today's date,
> newest entry at the top. Record every prompt I gave you this session, in
> order, including any corrections. End the entry with a short summary:
> the outcome, any places where I deviated from a recommended answer or
> asked follow-up questions, and anything that went sideways.

Two rules:

- Entries are added only by that prompt, never unprompted.
- New entries go at the top. Never rewrite or delete an old entry — the
  log is part of your work, and an honest log of a session that went
  sideways is worth more than a tidy one.

Each entry has this shape:

    ## YYYY-MM-DD — <one-line summary>

    ### Prompts
    1. ...

    ### Summary
    - **Outcome:** what was built and what was kept
    - **Deviations:** recommendations overridden, follow-up questions asked
    - **Sideways:** failures, wrong turns, and how they were caught

## 2026-11-15 — Product images: design interview, PRD and plan, handoff (no implementation)

### Prompts

1. `/grill-me` "i need to add real product images to the thoughttronix
   store. the images are already in the product-images folder in the
   project directory. products should display their uploaded images when
   available and use the existing placeholder when no image exists.
   employees need to be able to upload product images through the back
   office. invalid image files should be rejected with a clear error
   message. images should look consistent across the catalog, and the
   website should remain fast."
2. "a" — Q1, how many images: one optional image per product.
3. "b" — Q2, processing: resize to ≤ 1200 px and store as WebP once, at
   upload time; originals discarded.
4. "a" — Q3, consistency: fixed frame, cropped in the browser
   (`aspect-ratio` + `object-cover`).
5. "a" — Q4, frame shape: 4:5 portrait, also on the detail page.
6. "b" — Q5, invalid files: JPEG/PNG/WebP by contents, ≤ 10 MB, ≥ 800 px
   shortest side, one specific message per rule.
7. "b" — Q6, old files: deleted automatically via `transaction.on_commit`.
8. "c" — Q7, filenames: `products/<slug>-<random token>.webp`.
9. "c" — Q8, seed: pre-shrunk images committed as
   `products/seed_images/<slug>.webp`, loaded through the real upload path.
10. "a" — Q9, SyncRest uses the "No Text" image; guideline "product
    photos, not ads".
11. "c" — Q10, back office: styled field with preview and rules up front,
    plus a thumbnail column in the product list.
12. "b" — Q11, code location: validators on the model field
    (`products/validators.py`), processing in the model, one
    `display_image_url` property.
13. "change number 9: if an upload image is missing or unavailable, display
    the existing category placeholder instead of a broken image. keep the
    implementation simple an avoid unnecessary filesystem checks on every
    request."
14. "save both the prd and the plan"
15. "commit both files"
16. `/handoff` "the next session implements the design we just agreed"
17. "no do not commit HANDOFF.md because it is a temporary file. Please
    read the header of PROMPTS.md and follow its standard session-log
    instructions to document this Grill Me design session. do not begin
    implementation yet."

### Summary

- **Outcome:** A complete design for product images, with no code written.
  `prd/product-images.md` and `plans/product-images.md` (six phases) were
  committed to `main` in `fecf7f4`, which has not been pushed.
  `HANDOFF.md` was written for the next session, which will implement
  the design, and is deliberately left uncommitted as a temporary file.
  The `product-images/` source folder is still untracked; deleting or
  gitignoring it is deferred to Phase 6, where the user will be asked.
  Before asking anything, the agent explored the codebase. It found no
  media support or Pillow, 4:3 placeholder SVGs, and images only in the
  catalog and detail templates. It also found 13 source PNGs of about
  2 MB each, mostly 4:5. The agent viewed the ambiguous images to propose
  the image-to-product mapping.
- **Deviations:** All eleven answers matched the recommended option. The
  user changed one bundled default in Q12. Item #9 originally said a
  missing file shows a broken image; it now falls back to the category
  placeholder via a client-side `onerror`, with no server-side file
  checks. The SoulSear → Mark I mapping was put to the user in Q9, but
  the user answered only "a". The agent treated that silence as
  confirmation and said so. The user declined the offer to commit
  `HANDOFF.md`.
- **Sideways:**
  - The `grill-me` skill says to ask one question at a time. Q9 bundled
    the SyncRest choice with a request to confirm the mapping table. Q12
    bundled ten small defaults into one confirm-or-change question. That
    was efficient, but it departed from the skill's format, and the
    user's one correction came out of that bundle.
  - While writing the PRD and plan, the agent made three implementation
    calls that were not discussed in the interview. These were a
    `post_delete` receiver for file cleanup, `max_length=255` with a
    truncated slug, and a temporary-`MEDIA_ROOT` fixture applied to the
    existing seed tests. All three were reported after the files were
    saved, not before.
  - A `cd` inside a Bash call changed the session's working directory to
    `assets/images/placeholders`. The agent caught it from the
    environment update and switched to absolute paths. No files were
    affected.
  - The "~2 MB total" size for the seed images, and the ~100–200 KB per
    image, are estimates that the PRD repeats. They have not been
    measured; Phase 6 is where they get checked.

## 2026-10-05 — Discount codes: design interview, checkout/back-office implementation, store time zone

### Prompts

1. `/grill-me` "Customers should be able to enter discount codes at
   checkout. Codes can expire, retiring a code must not affect past
   orders, and the system should support both order-wide discounts and
   discounts for specific products."
2. "a" — Q1, discount value: percentage only.
3. "a" — Q2, targeting: a hand-picked product list, empty = order-wide.
4. "b" — Q3, order snapshot: order-level copy plus a per-line discount.
5. "b" — Q4, ending a code: optional `expires_at` plus an `is_active`
   switch.
6. "a" — Q5, usage limits: none.
7. "b" — Q6, entry: checkout form field plus an HTMX "Apply" preview.
8. "a" — Q7, a valid code that covers nothing in the cart: reject it.
9. "a" — Q8, a code that goes bad before placement: `place_order` raises
   `ValueError` and rolls back.
10. "b" — Q9, back office: list/create/edit tab, no delete.
11. "c" — Q10, seed: codes in every state plus past orders that used them.
12. "implement this feature"
13. "how can i manually verify the discount coupon feature in the browser?"
14. "uv run python manage.py seed"
15. "uv run python manage.py tailwind runserver"
16. "Commit and push the discount coupon feature with a commit message that
    says what changed."
17. "merge it into main and push"
18. "Based on our manual review of the discount coupon feature, identify one
    small but meaningful improvement we can make. Do not change anything
    yet. Tell me what you recommend and why."
19. "implement the time zone fix"
20. "commit and push it to main"
21. "restore it and restart the server"
22. "Append a session log to PROMPTS.md at the repo root, under today's
    date, newest entry at the top. Record every prompt I gave you this
    session, in order, including any corrections. End the entry with a
    short summary: the outcome, any places where I deviated from a
    recommended answer or asked follow up questions, and anything that went
    sideways."

### Summary

- **Outcome:** Discount codes shipped to `main` in `673a038`. They have a
  `DiscountCode` model, and `DiscountCode.objects.redeem()` is the single
  validity rule used by the checkout form, the HTMX preview and
  `place_order`. Per-line discounts are rounded half-up and copied onto
  `Order`/`OrderItem`, so retiring, editing or deleting a code never
  changes history. `place_order`'s formerly ignored `coupon_code` now
  works. Also added: an Apply preview at checkout, discount lines on the
  order pages, a "Discount codes" back-office tab, dashboard top-products
  revenue net of discounts, seed codes in every state plus orders that
  used them, migration `0004`, and 37 new tests. The follow-up `eaf1c3a`
  reads `TIME_ZONE` from `.env` (default `America/Chicago`) and labels
  expiry times with their zone, plus one test. Suite green at 238; ruff
  clean.
- **Deviations:** None from the interview. All ten answers matched the
  recommended option. At the end of the interview I offered to write a PRD
  and plan first; the user went straight to "implement this feature", so
  no `prd/` or `plans/` documents exist for discount codes. Follow-up
  questions: how to verify the feature manually in the browser (answered
  with a step-by-step walkthrough), and a request for one improvement
  "based on our manual review", although no results from that review were
  shared. The recommendation (the UTC expiry bug) was therefore inferred
  from the walkthrough, and that was said at the time. On "commit and
  push", the agent committed to a new `discount-codes` branch rather than
  pushing to `main`; the user then asked for the merge, which was a
  fast-forward. That branch still exists locally and on GitHub.
- **Sideways:**
  - During the interview the agent promised a `clean_discount_code()` form
    method. An existing test forbids imperative validation on
    `CheckoutForm`, so the check became a field validator built from the
    cart. The promised `usable()` queryset method was dropped as unused.
    Both changes were reported after implementation, not before.
  - During the interview the agent described the dashboard query it would
    change as "per-category revenue"; it is actually the top-products
    ranking. This was corrected in the implementation report.
  - The test suite caught a real bug. When a code went bad between form
    validation and placement, checkout re-rendered showing the discounted
    total with no error. The form's error now takes priority.
  - The agent's first throwaway-database run of the seed failed on a Unix
    temp path that Windows Python couldn't read; it worked after
    `cygpath`. The agent applied migration `0004` to the dev database
    without asking (reported afterwards). It ran `seed` against the dev
    database only when the user asked.
  - The manual-verification walkthrough itself had a hidden flaw. Step 4,
    "set Expires at to a minute from now", would have shown Expired at once
    for the wrong reason, because typed times were read as UTC. That is
    the bug the improvement prompt surfaced and `eaf1c3a` fixed.
  - After the time zone push, the dev server crashed on a stray `0.` typed
    into `orders/forms.py` in the editor. It was uncommitted, so nothing
    pushed was affected. The agent found it through the background-task
    notification and left it alone until the user said to restore the
    file, then restored it and restarted the server.

## 2026-09-19 — Featured products: model field, back-office form, catalog and detail badges

### Prompts

1. "i want you to add an is_featured field to the product model. make it a
   boolean field that defaults to false. do not make any changes to the
   website/templates yet."
2. "i added the is_featured field and ran the migration, but when i edit a
   product in the back office, i do not see a checkbox. why isnt the
   is_featured field appearing in the product form?"
3. "add it to the form"
4. "add a featured badge for featured products. i want the badge to show on
   both the catalog listing page and the product detail page."
5. "append a session log to PROMPTS.md at the repo root, under today's date,
   newest entry at the top. record every prompt i gave you this session, in
   order, including any corrections. end the entry with a short summary: the
   outcome, any places where i deviated from a recommended answer or asked
   follow up, questions, and anything that went sideways."

### Summary

- **Outcome:** `Product.is_featured` (`BooleanField`, default `False`) added
  after `is_available`, with migration `products/0003_product_is_featured.py`
  applied. `"is_featured"` added to `ProductForm.Meta.fields`; no template
  work was needed there, since the form template loops over all fields and
  `StyledModelForm` already styles checkboxes as DaisyUI toggles. A solid
  `badge-primary` "Featured" badge now renders in the catalog card badge row
  and on the detail page; the detail page's availability `<div>` was widened
  from bare `mt-4` to `mt-4 flex flex-wrap gap-2` so two badges sit side by
  side. Added a `featured_product` fixture to `conftest.py` and three tests
  (badge on detail, absent when not featured, exactly one on a two-product
  catalog). Suite green at 167 passed; ruff check and format clean.
- **Deviations:** Step 1's "no website/template changes yet" was read as
  covering the back-office form, so the field was deliberately left out of
  `ProductForm` — that is what prompt 2 went looking for. When asked, the
  diagnosis was given and the one-line fix was offered but held until prompt
  3 authorized it. Prompt 4 was scoped to the two customer-facing pages only;
  ordering and filtering by `is_featured` were flagged as possible follow-ons
  and not built.
- **Sideways:** No failures — nothing broke and no work was thrown away, but
  prompt 2 was an avoidable round trip. After step 1, the suggested next
  steps mentioned a `featured()` queryset method and the back-office form in
  passing, without stating plainly that `ProductForm.Meta.fields` is an
  explicit allowlist and the new field would therefore be invisible in the
  back office. Naming that consequence up front would have saved the
  debugging detour. Prompt 2 also attributed the field and migration to the
  user, when both had been done by the agent in step 1; immaterial to the
  diagnosis, so it was not corrected at the time.
