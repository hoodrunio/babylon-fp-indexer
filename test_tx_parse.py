import requests
import json
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

def get_transaction(txid):
    """
    Gets transaction details via RPC
    """
    rpc_url = os.getenv('BTC_RPC_URL')
    if not rpc_url:
        raise ValueError("BTC_RPC_URL environment variable is not set")
    
    headers = {'content-type': 'application/json'}
    
    # First get raw transaction
    tx_payload = {
        "jsonrpc": "1.0",
        "id": "btc",
        "method": "getrawtransaction",
        "params": [txid, True]
    }
    
    tx_response = requests.post(rpc_url, json=tx_payload, headers=headers)
    tx_data = tx_response.json()['result']
    
    # Then get block info
    if 'blockhash' in tx_data:
        block_payload = {
            "jsonrpc": "1.0",
            "id": "btc",
            "method": "getblock",
            "params": [tx_data['blockhash']]
        }
        block_response = requests.post(rpc_url, json=block_payload, headers=headers)
        block_data = block_response.json()['result']
        tx_data['block_height'] = block_data['height']
    
    return tx_data

def analyze_tx_data(txid):
    """
    Analyzes transaction data from RPC
    """
    print("\nTransaction Analysis")
    print("=" * 50)
    
    # Get transaction data
    tx_json = get_transaction(txid)
    
    print("\nTransaction Details:")
    print(f"TXID: {txid}")
    print(f"Block Hash: {tx_json.get('blockhash')}")
    print(f"Block Height: {tx_json.get('block_height')}")
    print(f"Time: {tx_json.get('time')}")
    print(f"Blocktime: {tx_json.get('blocktime')}")
    
    print("\nInputs:")
    for i, vin in enumerate(tx_json.get('vin', [])):
        print(f"\nInput #{i}:")
        print(json.dumps(vin, indent=2))
    
    print("\nOutputs:")
    for i, vout in enumerate(tx_json.get('vout', [])):
        print(f"\nOutput #{i}:")
        print(json.dumps(vout, indent=2))
    
    # Extract key information
    stake_amount = int(tx_json['vout'][0]['value'] * 100000000)  # Convert BTC to satoshi
    staker_address = tx_json['vout'][2]['scriptPubKey'].get('address')
    block_height = tx_json.get('block_height')
    timestamp = tx_json.get('blocktime') or tx_json.get('time')
    
    print("\nExtracted Information:")
    print(f"Stake Amount: {stake_amount} satoshi ({stake_amount/100000000:.8f} BTC)")
    print(f"Staker Address: {staker_address}")
    print(f"Block Height: {block_height}")
    print(f"Timestamp: {timestamp}")

# Test with new transaction
test_txid = "4c1bae5ec398fac718fb1053afecb77cd79c5d1ab227924af16771d3cba25720"
analyze_tx_data(test_txid)