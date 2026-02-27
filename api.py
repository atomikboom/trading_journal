import os
import requests
from dotenv import load_dotenv
import yfinance as yf
from bs4 import BeautifulSoup
import time

load_dotenv()

def normalize_ticker(symbol):
    """Normalize common ticker formats (e.g. $VIX -> ^VIX)."""
    if not symbol: return symbol
    symbol = symbol.strip().upper()
    
    # If symbol looks like a sentence or very long, it's likely not a ticker
    if len(symbol) > 15 or " " in symbol:
        return symbol # Return as is, let fetching handle error
        
    # Indices in Yahoo usually start with ^
    if symbol == "VIX" or symbol == "$VIX":
        return "^VIX"
    if symbol.startswith("$"):
        return "^" + symbol[1:]
    return symbol

def get_yfinance_price(symbol):
    """Fetch price from Yahoo Finance."""
    try:
        norm_symbol = normalize_ticker(symbol)
        ticker = yf.Ticker(norm_symbol)
        
        # 1. Try fast_info
        try:
            info = ticker.fast_info
            if info and hasattr(info, 'last_price') and info.last_price:
                return float(info.last_price), None
        except:
            pass
            
        # 2. Try history as fallback (more robust)
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1]), None
            
        # 3. Try info (slow but comprehensive)
        try:
            val = ticker.info.get('regularMarketPrice') or ticker.info.get('currentPrice')
            if val:
                return float(val), None
        except:
            pass
            
        return None, f"YFinance: No data for {norm_symbol}."
    except Exception as e:
        return None, f"Yfinance error: {str(e)}"

def get_bnp_price(isin):
    """
    Scrape BNP Paribas site for certificate price using ISIN.
    """
    if not isin or len(isin) < 10:
        return None, "BNP: ISIN non valido."
    
    # Try direct product details URL first
    urls = [
        f"https://investimenti.bnpparibas.it/product-details/{isin}/",
        f"https://www.investimenti.bnpparibas.it/search-result/?query={isin}"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    
    errors = []
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 404:
                continue # Try next URL
            if response.status_code != 200:
                errors.append(f"BNP status {response.status_code} for {url}")
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Selectors found via investigation:
            # .bid-button strong span (Vendi)
            # .ask-button strong span (Compra)
            # fallback: .price-value, .last-price
            
            selectors = [
                ('.bid-button strong span', None), # Class based
                ('.ask-button strong span', None), 
                ('span', {'class': 'price-value'}),
                ('div', {'class': 'last-price'}),
                ('span', {'class': 'last-price-value'})
            ]
            
            for selector, attrs in selectors:
                if attrs is None:
                    price_tag = soup.select_one(selector)
                else:
                    price_tag = soup.find(selector, attrs)
                
                if price_tag:
                    price_text = price_tag.text.strip().split(' ')[0]
                    price_text = price_text.replace('.', '').replace(',', '.')
                    try:
                        return float(price_text), None
                    except ValueError:
                        continue
                        
        except Exception as e:
            errors.append(f"BNP error for {url}: {str(e)}")
            
    return None, " | ".join(errors) if errors else f"BNP: ISIN {isin} non trovato nel sito."

def get_google_finance_price(symbol):
    """Scrape Google Search for stock price (more robust than direct Finance page)."""
    try:
        # Search for ticker price to avoid consent pages sometimes
        url = f"https://www.google.com/search?q={symbol}+stock+price"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Look for price in specific data attributes or common classes
            # Google search often uses [data-precision] or specific span classes
            price_tag = soup.select_one('span[jsname="vW79of"]') # Price in Google Search Widget
            if not price_tag:
                 price_tag = soup.select_one('.pclqee') # Fallback price class
            
            if price_tag:
                price_text = price_tag.text.strip().replace('$', '').replace(',', '').replace('€', '').strip()
                return float(price_text), None
        
        # Fallback to direct Finance page if search fails
        url_fin = f"https://www.google.com/finance/quote/{symbol}"
        response = requests.get(url_fin, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            price_tag = soup.select_one('.YMlKec.fxKbKc')
            if price_tag:
                price_text = price_tag.text.strip().replace('$', '').replace(',', '').strip()
                return float(price_text), None
                
        return None, f"Google Finance: No data for {symbol}."
    except Exception as e:
        return None, f"Google Finance error: {str(e)}"

def get_finnhub_price(symbol):
    """Fetch price from Finnhub (requires API key)."""
    load_dotenv(override=True)
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return None, "Finnhub: API Key missing."
    
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"
        response = requests.get(url, timeout=10)
        data = response.json()
        if "c" in data and data["c"] != 0:
            return float(data["c"]), None
        return None, f"Finnhub: No data for {symbol}."
    except Exception as e:
        return None, f"Finnhub error: {str(e)}"

def get_marketwatch_price(symbol):
    """Scrape MarketWatch for price."""
    # MarketWatch often blocks simple requests, but we keep it as a best-effort fallback
    try:
        url = f"https://www.marketwatch.com/investing/stock/{symbol.lower()}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            price_tag = soup.select_one('bg-quote[field="Last"]')
            if price_tag:
                return float(price_tag.text.strip().replace(',', '')), None
        return None, f"MarketWatch: No data for {symbol}."
    except:
        return None, "MarketWatch failure."

def get_investing_price(isin_or_symbol):
    """Search Investing.com for ISIN or Symbol and get price."""
    # This is often blocked by Cloudflare, but useful if it works
    try:
        search_url = f"https://www.investing.com/search/?q={isin_or_symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            price_tag = soup.select_one('[data-test="instrument-price-last"]')
            if price_tag:
                text = price_tag.text.strip().replace('.', '').replace(',', '.')
                return float(text), None
        return None, f"Investing.com: No data for {isin_or_symbol}."
    except:
        return None, "Investing.com failure."

def get_current_price(symbol, isin=None):
    """
    Fetch the current price trying multiple sources in order of reliability.
    """
    errors = []

    # 1. BNP Scraper (for Certificates)
    if isin and len(isin.strip()) >= 10:
        price, err = get_bnp_price(isin.strip())
        if price: return price, None
        errors.append(err)

    # 2. Google Finance/Search (Very robust)
    if symbol and symbol != "N/A":
        price, err = get_google_finance_price(symbol)
        if price: return price, None
        errors.append(err)

    # 3. Finnhub (API - Reliable)
    if symbol and symbol != "N/A":
        price, err = get_finnhub_price(symbol)
        if price: return price, None
        errors.append(err)

    # 4. Yahoo Finance (Recently unstable)
    if symbol and symbol != "N/A":
        price, err = get_yfinance_price(symbol)
        if price: return price, None
        errors.append(err)

    # 5. Fallbacks (MarketWatch, Investing.com)
    search_term = isin if isin and len(isin.strip()) >= 10 else symbol
    if search_term and search_term != "N/A":
        for func in [get_marketwatch_price, get_investing_price]:
            price, err = func(search_term)
            if price: return price, None
            errors.append(err)

    # 6. AlphaVantage (Last Fallback)
    if symbol and symbol != "N/A":
        load_dotenv(override=True)
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if api_key and api_key and api_key != "your_api_key_here":
            BASE_URL = "https://www.alphavantage.co/query"
            params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key}
            try:
                response = requests.get(BASE_URL, params=params, timeout=10)
                data = response.json()
                if "Global Quote" in data and data["Global Quote"]:
                    return float(data["Global Quote"]["05. price"]), None
            except:
                pass

    return None, "Tutte le fonti hanno fallito. Controlla la connessione o il ticker."

def resolve_isin_to_symbol(isin):
    """
    Search for a symbol using an ISIN via AlphaVantage.
    """
    load_dotenv(override=True)
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return None, "API Key missing."

    BASE_URL = "https://www.alphavantage.co/query"
    params = {
        "function": "SYMBOL_SEARCH",
        "keywords": isin,
        "apikey": api_key
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        data = response.json()
        if "bestMatches" in data and len(data["bestMatches"]) > 0:
            return data["bestMatches"][0]["1. symbol"], None
        return None, "No symbol found for this ISIN."
    except Exception as e:
        return None, str(e)

if __name__ == "__main__":
    # Test with a known symbol if API key is present
    price, error = get_current_price("AAPL")
    if error:
        print(f"Error: {error}")
    else:
        print(f"AAPL Price: {price}")
