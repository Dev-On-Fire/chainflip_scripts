import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# --- CONFIGURATION ---
TARGET_ADDRESS = "bc1p5x9r9rm8xmsldk046ewu4qf80z5yugwh5ntgz6n25nft88gxxtwsfezq3z" ##chainflip btc wallet
BLOCK_WINDOW = 6
FILTER_PARTNER = "Phantom Wallet"
MIN_FEE_PCT = 0.75
MAX_FEE_PCT = 0.85

def get_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=2, 
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
    return session

def analyze_btc_final_v12(tx_hash, session):
    FEE_WALLETS = {
        "bc1pt5zrlm55lmfwq7sjsuzgpgkmm7fymkna375l8kyuu5p6cq77545q554mgr": "Phantom Wallet"
    }

    url = f"https://mempool.space/api/tx/{tx_hash}"
    try:
        response = session.get(url)
        if response.status_code != 200: return None
        data = response.json()
        
        partner = "Jumper / Li.Fi Generic"
        bridge_val = 0
        fee_val = 0
        fee_wallet_found = None

        for out in data['vout']:
            addr = out.get('scriptpubkey_address', '')
            val = out.get('value', 0)
            if out.get('scriptpubkey', '').startswith('6a'): continue

            if addr in FEE_WALLETS:
                partner = FEE_WALLETS[addr]
                fee_val = val
                fee_wallet_found = addr
            else:
                if val > bridge_val: bridge_val = val

        total_user_paid_sats = bridge_val + fee_val
        fee_percentage = (fee_val / total_user_paid_sats * 100) if total_user_paid_sats > 0 else 0

        return {
            "TXID": tx_hash,
            "Partner": partner,
            "Total_BTC_Paid": f"{total_user_paid_sats / 100_000_000:.8f}",
            "Bridge_Net_Amount": f"{bridge_val / 100_000_000:.8f}",
            "Partner_Fee_Taken": f"{fee_val / 100_000_000:.8f}",
            "Fee_Percentage": f"{fee_percentage:.2f}%",
            "Fee_Wallet_Used": fee_wallet_found if fee_wallet_found else "None"
        }
    except Exception:
        return None

def run_integrated_analysis():
    session = get_session()
    parent_txids = set()
    filtered_total_sum = 0.0
    found_count = 0
    
    try:
        tip = session.get("https://mempool.space/api/blocks/tip/height").json()
        min_h = tip - BLOCK_WINDOW
        
        print(f"Scanning blocks {min_h} to {tip}...")
        print(f"Filtering for: {FILTER_PARTNER} with Fee between {MIN_FEE_PCT}% and {MAX_FEE_PCT}%\n")
        
        # 1. Collect unique parent TXIDs
        addr_url = f"https://mempool.space/api/address/{TARGET_ADDRESS}/txs"
        my_txs = session.get(addr_url).json()

        for tx in my_txs:
            height = tx.get("status", {}).get("block_height")
            if height and height >= min_h:
                for vin in tx.get("vin", []):
                    if vin.get("txid"):
                        parent_txids.add(vin.get("txid"))

        # 2. Analyze and Filter
        for p_txid in parent_txids:
            res = analyze_btc_final_v12(p_txid, session)
            
            if res and res["Partner"] == FILTER_PARTNER:
                # Convert "0.81%" -> 0.81
                pct_val = float(res["Fee_Percentage"].replace('%', ''))
                
                # Check range
                if MIN_FEE_PCT <= pct_val <= MAX_FEE_PCT:
                    print(res)
                    filtered_total_sum += float(res["Total_BTC_Paid"])
                    found_count += 1
            
            time.sleep(1.0) # Rate limiting

        print("\n" + "="*60)
        print(f"SUMMARY (Partner: {FILTER_PARTNER} | Fee: {MIN_FEE_PCT}-{MAX_FEE_PCT}%)")
        print(f"Transactions: {found_count}")
        print(f"Total Sum: {filtered_total_sum:.8f} BTC")
        print("="*60)

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    run_integrated_analysis()