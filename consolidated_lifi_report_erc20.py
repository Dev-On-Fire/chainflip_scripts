import requests
import time
import re
from collections import defaultdict

# --- CONFIGURATION ---
API_KEY = "xxxxxxx" #add your etherscan api key
BRIDGE_ADDRESS = "0xf5e10380213880111522dd0efd3dbb45b9f62bcc".lower()
TIME_WINDOW_SECONDS = 3600 #1 hour
ETHERSCAN_V2_API = "https://api.etherscan.io/v2/api"

def get_block_by_time(timestamp):
    params = {"chainid": 1, "module": "block", "action": "getblocknobytime", 
              "timestamp": timestamp, "closest": "before", "apikey": API_KEY}
    r = requests.get(ETHERSCAN_V2_API, params=params).json()
    return int(r["result"])

def get_token_transfers(start_block, end_block):
    params = {"chainid": 1, "module": "account", "action": "tokentx", "address": BRIDGE_ADDRESS,
              "startblock": start_block, "endblock": end_block, "sort": "desc", "apikey": API_KEY}
    r = requests.get(ETHERSCAN_V2_API, params=params).json()
    return r.get("result", []) if r.get("status") == "1" else []

def get_tx_details(tx_hash):
    params = {"chainid": 1, "module": "proxy", "action": "eth_getTransactionByHash", "txhash": tx_hash, "apikey": API_KEY}
    r = requests.get(ETHERSCAN_V2_API, params=params).json()
    return r.get("result", {}).get("input", "0x")

def extract_bridge_and_integrator(input_data):
    if len(input_data) < 100: return None, "N/A"
    try:
        raw_bytes = bytes.fromhex(input_data[2:])
        bridge_name = "chainflip"
        bridge_bytes = bridge_name.encode('utf-8')
        
        start_idx = raw_bytes.find(bridge_bytes)
        if start_idx == -1:
            return None, "N/A"
            
        # Look for the integrator name in the data following 'chainflip'
        remaining_data = raw_bytes[start_idx + 32:]
        matches = re.findall(rb'[a-zA-Z0-9\.\-\_]{3,30}', remaining_data)
        
        integrator = "N/A"
        for m in matches:
            found = m.decode('utf-8')
            if found.lower() not in ["chainflip", "lifi"]:
                integrator = found
                break
                
        return bridge_name, integrator
    except:
        return None, "N/A"

def main():
    now = int(time.time())
    start_time = now - TIME_WINDOW_SECONDS

    # Data structure for summary: { integrator: { token_symbol: total_amount } }
    summary = defaultdict(lambda: defaultdict(float))

    try:
        start_block = get_block_by_time(start_time)
        end_block = get_block_by_time(now)
        token_txs = get_token_transfers(start_block, end_block)
    except Exception as e:
        print(f"Error: {e}")
        return

    print(f"\nScanning {len(token_txs)} transfers for Chainflip activity...")
    print(f"{'TOKEN':<8} | {'AMOUNT':<12} | {'INTEGRATOR':<20} | {'HASH'}")
    print("-" * 105)

    seen_hashes = {}

    for tx in token_txs:
        if tx["to"].lower() != BRIDGE_ADDRESS: continue 
        
        tx_hash = tx["hash"]
        if tx_hash not in seen_hashes:
            input_data = get_tx_details(tx_hash)
            seen_hashes[tx_hash] = extract_bridge_and_integrator(input_data)
        
        bridge, integrator = seen_hashes[tx_hash]
        
        # --- STRICT FILTER ---
        # Only process if bridge is specifically 'chainflip'
        if bridge != "chainflip":
            continue

        amount = int(tx["value"]) / (10 ** int(tx["tokenDecimal"]))
        symbol = tx['tokenSymbol']
        
        # Update Summary Data
        summary[integrator][symbol] += amount
        
        print(f"{symbol:<8} | {amount:<12.4f} | {integrator:<20} | {tx_hash}")
        time.sleep(0.15) # Faster scanning

    # --- FINAL SUMMARY SECTION ---
    print("\n" + "="*50)
    print("           INTEGRATOR VOLUME SUMMARY")
    print("="*50)
    
    if not summary:
        print("No Chainflip transactions found in this time window.")
    else:
        for integrator, tokens in summary.items():
            print(f"\nIntegrator: {integrator.upper()}")
            print(f"{'  Token':<15} | {'Total Amount':<15}")
            print(f"  {'-'*30}")
            for symbol, total in tokens.items():
                print(f"  {symbol:<13} | {total:<15.4f}")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()