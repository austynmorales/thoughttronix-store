The apps and what each owns:

Products - Items shown in the store and information associated with them, such as price, details, and availibility/inventory.

Orders - The order app is responsible for customer orders and their details, including who placed the order, what and how many items were ordered, when the order was placed, and the order's status such as processing, in transit, or delivered.

Accounts - Accounts manages customer accounts and authentication and profile information.

Dashboard - Dashboard is the analytics/reporting area presenting information such as revenue over time, top selling products, and other store performance information.

The path of one request:

When home page / is requested, products, products/urls.py directs it to CatalogView in products/views.py. CatalogView gets the product information and uses products/catalog.html to display the catalog on the home page.

A model you read:

The Cart model represents what is displayed inside your shopping cart that you wish to purchase, including multiple items at once, and it allows itmes to be removed as well. The add() method is interesting because it checks if a product is already in your cart, and if it is, it increases the quantity instead of adding the same product as a separate item.

Deleting a category:

If a category still has products connected to it, PROTECT blocks the category from being deleted. The on_delete=models.PROTECT line in products/models.py is what prevents this action.

Where the tests live:

The tests are organized into different test files for each part of the website. The conftest.py file provides reusable test data such as customers, products, categories, and carts that can be used throughout the tests.

One thing you're still working to understand:

Mostly all the files are still somewhat confusing to understand along with the code but with more practice with coding and working with the terminal and files, I will become more familiar with what file does what along with what strings format what information to the webpages.