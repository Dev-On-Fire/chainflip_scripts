import requests
import time
import re
from collections import defaultdict

# --- CONFIGURATION ---
API_KEY = "xxxxxxxxx" #insert your etherscan api key
BRIDGE_ADDRESS = "0xf5e10380213880111522dd0efd3dbb45b9f62bcc".lower()
TIME_WINDOW_SECONDS = 600  #10min
ETHERSCAN_V2_API = "https://api.etherscan.io/v2/api"

# Method IDs
TRUST_METHODS = ["9fe99b64", "57e780ad"]
METAMASK_METHOD = "3ce33bff"
BINANCEWEB3_METHOD = "810c705b"

# --- PRICE UTILITY ---
price_cache = {}

def get_usd_price(symbol, contract_address=None):
    """Fetches current price from CoinGecko. Native ETH uses symbol 'ethereum'."""
    cache_key = symbol.upper()
    if cache_key in price_cache:
        return price_cache[cache_key]
    
    try:
        if symbol.lower() == "eth":
            url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
            r = requests.get(url).json()
            price = r.get("ethereum", {}).get("usd", 0)
        else:
            url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={contract_address}&vs_currencies=usd"
            r = requests.get(url).json()
            price = r.get(contract_address.lower(), {}).get("usd", 0)
        
        price_cache[cache_key] = price
        return price
    except:
        return 0

# --- BLOCKCHAIN UTILITY ---
def get_block_by_time(timestamp):
    params = {"chainid": 1, "module": "block", "action": "getblocknobytime", 
              "timestamp": timestamp, "closest": "before", "apikey": API_KEY}
    r = requests.get(ETHERSCAN_V2_API, params=params).json()
    return int(r["result"])

def get_tx_method_id(tx_hash):
    params = {"chainid": 1, "module": "proxy", "action": "eth_getTransactionByHash", "txhash": tx_hash, "apikey": API_KEY}
    r = requests.get(ETHERSCAN_V2_API, params=params).json()
    input_data = r.get("result", {}).get("input", "0x")
    match = re.search(r'^0x([a-fA-F0-9]{8})', input_data)
    return match.group(1).lower() if match else None

def main():
    now = int(time.time())
    start_block = get_block_by_time(now - TIME_WINDOW_SECONDS)
    end_block = get_block_by_time(now)

    # Aggregator Structure: { 'WALLET': { 'TOKEN_SYM': {'amount': 0, 'usd': 0} } }
    report = {
        "TRUST": defaultdict(lambda: {"amount": 0.0, "usd": 0.0}),
        "METAMASK": defaultdict(lambda: {"amount": 0.0, "usd": 0.0}),
        "BINANCEWEB3": defaultdict(lambda: {"amount": 0.0, "usd": 0.0})
    }

    print(f"--- Scanning Chainflip Bridge ({TIME_WINDOW_SECONDS/60}m window) ---")

    # 1. SCAN NATIVE ETH (Internal Txs)
    internal_params = {"chainid": 1, "module": "account", "action": "txlistinternal", "address": BRIDGE_ADDRESS,
                       "startblock": start_block, "endblock": end_block, "sort": "desc", "apikey": API_KEY}
    internal_txs = requests.get(ETHERSCAN_V2_API, params=internal_params).json().get("result", [])
    
    eth_price = get_usd_price("ETH")

    for tx in internal_txs:
        val_eth = int(tx.get("value", 0)) / 10**18
        if val_eth <= 0: continue
        
        method_id = get_tx_method_id(tx["hash"])
        wallet = None
        if method_id in TRUST_METHODS: wallet = "TRUST"
        elif method_id == METAMASK_METHOD: wallet = "METAMASK"
        elif method_id == BINANCEWEB3_METHOD: wallet = "BINANCEWEB3"
        
        if wallet:
            report[wallet]["ETH"]["amount"] += val_eth
            report[wallet]["ETH"]["usd"] += (val_eth * eth_price)
        time.sleep(0.2)

    # 2. SCAN ERC-20 TOKENS
    token_params = {"chainid": 1, "module": "account", "action": "tokentx", "address": BRIDGE_ADDRESS,
                    "startblock": start_block, "endblock": end_block, "sort": "desc", "apikey": API_KEY}
    token_txs = requests.get(ETHERSCAN_V2_API, params=token_params).json().get("result", [])

    for tx in token_txs:
        if tx["to"].lower() != BRIDGE_ADDRESS: continue
        
        method_id = get_tx_method_id(tx["hash"])
        wallet = None
        if method_id in TRUST_METHODS: wallet = "TRUST"
        elif method_id == METAMASK_METHOD: wallet = "METAMASK"
        elif method_id == BINANCEWEB3_METHOD: wallet = "BINANCEWEB3"

        if wallet:
            symbol = tx["tokenSymbol"]
            amount = int(tx["value"]) / (10 ** int(tx["tokenDecimal"]))
            price = get_usd_price(symbol, tx["contractAddress"])
            
            report[wallet][symbol]["amount"] += amount
            report[wallet][symbol]["usd"] += (amount * price)
        time.sleep(0.2)

    # --- FINAL CONSOLIDATED REPORT ---
    print("\n" + "="*65)
    print(f"{'WALLET':<15} | {'TOKEN':<8} | {'AMOUNT':>15} | {'USD VALUE':>15}")
    print("-" * 65)

    total_bridge_usd = 0
    for wallet, tokens in report.items():
        if not tokens:
            continue
        for sym, data in tokens.items():
            print(f"{wallet:<15} | {sym:<8} | {data['amount']:>15,.4f} | ${data['usd']:>14,.2f}")
            total_bridge_usd += data['usd']
    
    print("="*65)
    print(f"{'TOTAL HOURLY VOLUME':<44} | ${total_bridge_usd:>14,.2f}")
    print("="*65)

if __name__ == "__main__":
    main()