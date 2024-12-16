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
        Parses Babylon stake OP_RETURN data according to specification
        Format: 0x6a || 0x47 || Tag || "1" || Version || StakerPK || FinalityProviderPK || StakingTime
        """
        try:
            # Check prefix (0x6a = OP_RETURN, 0x47 = PUSH71, Tag = 62626e31)
            if not hex_data.startswith('6a4762626e31'):
                return None
            
            # Remove prefix
            data = hex_data[10:]  # Skip 6a4762626e31
            
            # Skip "1" prefix and get version
            version = int(data[2:4], 16)  # Second byte is version
            if version not in [0, 1, 2]:  # Support all known versions
                print(f"Unsupported version: {version}")
                return None
            
            # Parse other fields (skip first two bytes)
            staker_pk = data[4:68]  # Skip both prefix bytes
            fp_pk = data[68:132]
            staking_time = int(data[132:136], 16)
            
            return {
                'tag': '62626e31',
                'version': version,
                'staker_public_key': staker_pk,
                'finality_provider': fp_pk,
                'staking_time': staking_time,
                'raw_data': hex_data
            }
            
        except Exception as e:
            print(f"Error parsing OP_RETURN data: {str(e)}")
            return None
    
    def get_block_height(self, blockhash):
        """
        Gets block height from block hash
        """
        block = self._rpc_call('getblock', [blockhash])
        return block['height']
    
    def get_transaction_info(self, tx):
        """
        Analyzes transaction according to Babylon stake specification
        """
        try:
            txid = tx.get('txid', 'unknown')
            print(f"\nAnalyzing transaction: {txid}")
            
            vout = tx.get('vout', [])
            if len(vout) != 3:
                print(f"Skip: Wrong output count ({len(vout)})")
                return None
            
            # First output must be Taproot output with stake amount
            stake_output = vout[0]
            if stake_output['scriptPubKey'].get('type') != 'witness_v1_taproot':
                print(f"Skip: First output is not Taproot")
                return None
            
            stake_amount = int(stake_output['value'] * 100000000)  # BTC to satoshi
            print(f"Stake amount: {stake_amount} satoshi")
            
            # First parse OP_RETURN to get version
            op_return_data = vout[1]['scriptPubKey']['hex']
            parsed_data = self.parse_op_return(op_return_data)
            if not parsed_data:
                return None
            
            # Get parameters for this transaction's version
            block_height = tx.get('block_height')
            if not block_height:
                block_height = self.get_block_height(tx['blockhash'])
            
            params = self.get_params_for_height(block_height, parsed_data['version'])
            if not params:
                print(f"Skip: No parameters found for height {block_height}")
                return None
            
            # Verify version matches parameters
            if parsed_data['version'] != params['version']:
                print(f"Skip: Version mismatch (tx: {parsed_data['version']}, params: {params['version']})")
                return None
            
            # Validate parameters according to version
            if stake_amount < params['min_staking_amount']:
                print(f"Skip: Stake amount too low for version {params['version']}")
                return None
            
            # Validate stake amount
            if stake_amount > params['max_staking_amount']:
                print(f"Skip: Stake amount too high ({stake_amount} > {params['max_staking_amount']})")
                return None
            
            # Second output must be OP_RETURN
            op_return_output = vout[1]
            if op_return_output['scriptPubKey'].get('type') != 'nulldata':
                print(f"Skip: Second output is not OP_RETURN")
                return None
            
            op_return_data = op_return_output['scriptPubKey']['hex']
            print(f"OP_RETURN data: {op_return_data}")
            
            parsed_data = self.parse_op_return(op_return_data)
            if not parsed_data:
                print(f"Skip: Could not parse OP_RETURN data")
                return None
            
            # Validate staking time
            if parsed_data['staking_time'] < params['min_staking_time']:
                print(f"Skip: Staking time too low ({parsed_data['staking_time']} < {params['min_staking_time']})")
                return None
            if parsed_data['staking_time'] > params['max_staking_time']:
                print(f"Skip: Staking time too high ({parsed_data['staking_time']} > {params['max_staking_time']})")
                return None
            
            # Get staker address from last output
            staker_output = vout[2]
            staker_address = staker_output['scriptPubKey'].get('address')
            print(f"Staker address: {staker_address}")
            
            print("Transaction is valid Babylon stake!")
            return {
                'txid': txid,
                'block_height': block_height,
                'timestamp': tx.get('blocktime') or tx.get('time'),
                'stake_amount': stake_amount,
                'staker_address': staker_address,
                'staker_public_key': parsed_data['staker_public_key'],
                'finality_provider': parsed_data['finality_provider'],
                'staking_time': parsed_data['staking_time'],
                'version': parsed_data['version'],
                'params_version': params['version'],  # Add params version for reference
                'is_babylon_stake': True
            }
            
        except Exception as e:
            print(f"Error analyzing transaction: {str(e)} - TX: {txid}")
            return None
    
    def scan_blocks(self, start_height, end_height, batch_size=10):
        stats = {
            'total_tx': 0,
            'babylon_prefix': 0,
            'valid_stake': 0
        }
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
                        stats['total_tx'] += 1
                        
                        # Quick check for potential Babylon transactions
                        has_babylon_output = False
                        for vout in tx.get('vout', []):
                            if (vout['scriptPubKey'].get('type') == 'nulldata' and 
                                vout['scriptPubKey'].get('hex', '').startswith('6a4762626e31')):
                                has_babylon_output = True
                                stats['babylon_prefix'] += 1
                                break
                        
                        if not has_babylon_output:
                            continue
                            
                        # Only analyze transactions with Babylon prefix
                        tx['blockhash'] = block['hash']
                        tx['block_height'] = block['height']
                        tx['blocktime'] = block['time']
                        
                        tx_info = self.get_transaction_info(tx)
                        if tx_info:
                            print(f"\nStake transaction found: {tx_info['txid']}")
                            print(f"Block: {tx_info['block_height']}")
                            print(f"Amount: {tx_info['stake_amount']/100000000:.8f} BTC")
                            all_transactions.append(tx_info)
                            stats['valid_stake'] += 1
                            
                except Exception as e:
                    print(f"\nError processing block {block_height}: {str(e)}")
                    continue
        
        print("\n\nScan completed!")
        print(f"Total blocks scanned: {total_blocks}")
        print(f"Total stake transactions found: {len(all_transactions)}")
        
        print("\nScan Statistics:")
        print(f"Total transactions: {stats['total_tx']}")
        print(f"Babylon prefix found: {stats['babylon_prefix']}")
        print(f"Valid stake transactions: {stats['valid_stake']}")
        
        return all_transactions

    def analyze_transactions(self, transactions):
        """
        Analyzes Babylon stake transactions and outputs detailed metrics
        """
        stake_info = {
            'total_stake_amount': 0,
            'unique_stakers': set(),
            'finality_providers': {},
            'transactions': [],
            'blocks': set(),
            'time_range': {'first': None, 'last': None},
            'versions': {}  # Version bazlı istatistikler
        }
        
        for tx in transactions:
            if tx and tx.get('is_babylon_stake'):
                amount = tx['stake_amount']
                fp = tx['finality_provider']
                version = tx['version']
                block = tx['block_height']
                timestamp = tx['timestamp']
                
                # Version bazlı istatistikler
                if version not in stake_info['versions']:
                    stake_info['versions'][version] = {
                        'total_stake': 0,
                        'transaction_count': 0,
                        'unique_stakers': set(),
                        'unique_fps': set(),
                        'blocks': set(),
                        'time_range': {'first': None, 'last': None}
                    }
                
                ver_stats = stake_info['versions'][version]
                ver_stats['total_stake'] += amount
                ver_stats['transaction_count'] += 1
                ver_stats['unique_stakers'].add(tx['staker_address'])
                ver_stats['unique_fps'].add(fp)
                ver_stats['blocks'].add(block)
                
                # Version için zaman aralığı
                if not ver_stats['time_range']['first'] or timestamp < ver_stats['time_range']['first']:
                    ver_stats['time_range']['first'] = timestamp
                if not ver_stats['time_range']['last'] or timestamp > ver_stats['time_range']['last']:
                    ver_stats['time_range']['last'] = timestamp
                
                # FP bazlı istatistikler
                if fp not in stake_info['finality_providers']:
                    stake_info['finality_providers'][fp] = {
                        'total_stake': 0,
                        'unique_stakers': set(),
                        'transactions': [],
                        'blocks': set(),
                        'versions': set(),
                        'time_range': {'first': None, 'last': None}
                    }
                
                fp_stats = stake_info['finality_providers'][fp]
                fp_stats['total_stake'] += amount
                fp_stats['unique_stakers'].add(tx['staker_address'])
                fp_stats['transactions'].append(tx)
                fp_stats['blocks'].add(block)
                fp_stats['versions'].add(version)
                
                # FP için zaman aralığı
                if not fp_stats['time_range']['first'] or timestamp < fp_stats['time_range']['first']:
                    fp_stats['time_range']['first'] = timestamp
                if not fp_stats['time_range']['last'] or timestamp > fp_stats['time_range']['last']:
                    fp_stats['time_range']['last'] = timestamp
                
                # Genel istatistikler
                stake_info['total_stake_amount'] += amount
                stake_info['unique_stakers'].add(tx['staker_address'])
                stake_info['transactions'].append(tx)
                stake_info['blocks'].add(block)
                
                # Genel zaman aralığı
                if not stake_info['time_range']['first'] or timestamp < stake_info['time_range']['first']:
                    stake_info['time_range']['first'] = timestamp
                if not stake_info['time_range']['last'] or timestamp > stake_info['time_range']['last']:
                    stake_info['time_range']['last'] = timestamp
        
        # JSON çıktısını hazırla
        output = {
            'summary': {
                'total_stake_btc': stake_info['total_stake_amount'] / 100000000,
                'unique_stakers_count': len(stake_info['unique_stakers']),
                'total_transactions': len(stake_info['transactions']),
                'finality_provider_count': len(stake_info['finality_providers']),
                'unique_blocks': len(stake_info['blocks']),
                'time_range': {
                    'first_timestamp': stake_info['time_range']['first'],
                    'last_timestamp': stake_info['time_range']['last'],
                    'duration_seconds': stake_info['time_range']['last'] - stake_info['time_range']['first']
                    if stake_info['time_range']['first'] and stake_info['time_range']['last'] else 0
                }
            },
            'versions': {
                str(ver): {
                    'total_stake_btc': info['total_stake'] / 100000000,
                    'transaction_count': info['transaction_count'],
                    'unique_stakers': len(info['unique_stakers']),
                    'unique_fps': len(info['unique_fps']),
                    'unique_blocks': len(info['blocks']),
                    'time_range': {
                        'first_timestamp': info['time_range']['first'],
                        'last_timestamp': info['time_range']['last'],
                        'duration_seconds': info['time_range']['last'] - info['time_range']['first']
                        if info['time_range']['first'] and info['time_range']['last'] else 0
                    }
                }
                for ver, info in stake_info['versions'].items()
            },
            'finality_providers': {
                fp: {
                    'total_stake_btc': info['total_stake'] / 100000000,
                    'unique_stakers_count': len(info['unique_stakers']),
                    'transaction_count': len(info['transactions']),
                    'unique_blocks': len(info['blocks']),
                    'versions_used': list(info['versions']),
                    'average_stake_btc': (info['total_stake'] / len(info['transactions'])) / 100000000
                    if info['transactions'] else 0,
                    'time_range': {
                        'first_timestamp': info['time_range']['first'],
                        'last_timestamp': info['time_range']['last'],
                        'duration_seconds': info['time_range']['last'] - info['time_range']['first']
                        if info['time_range']['first'] and info['time_range']['last'] else 0
                    }
                }
                for fp, info in stake_info['finality_providers'].items()
            },
            'transactions': [
                {
                    'txid': tx['txid'],
                    'block_height': tx['block_height'],
                    'timestamp': tx['timestamp'],
                    'stake_amount_btc': tx['stake_amount'] / 100000000,
                    'staker_address': tx['staker_address'],
                    'finality_provider': tx['finality_provider'],
                    'version': tx['version']
                }
                for tx in stake_info['transactions']
            ]
        }
        
        return output

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

    def get_params_for_height(self, height, tx_version=None):
        """
        Gets parameters valid for given block height and transaction version
        """
        try:
            with open('global-params.json', 'r') as f:
                params = json.load(f)
                
            print(f"\nLooking for parameters at height {height} (tx version: {tx_version})")
            
            # Find applicable version for height
            current_params = None
            
            # If tx_version is provided, first try to find matching version
            if tx_version is not None:
                for version in params['versions']:
                    if version['version'] == tx_version and version['activation_height'] <= height:
                        if 'cap_height' in version:
                            if height <= version['cap_height']:
                                current_params = version
                                print(f"Found matching version {version['version']} for tx")
                                break
                        else:
                            current_params = version
                            print(f"Found matching version {version['version']} for tx")
                            break
            
            # If no matching version found, find latest applicable version
            if not current_params:
                for version in reversed(params['versions']):
                    activation_height = version['activation_height']
                    if activation_height <= height:
                        if 'cap_height' in version:
                            cap_height = version['cap_height']
                            if height <= cap_height:
                                current_params = version
                                break
                        else:
                            current_params = version
                            break
                        
            if current_params:
                print(f"Using parameters version {current_params['version']}")
            else:
                print("No valid parameters found")
                
            return current_params
                
        except Exception as e:
            print(f"Error loading parameters: {str(e)}")
            return None

    def save_analysis(self, analysis):
        """
        Saves analysis results to babylon-stake-analysis.json
        """
        try:
            with open('babylon-stake-analysis.json', 'w') as f:
                json.dump(analysis, f, indent=2)
            print(f"\nAnalysis results saved to babylon-stake-analysis.json")
        except Exception as e:
            print(f"Error saving analysis: {str(e)}")

if __name__ == '__main__':
    indexer = BabylonStakeIndexer()
    
    # Get scan range from env or use default
    scan_range = int(os.getenv('SCAN_RANGE', '50'))
    target_height = indexer._rpc_call('getblockcount', [])
    start_height = target_height - scan_range 
    end_height = target_height
    
    print(f"Scanning blocks: {start_height} - {end_height}")
    
    # Scan blocks and analyze transactions
    transactions = indexer.scan_blocks(start_height, end_height)
    
    # Save raw transaction data
    try:
        with open('babylon-transactions.json', 'w') as f:
            json.dump(transactions, f, indent=2)
        print(f"Raw transactions saved to babylon-transactions.json")
    except Exception as e:
        print(f"Error saving transactions: {str(e)}")
        
    # Analyze and save detailed metrics
    analysis = indexer.analyze_transactions(transactions)
    indexer.save_analysis(analysis)