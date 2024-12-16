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
    
    payload = {
        "jsonrpc": "1.0",
        "id": "btc",
        "method": "getrawtransaction",
        "params": [txid, True]
    }
    
    response = requests.post(rpc_url, json=payload, headers=headers)
    return response.json()['result']

def parse_op_return(hex_data):
    """
    Parses OP_RETURN data and extracts FP address
    """
    # Check prefix
    if not hex_data.startswith('6a4762626e31'):
        return None
    
    # Remove prefix
    data = hex_data[10:]
    
    # Split into 64 character chunks
    chunks = [data[i:i+64] for i in range(0, len(data), 64)]
    if len(chunks) < 3:
        return None
    
    # FP address: last 60 chars of chunk1 + first 4 chars of chunk2
    fp_address = chunks[1][-60:] + chunks[2][:4]
    
    return {
        'prefix': '6a4762626e31',
        'random_data': chunks[0],
        'finality_provider': fp_address,
        'suffix': chunks[2][4:],  # fa00
        'raw_data': hex_data
    }

def analyze_op_return(txid, expected_fp):
    """
    Analyzes OP_RETURN data of a transaction
    """
    print(f"\n{'='*80}")
    print(f"Transaction: {txid}")
    print(f"Expected FP: {expected_fp}")
    
    tx = get_transaction(txid)
    op_return = next(
        (out for out in tx['vout'] if out['scriptPubKey']['type'] == 'nulldata'),
        None
    )
    
    if not op_return:
        print("OP_RETURN not found!")
        return
    
    hex_data = op_return['scriptPubKey']['hex']
    result = parse_op_return(hex_data)
    
    if not result:
        print("Could not parse!")
        return
    
    print("\nParse Result:")
    print(f"Random Data: {result['random_data']}")
    print(f"FP Address: {result['finality_provider']}")
    print(f"Suffix: {result['suffix']}")
    print(f"Is Correct: {result['finality_provider'] == expected_fp}")

# Test cases
test_cases = [
    {
        'txid': '881eb9ee2ee7cbd30c8c148c5298a6ee32e921d718cf378622c6315e79a40523',
        'fp': '609b4b8e27e214fd830e69a83a8270a03f7af356f64dde433a7e4b81b2399806'
    },
    {
        'txid': 'af3f3d6c9857c5bb4dbc98a0411bf1d832e32561b659bb25ed8076d9e591332c',
        'fp': '609b4b8e27e214fd830e69a83a8270a03f7af356f64dde433a7e4b81b2399806'
    },
    {
        'txid': '4d1ebf3ef7719898c2240fb6cad32a0376698a8d20a94a463e7f82bc9bbdeb69',
        'fp': '67732ad150b6bd773f24d250be3c65c6a7aff77abbd1ed4196b8f889374dda8a'
    },
    {
        'txid': 'e9e672c298f87b3e6536f4e1a1f133fc31cfe049e052da6c9be5a49908d1318e',
        'fp': '609b4b8e27e214fd830e69a83a8270a03f7af356f64dde433a7e4b81b2399806'
    },
    {
        'txid': '1f14369c026d77f4dea5e10bbc37f8c3eb0f1db1529f22c3af94581be0613d2a',
        'fp': '609b4b8e27e214fd830e69a83a8270a03f7af356f64dde433a7e4b81b2399806'
    }
]

for case in test_cases:
    analyze_op_return(case['txid'], case['fp'])