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
        # Use fast_info if available or history
        info = ticker.fast_info
        if info and hasattr(info, 'last_price') and info.last_price:
            return float(info.last_price), None
        
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1]), None
        
        return None, f"YFinance: No data for {norm_symbol}."
    except Exception as e:
        return None, f"YFinance error: {str(e)}"

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

def get_current_price(symbol, isin=None):
    """
    Fetch the current price of a symbol trying multiple sources:
    1. BNP Scraper (if ISIN provided)
    2. Yahoo Finance
    3. AlphaVantage (Fallback)
    """
    errors = []

    # 1. Try BNP Scraper if it looks like an ISIN
    if isin and len(isin.strip()) >= 10:
        price, err = get_bnp_price(isin.strip())
        if price:
            return price, None
        errors.append(err)

    # 2. Try Yahoo Finance
    if symbol and symbol != "N/A":
        price, err = get_yfinance_price(symbol)
        if price:
            return price, None
        errors.append(err)

    # 3. Try AlphaVantage (Fallback)
    if symbol and symbol != "N/A":
        load_dotenv(override=True)
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if api_key and api_key != "your_api_key_here":
            BASE_URL = "https://www.alphavantage.co/query"
            params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key}
            try:
                response = requests.get(BASE_URL, params=params, timeout=10)
                data = response.json()
                if "Global Quote" in data and data["Global Quote"]:
                    return float(data["Global Quote"]["05. price"]), None
                elif "Note" in data:
                    errors.append("AlphaVantage: Rate limit reached.")
            except Exception as e:
                errors.append(f"AlphaVantage error: {str(e)}")

    return None, " | ".join(filter(None, errors)) if errors else "Nessuna fonte disponibile."

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
