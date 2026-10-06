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