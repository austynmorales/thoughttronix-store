# Product Images

## Question 1 - One decision from grill me
During the Grill Me interview, one important decision I made was how the website should handle missing product images. Claude originally recommended allowing a broken image to appear if the uploaded file was missing. I disagreed because i thought broken images would make the website look unfinished and could confuse customers. Instead, I decided the website should display the existing category placeholder whenever an image fails to load. This decision helped keep the product catalog lookin consisten and professinal. The feature uses an error handler to automacitcally switch to the placeholder without checking the server for missing files every time a page loads.

## Question 2 - Find the upload code
Part 1 - ImageField
The ImageField is located in products/models.py, starting on line 104.
    image = models.ImageField(
        upload_to=product_image_path,
        blank=True,
        max_length=255,
        validators=[
            validate_image_format,
            validate_image_file_size,
            validate_image_megapixels,
            validate_image_min_size,
        ],
    )
The upload_to=product_image_path setting tells Django where to store uploaded product images. The function product_image_path, defined on line 68, generates a unique filename using the product's slug and a random identifier. The uploaded image is then saved inside the media/products/folder.

Part 2 - HTML Upload Form

The opening form tag is located in templates/products/manage_product_form.html, line 14.

<form method="post" enctype="multipart/form-data" class="mt-2 space-y-4">

The enctype="multipart/form-data" attribute is necessary because it allows the browser to send uploaded image files along with the other information entered in the product form. Without this attribute, Django would not receive the image correctly through request.FILES, and the upload would not work.

## Question 3 - Follow the upload process
1. Where the image is stored on disk

My NeuroBand X image is saved at:
C:/Users/moral/thoughttronix-store/thoughttronix-store/media/products/neuroband-x-8234a5f483c51904.webp

The MEDIA_ROOT setting in config/settings.py, line 144, determines wehre uploaded images are stored. It uses the project's BASE_DIR, which is defined on line 15, and adds the media folder.

2. What the database stores

The database stores this value for my image:

products/neuroband-x-8234a5f483c51904.webp

The database stores the image's relative file path instead of the actual image file. The Product.image field is defined in products/models.py, beginning on line 104. The upload_to setting calls the product_image_path function on lines 68-76. This function creates a unique filename using the product's slug and a random identifier.

3. The URL the browser requests

The browser requests:

http://127.0.0.1:8000/media/products/neuroband-x-8234a5f483c51904.webp

The MEDIA_URL setting is defined in config/settings.py, line 146. The display_image_url property in products/models.py, lines 174-178, gets the image URL. The template
templates/products/partials/_product_image.html, line 17, uses that URL to display the image.

How Django serves the image

In config/urls.py, line 27, the following code allows Django to serve uploaded images during development:

urlpatters += static(settings.MEDIA_URL, document_root=settings.MEDIAT_ROOT)

This connects the media URL to the folder containing uploaded images. When the browser requests the image, Django reads the file from the media folder and sends it to the browser.

This works while Django's DEBUG setting is enabled. The setting is defined in config/settings.py, line 26.

# Discount Coupons

## Question 1 - One decision from grill me
One question from grill me that made me think was whether a discount code should apply to the whole order or only certain products. At first I was not completely sure how the two options would work differently. After going through the questions, I decided the system should support both types. This made sense because some promotions could discount an entire purchase while others could be used for a specific product. This decision affected how the coupon feature was designed because it needed to know which products were eligible for each discount.

## Question 2 - The change
After reviewing the discount coupon feature, I noticed there could be a problem with the expiration time for the coupons. The expiration time was being handled in UTC instead of the store's local time. This could cause a coupon to expire earlier or later than expected for the customer. I decided to change it so the expiration time uses the store's time zone. After making the change, I checked the feature again to make sure the coupons expired at the correct time and that the rest of the discount feature still worked correctly.

## Featured Products

### Question 1 - Trace the feature
When I mark a product as featured in the back office, the is_featured field in models.py saved that choice. The field was added to forms.py, which allowed me to turn the is featured on or off when editing a product. The catalog.html file checks if the product is featured and displays the Featured badge on the catalog page. The detail.html file does the same thing on the individual product page.

### Question 2 - How I verified
I verified the feature by marking Seraphine, SoulSear Mark 2, and SoulSear Mark 1 as featured in the back office. I then checked the catalog listing page and each product detail page in the browser. I confirmed that the Featured badge appeared for the three products I marked as featured and did not appear for the other products.

### Question 3 - Judgement

I realise that you have to play around with claude when you ask it questions or tell it what to do due to the fact that there are limitless options that the agent is capable of which can be helpful as it can be dangerous in creating or editing. I wouldn't say I have encountered a real challenge yet, but I appreciate the git commit and push to save my work without risking the deletion or major errors when working in my terminal.