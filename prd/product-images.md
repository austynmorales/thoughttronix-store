# PRD: The ThoughtTronix Store — Product Images

*Commissioned by ThoughtTronix Product Management. "Your Thoughts, Our Business."*

*Extends `prd/core-platform.md`, which deferred media handling ("this arrives later"). Where this document and the core PRD disagree about images, this document wins; everything else in the core PRD stands.*

---

## Problem Statement

Every product in the ThoughtTronix catalog is currently represented by a category illustration. A customer considering a MindSync Duo sees the same glowing brain icon as a customer considering a MindSync Lite, which our conversion team describes as "a missed opportunity to make them feel something specific."

Marketing has produced real product imagery for twelve products. It sits in a folder. Employees have no way to add, replace, or remove a product's image, and if they could, nothing would stop them uploading a 40 MB TIFF, a screenshot of a spreadsheet, or a phone photo containing the GPS coordinates of their kitchen.

We need real product images in the storefront, with the existing placeholders as a graceful fallback, an upload tool for employees that rejects bad files with clear explanations, a catalog that looks consistent whatever gets uploaded, and a site that stays fast.

## Solution

Each product gains one optional image. Employees upload it from the existing back-office product form. Every upload — from the back office, the Django admin, or the `seed` command — passes the same validation rules and is normalized the same way: rotated upright, stripped of metadata, resized to at most 1200 px, and stored as WebP under a fresh, unique filename. Old files are deleted once they are no longer used.

The storefront shows every product image, real or placeholder, in the same 4:5 portrait frame, cropped to fill. A product with no image — or whose image file cannot be loaded — shows its category placeholder.

The seed command loads twelve pre-optimized images into the demo world; the remaining products keep their placeholders.

## User Stories

**Visitor / customer**

1. As a visitor, I see a product's real image on its catalog card and detail page when one has been uploaded.
2. As a visitor, I see the product's category placeholder when it has no image.
3. As a visitor, I see the category placeholder — never a broken-image icon — when a product's image file is missing or fails to load.
4. As a visitor, every product image in the catalog occupies an identical 4:5 frame, so the grid is even regardless of the uploaded image's shape.
5. As a visitor, catalog pages stay fast: images are small, sized to prevent layout shift, and below-the-fold images load only as I scroll.

**Employee (staff)**

6. As an employee, I can upload an image when creating or editing a product in the back office.
7. As an employee, I can see the product's current image (or its placeholder) as a preview on the edit form.
8. As an employee, I can replace a product's image by uploading a new one.
9. As an employee, I can remove a product's image, returning it to its placeholder.
10. As an employee, I can read the upload rules on the form before I upload: JPEG, PNG, or WebP; up to 10 MB; at least 800 px on the shortest side.
11. As an employee, when I upload an invalid file, the form tells me specifically what is wrong and how to fix it, beside the image field, with the rest of my input preserved.
12. As an employee, I can see a thumbnail column in the back-office product list, so I can tell at a glance which products still need images.
13. As an employee, I can upload a photo straight from my phone and it appears the right way up, without my location embedded in it.

**Admin**

14. As an admin, uploads through the Django admin obey exactly the same rules and processing as the back office.

**Developer**

15. As a developer, `manage.py seed` still rebuilds an identical demo world — now including product images — every time it runs.
16. As a developer, running the test suite never writes to the real `media/` directory.

## Implementation Decisions

**One image per product.** `Product.image` is an optional `ImageField` (`blank=True`). No gallery, no `ProductImage` model. A gallery can be added later without discarding this work.

**Dependency and settings.** Add Pillow (required by `ImageField`). `MEDIA_ROOT = BASE_DIR / "media"`, `MEDIA_URL = "media/"`; `config/urls.py` serves media with `django.conf.urls.static.static()` when `DEBUG` is on. `media/` is gitignored. The project has no production deployment; production media serving is out of scope until one exists.

**Validation — on the model field, so every entry point enforces it.** Validators live in `products/validators.py` (mirroring `orders/validators.py`): plain functions raising `ValidationError`, attached via `Product.image`'s `validators=[...]`. They therefore apply to the back-office `ProductForm`, the Django admin, and `seed` (through `full_clean()`). Each rule has its own message naming the problem and the fix:

| Rule | Example message |
|---|---|
| Real format (read from file contents, not the filename) is JPEG, PNG, or WebP | "Unsupported image format (GIF). Upload a JPEG, PNG, or WebP file." |
| File size ≤ 10 MB | "This file is 14.2 MB. The maximum is 10 MB." |
| Pixel count ≤ 50 megapixels, checked from the header before decoding (decompression-bomb guard) | "This image is 12000×9000 pixels. The maximum is 50 megapixels." |
| Shortest side ≥ 800 px | "This image is 500×400 pixels. Images must be at least 800 pixels on their shortest side." |

Files Pillow cannot open at all are rejected by `ImageField`'s built-in message ("Upload a valid image…").

**Processing — in the model, only when the image changes.** A `Product` model method normalizes a newly assigned image, called from `save()` only when the image differs from what is stored (editing a price never reprocesses a photo). Processing: apply EXIF orientation (`ImageOps.exif_transpose`); resize to at most 1200 px on the longest side (never upscale); encode as WebP, quality 85; drop all metadata, including GPS; preserve transparency; keep only the first frame of animated images. Only the processed file is stored — originals are discarded. No new service module: the core PRD's "exactly two deep modules" rule stands.

**Filenames.** `upload_to` produces `products/<slug>-<random token>.webp`. Every upload gets a never-before-used name, so a replaced image is a new URL (no stale browser caches) and an old file can be deleted without colliding with its replacement.

**Old-file cleanup.** When an image is replaced or cleared, or its product deleted, the old file is deleted via `transaction.on_commit`, so a failed or rolled-back save never deletes a file still in use.

**Display.** `Product.display_image_url` returns the uploaded image's URL, or the static URL of `Category.placeholder_image`. Every product image in every template — catalog card, detail page, back-office form preview, back-office list thumbnail — renders through one partial, `templates/products/partials/_product_image.html`, which provides:

- a 4:5 frame (`aspect-ratio` + `object-cover`) — real photos and 4:3 placeholders alike fill it, cropped in the browser; stored files are never cropped;
- `width`/`height` attributes to prevent layout shift;
- `alt` = the product name;
- `loading="lazy"` on catalog cards (the detail-page image loads eagerly);
- a client-side fallback: `onerror="this.onerror=null; this.src='<placeholder>'"`. The server never checks the filesystem per request; the browser swaps in the category placeholder if the file fails to load. (If a Content Security Policy is ever enabled, this inline handler moves into a small static JS file — a one-partial change.)

**Back office.** The product form gains `enctype="multipart/form-data"` and a styled image field: a 4:5 preview of the current image or placeholder, a DaisyUI `file-input`, a "Remove image" checkbox, and help text stating the upload rules. The product list gains a small thumbnail column.

**Seed data.** Twelve images, shrunk once and committed as `products/seed_images/<slug>.webp` (~2 MB total). `seed` empties `media/products/`, then attaches each image through the same validation and processing path an upload uses. The source folder `product-images/` is not committed. Mapping:

| Source file | Product |
|---|---|
| Seraphine GPT Text | Seraphine |
| Hush GPT No Text | Hush |
| MindSync GPT 2 | MindSync |
| MindSync Duo | MindSync Duo |
| RecallPro | RecallPro |
| MoodSet GPT No Text | MoodSet |
| DreamWeaver Matrix GPT 3 | DreamWeaver |
| Veil GPT Text | Veil |
| Calm Collar GPT Man | Calm Collar |
| CrowdCalm Array No Text | CrowdCalm Array |
| SoulSear No Text | SoulSear Mark I |
| SyncRest GPT No Text | SyncRest |

`SyncRest GPT Text` is not used. All other products keep their category placeholder.

**Content guideline (for employees, not enforced in code).** Product photos, not ads: no marketing text baked into the image — the name, tagline, and description already sit beside it, and baked-in text is unreadable at card size. Seraphine and Veil currently carry text and should be replaced when text-free versions exist.

## Testing Decisions

Follows `docs/TESTING.md`: pytest + pytest-django, plain fixtures in `conftest.py`, no factory-boy.

**Isolation.** Every test that saves an image — including the existing seed tests — runs against a temporary `MEDIA_ROOT` that is discarded afterwards. Test images are generated in memory with Pillow, never read from disk.

Coverage priorities, in order:

1. **`products/validators.py`** — each rule accepts a valid image and rejects an invalid one with its specific message: wrong real format (including a GIF renamed `.png`), oversize file, too many megapixels, too small.
2. **Processing** — output is WebP; longest side ≤ 1200 px; small images are not upscaled; EXIF orientation applied; metadata stripped; transparency preserved; filename matches `products/<slug>-<token>.webp`; saving a product without changing its image does not reprocess it.
3. **Cleanup** — replacing, clearing, and deleting each remove the old file after commit; a rolled-back save removes nothing.
4. **Display** — `display_image_url` returns the image URL when present and the category placeholder when absent; catalog and detail pages render the shared partial with the fallback.
5. **Back office** — the product form is multipart; a valid upload saves; an invalid upload re-renders with the field error and other input preserved; "Remove image" clears it; staff-only access unchanged.
6. **Admin** — an invalid upload through the admin is rejected (validators live on the model field).
7. **Seed** — still idempotent; the twelve mapped products have images and the rest do not.

## Out of Scope

- Multiple images per product / galleries.
- Multiple stored sizes, `srcset`, or thumbnail packages.
- Production media serving, CDNs, or cloud storage backends.
- Image cropping or editing tools in the back office.
- Images on cart, checkout, or order pages (they show none today).
- Per-image alt-text fields.
