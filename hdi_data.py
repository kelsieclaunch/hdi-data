import requests
import csv
import os
import tweepy
import time
from datetime import datetime
from datetime import timezone
from dotenv import load_dotenv
from google.cloud import firestore
from bs4 import BeautifulSoup


def time_marker():
    return datetime.now(timezone.utc).strftime("%H:%M UTC")


load_dotenv()

ENABLE_STORE_PASSWORD = os.getenv("ENABLE_STORE_PASSWORD", "false").lower() == "true"
STORE_PASSWORD = os.getenv("SHOPIFY_STORE_PASSWORD")


db = firestore.Client()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "hdi-scraper")

LOCK_STATUS_FILE = 'store_lock_status.txt'
print("Current working directory:", os.getcwd())


class ShopifyScraper():

    def __init__(self, baseurl, enable_password=False, password=None):
        self.baseurl = baseurl
        self.enable_password = enable_password
        self.password = password
        self.session = requests.Session()



    def download_json(self, page):
        # Unlock the store first if needed
        if self.enable_password: 
            self.unlock_store() 

        url = f"{self.baseurl}/products.json?limit=250&page={page}"  
        try: 
            r = self.session.get(url, timeout=10) 
            r.raise_for_status() 
            return r.json().get('products', []) 
        except requests.exceptions.HTTPError as e: 
            print(f"HTTP Error {r.status_code}: {e}") 
        except requests.exceptions.RequestException as e: 
            print(f"Request failed: {e}") 
        return None



    
    def normalize_size(self, size_str):
        # Normalize size names to S, M, L, XL, or blank
        size_str = size_str.lower()
        if 'small' in size_str:
            return 'S'
        elif 'medium' in size_str:
            return 'M'
        elif 'large' in size_str and 'x' not in size_str:
            return 'L'
        elif 'x-large' in size_str and not '2' in size_str:
            return 'XL'
        elif 'xx-large' in size_str or '2x' in size_str:
            return 'XXL'
        else:
            return '' # leave blank if no match
        
        
    def parse_json(self, jsondata):
        products = []

        for prod in jsondata:
            main_title = prod['title']
            main_type = prod['product_type']
            main_handle = prod['handle']
            main_link = 'https://hiidef.xyz/products/' + main_handle
            for v in prod['variants']:
                varid = str(v['id'])
                var_link = main_link + '?variant=' + varid


                size_raw = v['title']
                size_normalized = self.normalize_size(size_raw)

                item = {
                    'title': main_title,
                    'type' : main_type,
                    'size': size_normalized,
                    'v_id': v['id'],
                    'available': v['available'],
                    'price': v['price'],
                    'url': var_link
                    
                }
                products.append(item)
                
                
        return products
    
    def is_store_locked(self):
        try:
            res = self.session.get(self.baseurl, timeout=5)

            # Look for url redirect
            if res.url.rstrip("/").endswith("/password"):
                return True
            
            # Look for password modal link
            soup = BeautifulSoup(res.text, "html.parser")
            login_link = soup.find(
                "a",
                href="#LoginModal",
                class_="js-modal-open-login-modal"
            )

            if login_link and "enter using password" in login_link.get_text(strip=True).lower():
                return True 

            # If page loads and none of the lock indicators are found, it's not locked
            return False

        except requests.RequestException as e:
            print(f"Error checking store status: {e}")
            # Do not assume locked — just return False and optionally log
            return None
        
    def unlock_store(self):
        """Submit the Shopify storefront password to get access to /products.json"""
        if not self.enable_password or not self.password:
            return

        password_url = f"{self.baseurl}/password"
        data = {'password': self.password}

        try:
            res = self.session.post(password_url, data=data, timeout=10)
            if res.status_code == 200:
                print("Store unlocked successfully!")
            else:
                print(f"Failed to unlock store: {res.status_code}")
        except requests.RequestException as e:
            print(f"Error unlocking store: {e}")

        


    

# # # FIRESTORE VERSION # # # FOR CLOUD RUN

def save_to_firestore(products):
    if not products:
        print("No products to save.")
        return

    product_collection = db.collection('products')

    # Check if this is the first run (no products in DB)
    existing_docs = list(product_collection.limit(1).stream())
    is_first_run = len(existing_docs) == 0

    if is_first_run:
        print("First run detected — saving products without tweeting.")
    else:
        print("Existing data found — comparing for changes.")

    for p in products:
        vid = str(p['v_id'])  # Firestore document ID must be a string
        doc_ref = product_collection.document(vid)
        doc = doc_ref.get()

        if not doc.exists:
            if not is_first_run:
                update_tweet(p)
        else:
            old = doc.to_dict()
            old_available = old.get('available', False)
            new_available = p['available']

            if old_available != new_available:
                if old_available and not new_available:
                    sold_out_tweet(p)
                elif not old_available and new_available:
                    restocked_tweet(p)

        # Save/update product in Firestore
        doc_ref.set(p)

    print(f"Saved {len(products)} products to Firestore.")
  
def has_store_lock_status_changed(current_status):
    #Check if the store lock status is different from Firestore, but do NOT update yet
    config_doc = db.collection('config').document('store_lock')

    status_str = 'locked' if current_status else 'unlocked'
    prev_status = None

    doc = config_doc.get()
    if doc.exists:
        prev_status = doc.to_dict().get('status')

    changed = prev_status != status_str

    print(f"[DEBUG] Previous: '{prev_status}', Current: '{status_str}', Changed: {changed}")

    return changed, prev_status, status_str


def update_store_lock_status(current_status):
    #Save the confirmed store lock status to Firestore.
    config_doc = db.collection('config').document('store_lock')
    status_str = 'locked' if current_status else 'unlocked'
    config_doc.set({'status': status_str})
    print(f"[DEBUG] Store lock status updated to '{status_str}' in Firestore")




def safe_post(tweet):
    try:
        tweet_with_time = f"{tweet}\n {time_marker()}"
        response = client.create_tweet(text=tweet_with_time)
        print(f"Tweet posted! ID: {response.data['id']}")
    except tweepy.TweepyException as e:
        print(f"Tweet failed: {tweet}\nReason: {e}")

def truncate_title(title, prefix="NEW PRODUCT", size=""): # trim title if needed
    static_parts = f"{prefix}:  - Size: {size}\n"  # other content
    reserved_chars = len(static_parts) + 23  # 23 for the link
    max_title_length = 280 - reserved_chars

    if len(title) <= max_title_length:
        return title
    return title[:max_title_length - 1] + "…"

# ACTUALLY TWEETING
def update_tweet(product):
    size = product['size']
    name = truncate_title(product['title'], "NEW PRODUCT", size)
    link = product['url']

    flag = bool(product.get('available', False))  
    avail = 'AVAILABLE' if flag else 'UNAVAILABLE'

    print("tweeting new product flag")
    tweet = f"NEW PRODUCT: {name}, {avail} - Size: {size}\n{link}"
    safe_post(tweet)



def sold_out_tweet(product): #avail flag false to true
    size = product['size']
    name = truncate_title(product['title'], "SOLD OUT", size)
    link = product['url']
    flag = bool(product.get('available', False))
    avail = 'AVAILABLE' if flag else 'UNAVAILABLE'

    print("tweeting sold out flag")
    tweet = f"SOLD OUT: {name} - Size: {size}\n{link}"
    safe_post(tweet)
    

def restocked_tweet(product): #avail flag true to false
    size = product['size']
    name = truncate_title(product['title'], "BACK IN STOCK", size)
    link = product['url']
    flag = bool(product.get('available', False))
    avail = 'AVAILABLE' if flag else 'UNAVAILABLE'

    print("tweeting back in stock flag")
    tweet = f"BACK IN STOCK: {name} - Size: {size}\n{link}"
    safe_post(tweet)


def job():
    print("Starting job at", datetime.now())
    products = main()
    save_to_firestore(products)
    print("Job finished", flush=True)





        
def main():
    print("Bot started", flush=True)
    print("Running hdi_data.py at", datetime.now())
    hiidef = ShopifyScraper(
        'https://hiidef.xyz/',
        enable_password=ENABLE_STORE_PASSWORD,
        password=STORE_PASSWORD
    )

    # Check lock status
    is_locked = hiidef.is_store_locked()


    if is_locked is None:
        print("Lock status unknown due to error — skipping lock state checks")
    else:
        changed, prev, curr = has_store_lock_status_changed(is_locked)

    if changed:
        print(f"Initial lock status changed: {prev} → {curr}")
        print("Waiting 20 seconds to confirm...")
        time.sleep(20)  # Wait before confirming

        # Re-check lock status
        is_locked_after_wait = hiidef.is_store_locked()
        changed_after_wait, prev_after_wait, curr_after_wait = has_store_lock_status_changed(is_locked_after_wait)


        if changed_after_wait:
            print(f"Confirmed lock status change after wait: {prev_after_wait} → {curr_after_wait}")

             # Commit status now
            update_store_lock_status(is_locked_after_wait)

            
            if is_locked_after_wait:
                print("Site locked confirmed")
                safe_post("The site is now locked.")
            else:
                print("Site unlocked confirmed")
                safe_post("The site is now unlocked.")
           

        else:
            print("Lock status reverted — no tweet sent.")

    # elif is_locked:
    #     print("Store is locked — skipping product scrape.")
    #     return []
    
    results = []
    for page in range(1, 10):
        data = hiidef.download_json(page)
        print('Getting page ', page)
        if not data:
            print(f'Completed, total pages = {page - 1}' )
            break
        parsed = hiidef.parse_json(data)
        results.extend(parsed)
    return results




API_key = os.getenv("TWITTER_API_KEY")
API_key_secret = os.getenv("TWITTER_API_SECRET")
access_token = os.getenv("TWITTER_ACCESS_TOKEN")
access_token_secret = os.getenv("TWITTER_ACCESS_SECRET")
bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

if not all([API_key, API_key_secret, access_token, access_token_secret, bearer_token]):
    raise EnvironmentError("Missing Twitter credentials. Check your .env file.")

# Create a Tweepy client (v2)
client = tweepy.Client(
    bearer_token=bearer_token,
    consumer_key=API_key,
    consumer_secret=API_key_secret,
    access_token=access_token,
    access_token_secret=access_token_secret,
    wait_on_rate_limit=False
)

from flask import Flask, request

app = Flask(__name__)

@app.route('/', methods=['GET'])
def health_check():
    return 'OK', 200


@app.route('/', methods=['POST'])
def run_job():
    print("Received job trigger")
    try:
        job()
        print("Job finished successfully")
    except Exception as e:
        print(f"Job failed: {e}")
    return 'Job complete', 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)