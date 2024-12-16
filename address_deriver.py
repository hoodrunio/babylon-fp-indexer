from bitcoinutils.setup import setup
from bitcoinutils.utils import decode_base58
from bitcoinutils.keys import P2pkhAddress, P2shAddress, P2wpkhAddress, P2wshAddress, P2trAddress
from binascii import hexlify

def decode_address(address):
    """
    Decode any Bitcoin address format and return its type and decoded data.
    """
    # Initialize the bitcoinutils library
    setup('mainnet')
    
    try:
        # Try to identify address type and decode accordingly
        if address.startswith('1'):  # Legacy P2PKH
            decoded = decode_base58(address)
            if len(decoded) != 25:  # 1 byte version + 20 bytes hash + 4 bytes checksum
                raise ValueError("Invalid P2PKH address length")
            return {
                'type': 'p2pkh',
                'description': 'Pay to Public Key Hash (Legacy)',
                'decoded_data': hexlify(decoded[1:-4]).decode('utf-8'),  # Remove version byte and checksum
                'data_type': 'public_key_hash'
            }
            
        elif address.startswith('3'):  # P2SH
            decoded = decode_base58(address)
            if len(decoded) != 25:  # 1 byte version + 20 bytes hash + 4 bytes checksum
                raise ValueError("Invalid P2SH address length")
            return {
                'type': 'p2sh',
                'description': 'Pay to Script Hash',
                'decoded_data': hexlify(decoded[1:-4]).decode('utf-8'),  # Remove version byte and checksum
                'data_type': 'script_hash'
            }
            
        elif address.startswith('bc1q'):  # Native SegWit
            addr = P2wpkhAddress(address) if len(address) == 42 else P2wshAddress(address)
            witness_prog = addr.to_hash()
            return {
                'type': 'p2wpkh' if len(address) == 42 else 'p2wsh',
                'description': 'Pay to Witness Public Key Hash (Native SegWit)' if len(address) == 42 else 'Pay to Witness Script Hash',
                'decoded_data': hexlify(witness_prog).decode('utf-8'),
                'data_type': 'witness_program'
            }
            
        elif address.startswith('bc1p'):  # Taproot
            addr = P2trAddress(address)
            return {
                'type': 'p2tr',
                'description': 'Pay to Taproot',
                'decoded_data': hexlify(addr.to_hash()).decode('utf-8'),
                'data_type': 'taproot_public_key'
            }
            
        else:
            raise ValueError("Unsupported address format")
            
    except Exception as e:
        raise ValueError(f"Error decoding address: {str(e)}")

# Example usage
if __name__ == "__main__":
    # Example addresses for different formats
    addresses = [
        "bc1pjf35nf8k3y87t5pqwksch9mhpu7drpq2cqqnlcz5lm6cqp2lf69sd6s0lm"  # Taproot
    ]
    
    for addr in addresses:
        try:
            info = decode_address(addr)
            print(f"\nAddress: {addr}")
            print(f"Type: {info['description']}")
            print(f"Decoded data: {info['decoded_data']}")
        except ValueError as e:
            print(f"\nError with address {addr}: {str(e)}")