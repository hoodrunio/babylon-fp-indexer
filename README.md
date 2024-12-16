# Babylon Stake Indexer

A tool for tracking and analyzing Babylon stake transactions on the Bitcoin blockchain.

## Features

- Blockchain scanning via Bitcoin RPC
- Detection and analysis of Babylon stake transactions  
- OP_RETURN data parsing
- Finality Provider based statistics
- Detailed reporting in JSON format

## Installation

1. Install requirements: 
```
pip install -r requirements.txt
```

2. Create .env file and add required variables:
```
BTC_RPC_URL="your_rpc_url_here"
SCAN_RANGE="10" # Number of blocks to scan from the current block
```

3. Run:
```
python btc.py
```
    