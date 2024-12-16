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
    return tx_data

def test_parse_op_return(hex_data, expected_version=0):
    """
    Test OP_RETURN parsing according to specification
    Format: 0x6a || 0x47 || Tag || Version || StakerPK || FinalityProviderPK || StakingTime
    """
    print("\nTesting OP_RETURN parsing:")
    print(f"Input: {hex_data}")
    
    # Check prefix
    if not hex_data.startswith('6a4762626e31'):
        print("❌ Invalid prefix")
        return None
    print("✓ Valid prefix (6a4762626e31)")
    
    # Remove prefix
    data = hex_data[10:]  # Skip 6a4762626e31
    
    try:
        # Detailed hex analysis
        print("\nHex Analysis:")
        print(f"Full data: {data}")
        print(f"First bytes: {' '.join(data[i:i+2] for i in range(0, 20, 2))}")
        
        # Try both version bytes
        first_byte = data[0:2]
        second_byte = data[2:4]
        
        print(f"\nVersion Analysis:")
        print(f"First byte (hex): {first_byte}")
        print(f"First byte (int): {int(first_byte, 16)}")
        print(f"First byte (ASCII): {bytes.fromhex(first_byte).decode('ascii')}")
        print(f"Second byte (hex): {second_byte}")
        print(f"Second byte (int): {int(second_byte, 16)}")
        
        # Use second byte as version
        version = int(second_byte, 16)
        if version != expected_version:
            print(f"❌ Invalid version: {version}")
            return None
            
        # Parse other fields (skip first two bytes)
        staker_pk = data[4:68]  # Skip both bytes
        fp_pk = data[68:132]
        staking_time = int(data[132:136], 16)
        
        print("\nParsed Fields:")
        print(f"Staker PK: {staker_pk}")
        print(f"FP PK: {fp_pk}")
        print(f"Staking Time: {staking_time}")
        
        return {
            'tag': '62626e31',
            'version': version,
            'staker_public_key': staker_pk,
            'finality_provider': fp_pk,
            'staking_time': staking_time,
            'raw_data': hex_data
        }
        
    except Exception as e:
        print(f"❌ Error parsing data: {str(e)}")
        print(f"Data: {data}")
        return None

def analyze_tx_data(txid):
    """
    Test transaction analysis with detailed logging
    """
    print("\nTransaction Analysis")
    print("=" * 50)
    
    # Get transaction data
    tx_json = get_transaction(txid)
    
    print("\nTransaction Details:")
    print(f"TXID: {txid}")
    print(f"Block Hash: {tx_json.get('blockhash')}")
    
    # Test OP_RETURN output
    op_return = None
    for vout in tx_json.get('vout', []):
        if vout['scriptPubKey'].get('type') == 'nulldata':
            op_return = vout['scriptPubKey'].get('hex')
            break
    
    if not op_return:
        print("❌ No OP_RETURN output found")
        return
    
    # Test parsing
    parsed = test_parse_op_return(op_return)
    if not parsed:
        print("❌ Failed to parse OP_RETURN data")
        return
    
    print("\n✓ Successfully parsed transaction")
    return parsed

# Test cases
test_cases = [
    # Known good transaction
    "4c1bae5ec398fac718fb1053afecb77cd79c5d1ab227924af16771d3cba25720",
    
    # Test with different versions (if available)
    "881eb9ee2ee7cbd30c8c148c5298a6ee32e921d718cf378622c6315e79a40523",
    
    # Add more test cases here
]

print("Starting OP_RETURN parsing tests...")
for txid in test_cases:
    print(f"\nTesting transaction: {txid}")
    result = analyze_tx_data(txid)
    if result:
        print(json.dumps(result, indent=2))