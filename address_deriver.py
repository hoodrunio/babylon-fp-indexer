from bitcoinutils.setup import setup
import requests
import json
import os
from base58 import b58decode
from binascii import hexlify
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import time

class BTCAddressDeriver:
    """
    Bitcoin address public key deriver.
    Supports:
    - Legacy (1...)
    - P2SH-SegWit (3...)
    - Native SegWit (bc1q...)
    - Taproot (bc1p...)
    """
    
    def __init__(self):
        load_dotenv()
        self.blockstream_api = "https://blockstream.info/api"
        setup('mainnet')
    
    def parse_op_return(self, script):
        """Parse Babylon OP_RETURN data"""
        try:
            if script.startswith('6a4762626e31'):
                return script[14:14+64]
            return None
        except Exception as e:
            print(f"Error parsing OP_RETURN: {str(e)}")
            return None

    def get_transaction_details(self, txid):
        """Get transaction details with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                tx_url = f"{self.blockstream_api}/tx/{txid}"
                response = requests.get(tx_url, timeout=10)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:  # Rate limit
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)
        return None

    def process_single_address(self, address):
        """Process a single address"""
        try:
            print(f"\nProcessing address: {address}")
            
            # Get address transactions
            url = f"{self.blockstream_api}/address/{address}/txs"
            response = requests.get(url)
            if response.status_code != 200:
                raise ValueError(f"API request failed with status {response.status_code}")
                
            txs = response.json()
            if not txs:
                raise ValueError("No transactions found")
                
            # Process transactions concurrently using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=10) as executor:
                tx_details = list(executor.map(self.get_transaction_details, 
                                            [tx['txid'] for tx in txs]))
            
            # Process each transaction
            for tx in tx_details:
                if not tx:
                    continue
                    
                # First check for Babylon OP_RETURN
                for vout in tx.get('vout', []):
                    if vout.get('scriptpubkey_type') == 'op_return':
                        script = vout['scriptpubkey']
                        print(f"Found OP_RETURN: {script}")
                        pubkey = self.parse_op_return(script)
                        if pubkey:
                            print(f"Found pubkey via OP_RETURN for {address}")
                            return address, pubkey
                
                # If no OP_RETURN, try address-specific methods
                if address.startswith('1'):  # Legacy
                    for vin in tx.get('vin', []):
                        if 'scriptsig' in vin:
                            script = vin['scriptsig']
                            parts = script.split()
                            for part in parts:
                                if len(part) in [66, 130]:
                                    print(f"Found pubkey via scriptsig for {address}")
                                    return address, part
                                    
                elif address.startswith('3'):  # P2SH-SegWit
                    for vin in tx.get('vin', []):
                        if 'witness' in vin:
                            for item in vin['witness']:
                                if len(item) in [66, 130]:
                                    print(f"Found pubkey via witness for {address}")
                                    return address, item
                                    
                elif address.startswith('bc1q'):  # Native SegWit
                    for vin in tx.get('vin', []):
                        if 'witness' in vin:
                            for witness_item in vin['witness']:
                                if len(witness_item) == 66:
                                    pubkey = witness_item[2:] if witness_item.startswith('02') else witness_item
                                    print(f"Found pubkey via witness for {address}")
                                    return address, pubkey
                                    
                elif address.startswith('bc1p'):  # Taproot
                    # First try OP_RETURN in all outputs
                    for vout in tx.get('vout', []):
                        if vout.get('scriptpubkey_type') == 'op_return':
                            script = vout['scriptpubkey']
                            if script.startswith('6a4762626e31'):  # Babylon identifier
                                pubkey = self.parse_op_return(script)
                                if pubkey:
                                    print(f"Found pubkey via Babylon OP_RETURN for {address}")
                                    return address, pubkey
                    
                    # Then try scriptPubKey in outputs
                    for vout in tx.get('vout', []):
                        if vout.get('scriptpubkey_address') == address:
                            script = vout['scriptpubkey']
                            if script.startswith('5120'):  # OP_1 PUSH32
                                pubkey = script[4:]  # Skip OP_1 and PUSH32
                                print(f"Found pubkey via scriptpubkey for {address}")
                                return address, pubkey
            
            raise ValueError("Could not find public key in transactions")
            
        except Exception as e:
            print(f"Error processing {address}: {str(e)}")
            return address, None

    def process_addresses(self, addresses, batch_size=10):
        """Process multiple addresses concurrently"""
        result = {"data": {}}
        
        # Process addresses in batches
        for i in range(0, len(addresses), batch_size):
            batch = addresses[i:i + batch_size]
            
            # Process batch concurrently
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                batch_results = list(executor.map(self.process_single_address, batch))
            
            # Collect results
            for address, pubkey in batch_results:
                if pubkey:
                    result["data"][address] = pubkey
                    print(f"Successfully processed address: {address}")
                
        return result

if __name__ == "__main__":
    # Test addresses for different formats
    addresses = [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Legacy (Genesis address)
        "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",  # P2SH-SegWit
        "bc1q7rj34aw9e0kgnkn0aakxa9slsvwyle92atmv4m",  # Native SegWit
        "bc1pjf35nf8k3y87t5pqwksch9mhpu7drpq2cqqnlcz5lm6cqp2lf69sd6s0lm"  # Taproot
    ]
    
    print("Starting address derivation process...")
    deriver = BTCAddressDeriver()
    result = deriver.process_addresses(addresses)
    print("\nFinal result:")
    print(json.dumps(result, indent=2))