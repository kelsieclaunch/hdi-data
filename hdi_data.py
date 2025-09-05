import schedule
import time

import requests
import csv
import os
import tweepy
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
LOCK_STATUS_FILE = 'store_lock_status.txt'
print("Current working directory:", os.getcwd())


class ShopifyScraper():

    def __init__(self, baseurl):
        self.baseurl = baseurl

    def download_json(self, page):
        r = requests.get(self.baseurl + f'products.json?limit=250&page={page}', timeout=5)
        if r.status_code != 200:
            print('Bad status code: ' + str(r.status_code))
            return None
        
        data = r.json().get('products', [])
        return data if data else None
    
    def normalize_size(self, size_str):
        # Normalize size names to S, M, L, XL, or blank
        size_str = size_str.lower()
        if 'small' in size_str:
            return 'S'
        elif 'medium' in size_str:
            return 'M'
        elif 'large' in size_str and 'x' not in size_str:
            return 'L'
        elif 'x-large' in size_str or 'extra large' in size_str:
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
            res = requests.get(self.baseurl, timeout=5)
            if res.status_code != 200:
                print(f"Status code {res.status_code} — assuming locked.")
                return True

            content = res.text.lower()

            # Shopify password page usually contains this
            if "enter password" in content or "this shop is currently password protected" in content:
                return True
            if "<title>opening soon</title>" in content:
                return True

            return False

        except requests.RequestException as e:
            print(f"Error checking store status: {e}")
            return True  # assume locked if request fails
    


    


def save_to_csv(products, filename='hiidef_products.csv'):
    if not products:
        print("No products to save.")
        return

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)

    # Load existing data (if file exists)
    existing_products = {}
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_products[row['v_id']] = row

    for p in products:
        vid = str(p['v_id'])

        if vid not in existing_products:
            update_tweet(p)
            

        else:
            old = existing_products[vid]
            old_available = old['available'].lower() == 'true'  # now bool
            new_available = bool(p['available'])                # already bool

            if old_available != new_available:
                if old_available and not new_available:
                    sold_out_tweet(p)
                elif not old_available and new_available:
                    restocked_tweet(p)


    keys = products[0].keys()
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=keys)
        writer.writeheader()
        writer.writerows(products)
    
    print(f"Saved {len(products)} products to {filepath}")

def has_store_lock_status_changed(current_status):
    if os.path.exists(LOCK_STATUS_FILE):
        with open(LOCK_STATUS_FILE, 'r') as f:
            previous_status = f.read().strip()
    else:
        previous_status = ''

    status_str = 'locked' if current_status else 'unlocked'

    changed = previous_status != status_str
    
    print(f"[DEBUG] Previous status: '{previous_status}', Current status: '{status_str}', Changed: {changed}")

    # Save current status
    with open(LOCK_STATUS_FILE, 'w') as f:
        f.write(status_str)
    print(f"[DEBUG] Store lock status file updated to '{status_str}'")

    return changed, previous_status, status_str


def safe_post(tweet):
    try:
        response = client.create_tweet(text=tweet)
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
def update_tweet(product): # when product id not yet in csv
    size = product['size']
    name = truncate_title(product['title'], "NEW PRODUCT", size)
    link = product['url']

    print("tweeting new product flag")
    
    tweet = f"NEW PRODUCT: {name} - Size: {size}\n{link}"
    safe_post(tweet)


def sold_out_tweet(product): # when available flag switched from true to false 
    size = product['size']
    name = truncate_title(product['title'], "SOLD OUT", size)
    link = product['url']
    
    print("tweeting sold out flag")
    
    tweet = f"SOLD OUT: {name} - Size: {size}\n{link}"
    safe_post(tweet)

def restocked_tweet(product): # when available flag switched from false to true
    size = product['size']
    name = truncate_title(product['title'], "BACK IN STOCK", size)
    link = product['url']
    print("tweeting back in stock flag")
    
    tweet = f"BACK IN STOCK: {name} - Size: {size}\n{link}"
    safe_post(tweet)

def job():
    print("Starting job at", datetime.now())
    products = main()
    save_to_csv(products)
    print("Job finished", flush=True)





        
def main():
    print("Bot started", flush=True)
    print("Running hdi_data.py at", datetime.now())
    hiidef = ShopifyScraper('https://hiidef.xyz/')

    # Check lock status
    is_locked = hiidef.is_store_locked()
    changed, prev, curr = has_store_lock_status_changed(is_locked)

    if changed:
        print(f"Store lock status changed: {prev} → {curr}")
        if is_locked:
            print("site locked")
            safe_post("The site is now locked.")
        else:
            print("site unlocked")
            safe_post("The site is now unlocked.")

    elif is_locked:
        print("Store is locked — skipping product scrape.")
        return []
    
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


if __name__ == '__main__':

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
        wait_on_rate_limit=True
    )

    schedule.every(2).minutes.do(job)


    print("Scheduler started. Press Ctrl+C to exit.")

    job()  

    while True:
        schedule.run_pending()
        time.sleep(1)

 

