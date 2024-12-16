import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

class BabylonStakeIndexer:
    def __init__(self):
        self.rpc_url = os.getenv('BTC_RPC_URL')
        if not self.rpc_url:
            raise ValueError("BTC_RPC_URL environment variable is not set")
        self.headers = {'content-type': 'application/json'}
    
    def _rpc_call(self, method, params=[]):
        payload = {
            "jsonrpc": "1.0",
            "id": "btc",
            "method": method,
            "params": params
        }
        response = requests.post(self.rpc_url, json=payload, headers=self.headers)
        return response.json()['result']
    
    def parse_op_return(self, hex_data):
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
        
        # Check suffix
        if not chunks[2][4:] == 'fa00':
            return None
        
        return {
            'prefix': '6a4762626e31',
            'random_data': chunks[0],
            'finality_provider': fp_address,
            'suffix': 'fa00',
            'raw_data': hex_data
        }
    
    def get_transaction_info(self, tx):
        """
        Analyzes each transaction in detail and detects Babylon stake transactions
        """
        try:
            vout = tx.get('vout', [])
            if len(vout) != 3:  # Must have exactly 3 outputs
                return None
                
            # First output contains stake amount
            stake_output = vout[0]
            
            # Second output must be OP_RETURN
            op_return_output = vout[1]
            op_return_data = op_return_output.get('scriptPubKey', {}).get('hex', '')
            
            # Parse OP_RETURN data
            parsed_data = self.parse_op_return(op_return_data)
            if not parsed_data:
                return None
                
            # Block info - check both possible locations
            block_height = None
            if 'block' in tx and 'height' in tx['block']:
                block_height = tx['block']['height']
            elif 'height' in tx:
                block_height = tx['height']
            
            # Timestamp - check both possible locations
            timestamp = None
            if 'time' in tx:
                timestamp = tx['time']
            elif 'blocktime' in tx:
                timestamp = tx['blocktime']
            
            # Address info
            stake_script = stake_output.get('scriptPubKey', {})
            stake_address = None
            if 'address' in stake_script:
                stake_address = stake_script['address']
            elif 'addresses' in stake_script and stake_script['addresses']:
                stake_address = stake_script['addresses'][0]
            
            # Change address
            change_output = vout[2]
            change_script = change_output.get('scriptPubKey', {})
            change_address = None
            if 'address' in change_script:
                change_address = change_script['address']
            elif 'addresses' in change_script and change_script['addresses']:
                change_address = change_script['addresses'][0]
            
            return {
                'txid': tx['txid'],
                'block_height': block_height,
                'timestamp': timestamp,
                'stake_amount': stake_output.get('value', 0),
                'staker_address': stake_address,
                'change_address': change_address,
                'finality_provider': parsed_data['finality_provider'],
                'op_return': parsed_data,
                'is_babylon_stake': True
            }
            
        except Exception as e:
            print(f"Error analyzing transaction: {str(e)} - TX: {tx.get('txid', 'unknown')}")
            return None
    
    def scan_blocks(self, start_height, end_height, batch_size=10):
        all_transactions = []
        total_blocks = end_height - start_height + 1
        processed_blocks = 0
        
        print(f"\nScanning {total_blocks} blocks")
        print(f"Start block: {start_height}")
        print(f"End block: {end_height}\n")
        
        for height in range(start_height, end_height + 1, batch_size):
            batch_end = min(height + batch_size, end_height + 1)
            processed_blocks += batch_end - height
            progress = (processed_blocks / total_blocks) * 100
            
            print(f"Progress: {progress:.1f}% | Blocks: {height} - {batch_end-1}", end='\r')
            
            for block_height in range(height, batch_end):
                try:
                    block_hash = self._rpc_call('getblockhash', [block_height])
                    block = self._rpc_call('getblock', [block_hash, 2])
                    
                    for tx in block['tx']:
                        tx_info = self.get_transaction_info(tx)
                        if tx_info:
                            print(f"\nStake transaction found: {tx_info['txid']}")
                            print(f"Block: {tx_info['block_height']}")
                            print(f"Amount: {tx_info['stake_amount']/100000000:.8f} BTC")
                            all_transactions.append(tx_info)
                            
                except Exception as e:
                    print(f"\nError processing block {block_height}: {str(e)}")
                    continue
        
        print("\n\nScan completed!")
        print(f"Total blocks scanned: {total_blocks}")
        print(f"Total stake transactions found: {len(all_transactions)}")
        
        return all_transactions

    def analyze_transactions(self, transactions):
        """
        Analyzes Babylon stake transactions and groups by FP
        """
        stake_info = {
            'total_stake_amount': 0,
            'unique_stakers': set(),
            'finality_providers': {},
            'transactions': []
        }
        
        for tx in transactions:
            if tx and tx.get('is_babylon_stake'):
                amount = tx['stake_amount']
                fp = tx['finality_provider']
                
                # FP based statistics
                if fp not in stake_info['finality_providers']:
                    stake_info['finality_providers'][fp] = {
                        'total_stake': 0,
                        'unique_stakers': set(),
                        'transactions': []
                    }
                
                fp_info = stake_info['finality_providers'][fp]
                fp_info['total_stake'] += amount
                fp_info['unique_stakers'].add(tx['staker_address'])
                fp_info['transactions'].append(tx)
                
                # General statistics
                stake_info['total_stake_amount'] += amount
                stake_info['unique_stakers'].add(tx['staker_address'])
                stake_info['transactions'].append(tx)
        
        # Save results to file
        output = {
            'summary': {
                'total_stake_btc': stake_info['total_stake_amount'] / 100000000,
                'unique_stakers_count': len(stake_info['unique_stakers']),
                'total_transactions': len(stake_info['transactions']),
                'finality_provider_count': len(stake_info['finality_providers'])
            },
            'finality_providers': {}
        }
        
        # Detailed info for each FP
        for fp, fp_info in stake_info['finality_providers'].items():
            output['finality_providers'][fp] = {
                'total_stake_btc': fp_info['total_stake'] / 100000000,
                'unique_stakers_count': len(fp_info['unique_stakers']),
                'transaction_count': len(fp_info['transactions']),
                'transactions': sorted([{
                    'txid': tx['txid'],
                    'block_height': tx['block_height'] if tx['block_height'] is not None else 'unknown',
                    'timestamp': tx['timestamp'] if tx['timestamp'] is not None else 'unknown',
                    'stake_amount_btc': tx['stake_amount'] / 100000000,
                    'staker_address': tx['staker_address'] if tx['staker_address'] is not None else 'unknown'
                } for tx in fp_info['transactions']], 
                key=lambda x: x['block_height'] if x['block_height'] != 'unknown' else float('inf'))
            }
        
        # Write results to file
        with open('babylon-point.json', 'w') as f:
            json.dump(output, f, indent=2)
        
        # Print summary
        print("\nBabylon Stake Analysis:")
        print(f"Total stake amount: {output['summary']['total_stake_btc']:.8f} BTC")
        print(f"Unique staker count: {output['summary']['unique_stakers_count']}")
        print(f"Total stake transactions: {output['summary']['total_transactions']}")
        print(f"Finality Provider count: {output['summary']['finality_provider_count']}")
        
        print("\nDistribution by Finality Provider:")
        for fp, info in output['finality_providers'].items():
            print(f"\nFP: {fp}")
            print(f"Total stake: {info['total_stake_btc']:.8f} BTC")
            print(f"Unique stakers: {info['unique_stakers_count']}")
            print(f"Transaction count: {info['transaction_count']}")
        
        return stake_info

    def debug_transaction(self, txid):
        """
        Analyzes a specific transaction in detail and shows OP_RETURN content
        """
        try:
            # Get transaction
            tx = self._rpc_call('getrawtransaction', [txid, True])
            
            print("\nTransaction Debug Information:")
            print(f"TXID: {txid}")
            print("\nOutputs:")
            
            for i, vout in enumerate(tx.get('vout', [])):
                print(f"\nOutput #{i}:")
                print(f"Value: {vout.get('value', 0)} BTC")
                
                scriptPubKey = vout.get('scriptPubKey', {})
                print(f"Script Type: {scriptPubKey.get('type', 'unknown')}")
                
                if 'addresses' in scriptPubKey:
                    print(f"Address: {scriptPubKey['addresses'][0]}")
                    
                if scriptPubKey.get('type') == 'nulldata':
                    print(f"OP_RETURN Hex: {scriptPubKey.get('hex', '')}")
                    print(f"ASM: {scriptPubKey.get('asm', '')}")
            
            return tx
            
        except Exception as e:
            print(f"Error debugging transaction: {str(e)}")
            return None

indexer = BabylonStakeIndexer()

# Get scan range from env or use default
scan_range = int(os.getenv('SCAN_RANGE', '50'))
target_height = indexer._rpc_call('getblockcount', [])
start_height = target_height - scan_range 
end_height = target_height

print(f"Scanning blocks: {start_height} - {end_height}")
transactions = indexer.scan_blocks(start_height, end_height)
patterns = indexer.analyze_transactions(transactions)