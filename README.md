# Hii-Def Twitter Alert Bot
## Description
This is a Twitter bot made for Sydney that tweets updates whenever an inventory change is made on hiidef.xyz. Every two minutes, this program runs using Google Cloud Run and Cloud Scheduler to parse the JSON products file on the hiidef website, pulling product information including the name, size, product id, price, and availability. The data is then compared to a PostgreSQL database in Google Firestore for any changes. Tweets are published for the following updates:
- New Product Added, for if a product is found in the JSON file that was not previously in the database
- Item Sold Out, for if the availability flag on a product changes from True to False
- Item Restocked, for if the availability flag on a product changes from False to True

In addition to product updates, tweets are also published if the lock status on the website changes. The is_store_locked function checks if a password input has been added or removed from the page and compares the findings to the value stored in store_lock_status.txt.