import requests
from bs4 import BeautifulSoup

def send_trade_offer(nation_id, amount, resource):
    session = requests.Session()
    login_url = 'https://politicsandwar.com/login/'
    trade_url = 'https://politicsandwar.com/nation/trade/create/'
    
    payload = {
        'email': 'ally.ciza313@gmail.com',
        'password': 'Ac031308'
    }
    
    login_response = session.post(login_url, data=payload)
    if login_response.status_code != 200:
        return {'success': False, 'message': 'Login failed'}
    
    payload = {
        'nation_id': nation_id,
        'amount': amount,
        'resource': resource,
        'type': 'offer'
    }
    
    trade_response = session.post(trade_url, data=payload)
    if trade_response.status_code == 200:
        return {'success': True, 'message': 'Trade offer sent'}
    else:
        return {'success': False, 'message': 'Failed to send trade offer'}
