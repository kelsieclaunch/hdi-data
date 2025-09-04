
import requests
import json
import dataset
import sqlite3

class ShopifyScraper():

    def __init__(self, baseurl):
        self.baseurl = baseurl

    def download_json(self, page):
        r = requests.get(self.baseurl + f'products.json?limit=250&page={page}', timeout=5)
        if r.status_code != 200:
            print('Bad status code: ' + str(r.status_code))
        if len(r.json()['products']) > 0:
            data = r.json()['products']
            return data
        else:
            return
        
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
                item = {
                    'title': main_title,
                    'type' : main_type,
                    'variant': v['title'],
                    'v_id': v['id'],
                    'available': v['available'],
                    'price': v['price'],
                    'url': var_link
                    
                }
                products.append(item)
                
                
        return products
    
def main():
    hiidef = ShopifyScraper('https://hiidef.xyz/')
    results = []
    for page in range(1, 10):
        data = hiidef.download_json(page)
        print('Getting page ', page)
        try:
            results.append(hiidef.parse_json(data))
        except:
            print(f'Completed, total pages = {page - 1}' )
            break
    return results

if __name__ == '__main__':
 
    db = dataset.connect('sqlite:///hdi-data.db')
    table = db.create_table('hiidef', primary_id='v_id')
    products = main()
    totals = [item for i in products for item in i] 
    print(len(totals))

    for p in totals:
        if not table.find_one(v_id = p['v_id']):
            table.insert(p)
            print('NEW PRODUCT: ', p)