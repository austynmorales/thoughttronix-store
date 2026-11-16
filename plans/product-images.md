# Implementation Plan: The ThoughtTronix Store — Product Images

*Companion to `prd/product-images.md`. The PRD owns the requirements; this plan owns the sequence. Where a task says "per the PRD," the PRD's wording is authoritative — do not improvise alternatives. The suite must be green at every phase boundary.*

---

## Phase 1 — Tracer Bullet: One Image, Every Layer

**Goal:** One uploaded image appears on one product's catalog card, served from `media/` — proof that the dependency, settings, model field, URL serving, and template all connect before any rule or polish is added.

**Tasks:**
1. `uv add pillow`.
2. Settings: `MEDIA_ROOT = BASE_DIR / "media"`, `MEDIA_URL = "media/"`. Serve media in `config/urls.py` via `static()` when `DEBUG` is on. Add `media/` to `.gitignore`.
3. Add `Product.image` — `ImageField(blank=True, max_length=255)` with an `upload_to` function producing `products/<slug>-<random token>.webp` (truncate the slug so the path fits the column). Generate the migration.
4. Add `image` to `ProductAdmin` (it is a ModelAdmin field automatically; confirm it renders).
5. Add `Product.display_image_url`: image URL if present, else the static URL of `category.placeholder_image`.
6. Catalog card uses `display_image_url` (temporarily inline — the shared partial comes in Phase 4).
7. Test fixture: a `conftest.py` fixture that points `MEDIA_ROOT` at pytest's `tmp_path` (via `settings`), plus a helper that builds an in-memory image with Pillow. Apply the media fixture to the existing seed tests now, so nothing ever writes to the real `media/`.
8. Tests: `display_image_url` returns the placeholder without an image and the media URL with one.

**Verification.** *Automated:* full suite green, including the existing seed tests. *Manual:* upload any image through `/admin/` to one product; see it on the catalog card; clear it and see the placeholder return.

**Out of bounds:** validation, resizing, WebP, cleanup, back-office form. The file is stored exactly as uploaded for one phase.

---

## Phase 2 — Validation

**Goal:** Every entry point rejects invalid images with the PRD's specific messages.

**Tasks:**
1. **Validators first:** `products/validators.py` — one plain function per PRD rule (real format JPEG/PNG/WebP read from contents; ≤ 10 MB; ≤ 50 megapixels from the header before decoding; shortest side ≥ 800 px). Messages per the PRD's table. Unit tests for each, written alongside: accepts a valid image, rejects the invalid case, asserts the message text. Include a GIF renamed to `.png`.
2. Attach them via `Product.image`'s `validators=[...]`; regenerate the migration.
3. Test that the Django admin rejects an invalid upload (proves the rules live on the model, not a form).

**Verification.** *Automated:* PRD testing priorities 1 and 6. *Manual:* in the admin, upload a small icon, a GIF, and a valid PNG; read each message.

**Out of bounds:** processing (images are still stored as uploaded), back-office form.

---

## Phase 3 — Processing and Cleanup

**Goal:** Every stored image is a normalized WebP under a fresh name, and replaced or orphaned files are deleted safely.

**Tasks:**
1. A `Product` model method that normalizes the assigned image per the PRD: `exif_transpose`, resize to ≤ 1200 px longest side (never upscale), first frame only, transparency preserved, WebP at quality 85, no metadata.
2. Call it from `save()` only when the image has changed. Track the stored image name when the instance is loaded (e.g. in `from_db`/`__init__`) and compare on save.
3. Cleanup: when the image changes or is cleared, schedule deletion of the old file with `transaction.on_commit`. For product deletion use a `post_delete` receiver (also on `on_commit`) — it fires for queryset deletes too, which `Model.delete()` overrides would miss (admin bulk delete, `seed`'s wipe).
4. Tests per PRD priorities 2 and 3: WebP output, dimensions, no upscaling, orientation, stripped EXIF, alpha preserved, filename pattern, no reprocessing on unrelated edits; replace/clear/delete remove the old file after commit; a rolled-back save removes nothing (use `django_capture_on_commit_callbacks`).

**Verification.** *Automated:* PRD priorities 2–3. *Manual:* upload one of the 2 MB PNGs via the admin; confirm a ~100–200 KB `.webp` in `media/products/`; replace it and confirm the old file is gone.

**Out of bounds:** template polish, back-office form.

---

## Phase 4 — Storefront Display

**Goal:** Consistent, fast, never-broken images across the catalog and detail pages.

**Tasks:**
1. Read `docs/TEMPLATES.md` before touching templates.
2. Create `templates/products/partials/_product_image.html` per the PRD: 4:5 frame (`aspect-ratio` + `object-cover`), `width`/`height`, `alt` = product name, a `lazy` toggle, and the `onerror` placeholder fallback.
3. Use it on the catalog card (lazy) and the detail page (eager). Remove the Phase 1 inline markup.
4. Tests per PRD priority 4: both pages render the partial; the fallback attribute carries the category placeholder URL; catalog images are lazy and the detail image is not.

**Verification.** *Automated:* PRD priority 4. *Manual:* catalog grid is even with a mix of photos and placeholders; delete a file from `media/products/` by hand and confirm the placeholder appears instead of a broken icon; check DevTools Network that below-the-fold images load on scroll.

**Out of bounds:** back-office screens.

---

## Phase 5 — Back Office

**Goal:** Employees upload, preview, replace, and remove images from the existing product screens.

**Tasks:**
1. Add `image` to `ProductForm.Meta.fields`. Extend `StyledModelForm` to give the file widget DaisyUI `file-input` classes; set help text stating the upload rules.
2. Product form template: `enctype="multipart/form-data"`; an image-field template showing the current image/placeholder preview via the shared partial, the file input, a "Remove image" checkbox, help text, and errors beside the field. Ensure the create/update views pass `request.FILES` (the generic CBVs do).
3. Product list: thumbnail column via the shared partial (lazy).
4. Tests per PRD priority 5: form is multipart; valid upload saves; invalid upload re-renders with the field error and other values preserved; "Remove image" clears; non-staff still blocked.

**Verification.** *Automated:* PRD priority 5. *Manual:* as `employee`, upload a valid photo to a placeholder product; try a too-small image and read the error with your other edits intact; remove an image; scan the list's thumbnail column.

**Out of bounds:** seed images.

---

## Phase 6 — Seed Images and Finish

**Goal:** The demo world ships with real images, reproducibly; docs reflect what was built.

**Tasks:**
1. One-time conversion (a throwaway script, not committed): resize each mapped PNG from `product-images/` to ≤ 1200 px and save as high-quality WebP at `products/seed_images/<slug>.webp`, per the PRD's mapping table. Confirm total ≈ 2 MB. Do not commit `product-images/` (add it to `.gitignore` or delete it after conversion — confirm with the user first).
2. Extend `seed`: empty `media/products/`, then for each mapped product attach its seed image as a Django `File`, call `full_clean()` and `save()` — the real upload path.
3. Extend seed tests per PRD priority 7: still idempotent; the twelve mapped products have images, the others do not.
4. Update `CLAUDE.md` (layout: `media/`, `products/seed_images/`, `products/validators.py`; the employee content guideline) and `README.md` as needed. Append a `PROMPTS.md` entry for this work — append only, never rewrite.
5. Sweep: Ruff clean, full suite green, `seed` run twice by hand.

**Verification.** *Automated:* full suite green. *Manual:* `uv run python manage.py seed`; browse every category; confirm the twelve images, the placeholders elsewhere, and an even grid; run `seed` again and confirm `media/products/` holds exactly twelve files.

**Out of bounds:** nothing new — galleries, `srcset`, and production media serving are explicitly out of scope per the PRD.
