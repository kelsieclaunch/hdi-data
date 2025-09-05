
import requests
import csv
import os
import tweepy
from dotenv import load_dotenv
load_dotenv()


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
            old_available = old['available']
            new_available = p['available']

            if old_available != new_available:
                if old_available == 'True' and new_available == 'False':
                    sold_out_tweet(p)
                elif old_available == 'False' and new_available == 'True':
                    restocked_tweet(p)


    keys = products[0].keys()
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=keys)
        writer.writeheader()
        writer.writerows(products)
    
    print(f"Saved {len(products)} products to {filepath}")

def update_tweet(product):
    name = product['title']
    size = product['size']
    link = product['url']
    
    tweet = f"NEW PRODUCT: {name} - Size: {size}\n{link}"
    API.update_status(tweet)

def sold_out_tweet(product):
    name = product['title']
    size = product['size']
    link = product['url']
    
    tweet = f"SOLD OUT: {name} - Size: {size}\n{link}"
    API.update_status(tweet)

def restocked_tweet(product):
    name = product['title']
    size = product['size']
    link = product['url']
    
    tweet = f"BACK IN STOCK: {name} - Size: {size}\n{link}"
    API.update_status(tweet)





        
def main():
    hiidef = ShopifyScraper('https://hiidef.xyz/')
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

    auth = tweepy.OAuthHandler(API_key, API_key_secret)
    auth.set_access_token(access_token, access_token_secret)    

    # Create API object
    API = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)

    if not all([API_key, API_key_secret, access_token, access_token_secret]):
        raise EnvironmentError("Missing Twitter credentials. Check your .env file.")

    products = main()
    save_to_csv(products)

 

