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
