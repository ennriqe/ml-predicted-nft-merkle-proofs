import json
import os
import time
import sqlite3
from web3 import Web3
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import math
import secrets
import struct
import uuid
import sqlite3
from typing import Dict, List, Tuple
from Crypto.Hash import keccak

def keccak256(x: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(x)
    return h.digest()

def pair_hash(a: bytes, b: bytes) -> bytes:
    return keccak256(a + b)

def ceil_log2(n: int) -> int:
    return math.ceil(math.log2(n)) if n > 0 else 0

def create_merkle_leaves(df: pd.DataFrame) -> Tuple[Dict[int, bytes], Dict[int, bytes], Dict[int, float]]:
    """
    Creates Merkle leaves from a DataFrame with predictions.
    Returns dictionaries for leaf hashes, salts, and original predictions.
    """
    leaves_db: Dict[int, bytes] = {}
    salts_db: Dict[int, bytes] = {}
    predictions_db: Dict[int, float] = {}
    
    for idx, row in df.iterrows():
        # Get the prediction value
        pred_value = row['pred']
        # Generate a secure random salt (32 bytes)
        salt = secrets.token_bytes(32)
        # Pack the float into bytes using struct
        float_bytes = struct.pack('!d', pred_value)
        # Combine float and salt
        leaf_data = float_bytes + salt
        # Hash the combined data
        leaf_hash = keccak256(leaf_data)
        
        # Store all components
        leaves_db[idx] = leaf_hash
        salts_db[idx] = salt
        predictions_db[idx] = pred_value
    
    return leaves_db, salts_db, predictions_db
def compute_merkle_proof(index: int, leaves_db: Dict[int, bytes], default_hash: bytes) -> Tuple[List[bytes], bytes]:
    """
    Builds the proof path for `index` and returns (proof, root).
    Matches the contract's verification logic exactly.
    """
    proof: List[bytes] = []
    n_leaves = len(leaves_db)
    depth = ceil_log2(max(n_leaves, 1))
    size = 1 << depth  # Padded leaf layer size

    # Initialize the tree array.
    # Leaves will be in tree[0...size-1].
    # Internal nodes will be in tree[size...2*size-1].
    tree = [default_hash] * (2 * size)
    for idx, hash_val in leaves_db.items(): # leaves_db keys are original 0 to n_leaves-1
        tree[idx] = hash_val # Populate actual leaves. Unused leaf slots remain default_hash.

    # Tree building part (this part from your file is correct)
    # layer_start_idx tracks the global start index of the current layer of children.
    # parent_layer_start_idx tracks the global start index where parents are being written.
    layer_start_idx = 0 
    parent_layer_start_idx = size 
    for d_loop_var in range(depth): # d_loop_var from 0 (processing leaves) to depth-1
        num_nodes_in_current_layer = size >> d_loop_var # Number of nodes in the child layer
        for i_child_pair in range(0, num_nodes_in_current_layer, 2): # Iterate over pairs of children
            left_child = tree[layer_start_idx + i_child_pair]
            right_child = tree[layer_start_idx + i_child_pair + 1]
            
            parent_node_idx_in_parent_layer = i_child_pair // 2 # Parent's relative index in its layer
            current_parent_global_idx = parent_layer_start_idx + parent_node_idx_in_parent_layer
            
            if left_child <= right_child:
                tree[current_parent_global_idx] = keccak256(left_child + right_child)
            else:
                tree[current_parent_global_idx] = keccak256(right_child + left_child)
        
        layer_start_idx = parent_layer_start_idx # Parents of this level become children for the next
        parent_layer_start_idx += (num_nodes_in_current_layer // 2) # Advance parent write position
    
    # After the loop, layer_start_idx is the global index of the root node.
    root = tree[layer_start_idx]

    # Corrected Proof Collection:
    current_node_relative_idx = index # Leaf's index relative to its layer (0 to layer_size-1)

    for d_current_layer_level in range(depth): # Iterate from layer 0 (leaves) up to layer depth-1
        
        # Determine the global starting index of the current layer (d_current_layer_level) in the `tree` array.
        # Layer 0 (leaves) starts at global index 0.
        # Layer d (d > 0) starts at global index: 2*size - (size / 2^(d-1))
        current_layer_global_start_idx: int
        if d_current_layer_level == 0:
            current_layer_global_start_idx = 0
        else:
            current_layer_global_start_idx = (size << 1) - (size >> (d_current_layer_level - 1))

        sibling_node_relative_idx = current_node_relative_idx ^ 1 # Sibling's index within the current layer
        sibling_node_global_idx_in_tree = current_layer_global_start_idx + sibling_node_relative_idx
        
        proof.append(tree[sibling_node_global_idx_in_tree])
        
        # Move to the parent's relative index for the next iteration
        current_node_relative_idx = current_node_relative_idx // 2
        
    return proof, root

def get_merkle_proof_for_leaf(tree_id: str, leaf_index: int, db_path='merkle_tree.db') -> Tuple[bytes, List[bytes]]:
    """
    Retrieve a leaf and compute its proof on-demand from the local SQLite database.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        # Get the stored root first
        cur.execute('''
            SELECT root_hash 
            FROM merkle_roots 
            WHERE tree_id = ?
        ''', (tree_id,))
        
        root_row = cur.fetchone()
        if not root_row:
            raise ValueError(f"No tree found with ID {tree_id}")
        
        root = root_row['root_hash']
        
        # Get all leaves for this tree
        cur.execute('''
            SELECT leaf_index, leaf_hash 
            FROM merkle_leaves 
            WHERE tree_id = ?
        ''', (tree_id,))
        
        # Reconstruct leaves_db
        leaves_db = {row['leaf_index']: row['leaf_hash'] for row in cur.fetchall()}
        
        # Compute proof
        default_hash = keccak256(b'\x00')
        proof, computed_root = compute_merkle_proof(leaf_index, leaves_db, default_hash)
        
        # Verify that our computed root matches the stored root
        if computed_root != root:
            raise ValueError("Computed root does not match stored root")
        
        return root, proof
        
    finally:
        cur.close()
        conn.close()


def store_merkle_leaves(df: pd.DataFrame, db_path='merkle_tree.db') -> str:
    """
    Store the leaves, salts, predictions, and root in the local SQLite database.
    """
    # Initialize the database if needed
    init_db(db_path)
    
    # Generate a unique tree ID
    tree_id = str(uuid.uuid4())
    
    # Process predictions
    leaves_db, salts_db, predictions_db = create_merkle_leaves(df)
    
    # Compute the root hash once
    default_hash = keccak256(b'\x00')
    _, root = compute_merkle_proof(0, leaves_db, default_hash)  # We can use any index since we want the full tree
    
    # Database connection
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    try:
        # Store the root first
        cur.execute('''
            INSERT INTO merkle_roots 
            (tree_id, root_hash)
            VALUES (?, ?)
        ''', (tree_id, root))
        
        # Store the leaves
        for idx in leaves_db.keys():
            cur.execute('''
                INSERT INTO merkle_leaves 
                (tree_id, leaf_index, leaf_hash, salt, prediction)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                tree_id,
                idx,
                leaves_db[idx],
                salts_db[idx],
                predictions_db[idx]
            ))
        
        conn.commit()
        return tree_id
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def init_db(db_path='merkle_tree.db'):
    """Initialize the SQLite database with the required schema."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Create the existing merkle_leaves table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS merkle_leaves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_id TEXT NOT NULL,
        leaf_index INTEGER NOT NULL,
        leaf_hash BLOB NOT NULL,
        salt BLOB NOT NULL,
        prediction REAL NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tree_id, leaf_index)
    )
    ''')
    
    # Create new table for storing tree roots
    cur.execute('''
    CREATE TABLE IF NOT EXISTS merkle_roots (
        tree_id TEXT PRIMARY KEY,
        root_hash BLOB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()



def store_merkle_root(timestamp: int, root: bytes):
        
    load_dotenv()
    # Configuration and inputs

    RPC_URL = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")  # Base Sepolia RPC endpoint
    PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Private key for deploying and sending transactions
    CHAIN_ID = 84532     # Chain ID for Base Sepolia testnet


    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    account = w3.eth.account.from_key(PRIVATE_KEY)
    contract_address = '0x6baF889AEa470c01912ae209AcA04cB473929714'

    import json
    abi = json.load(open('punk_predictor_abi.json'))
    fee_kwargs = {'maxFeePerGas': 2000000378, 
                'maxPriorityFeePerGas': 1000000000}
    # Store the Merkle root on-chain using the current timestamp as key
    contract = w3.eth.contract(address=contract_address, abi=abi)
    nonce = w3.eth.get_transaction_count(account.address)
    set_root_tx = contract.functions.setMerkleRoot(timestamp, root).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "chainId": CHAIN_ID,
        **fee_kwargs,
        "gas": 0  # placeholder for gas; will estimate below
    })
    try:
        set_gas_estimate = w3.eth.estimate_gas({**set_root_tx, "gas": None})
    except Exception:
        set_gas_estimate = 200000  # fallback
    set_root_tx["gas"] = int(set_gas_estimate * 1.2)
    signed_set_root_tx = account.sign_transaction(set_root_tx)
    # Fix: Use raw_transaction instead of rawTransaction
    tx_hash2 = w3.eth.send_raw_transaction(signed_set_root_tx.raw_transaction)
    print(f"Calling setMerkleRoot(timestamp={timestamp}, root={root.hex()})... (tx hash: {tx_hash2.hex()})")
    w3.eth.wait_for_transaction_receipt(tx_hash2)
    print("Merkle root has been set on the blockchain.")
    return timestamp 



def verify_leaf(timestamp, PUNK_ID, proof_hex_list, tree_id):
    
    db_path = 'merkle_tree.db'
    conn = sqlite3.connect(db_path)
    data = pd.read_sql_query('SELECT * FROM merkle_leaves WHERE tree_id = ?', conn, params=(tree_id,))
    target_leaf = data.loc[PUNK_ID, 'leaf_hash']
    
    RPC_URL = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")  # Base Sepolia RPC endpoint
    PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Private key for deploying and sending transactions


    w3 = Web3(Web3.HTTPProvider(RPC_URL))


    contract_address = '0x6baF889AEa470c01912ae209AcA04cB473929714'

    abi = json.load(open('punk_predictor_abi.json'))
    contract = w3.eth.contract(address=contract_address, abi=abi)
    # Call verifyLeaf on the contract to verify the proof
    leaf_hex = "0x" + target_leaf.hex()
    proof_hex_list = ["0x" + p.hex() for p in proof]
    verify_result = contract.functions.verifyLeaf(timestamp, PUNK_ID, w3.to_bytes(hexstr=leaf_hex), [w3.to_bytes(hexstr=h) for h in proof_hex_list]).call()
    # Output the results
    print(f"Leaf hash for Punk ID {PUNK_ID}: {leaf_hex}")
    print(f"Merkle root: 0x{root.hex()}")
    print(f"Proof for Punk ID {PUNK_ID}: {[h for h in proof_hex_list]}")
    print(f"verifyLeaf returned: {verify_result}")
    print("Proof valid?", verify_merkle_proof(target_leaf, PUNK_ID, proof, root))
    
def verify_merkle_proof(leaf: bytes, index: int, proof: List[bytes], root: bytes) -> bool:
    h = leaf
    print(f"Starting with leaf: {h.hex()}")
    for i, proof_element in enumerate(proof):
        print(f"\nStep {i}:")
        print(f"Current hash: {h.hex()}")
        print(f"Proof element: {proof_element.hex()}")
        if h <= proof_element:
            print("h <= proof_element, concatenating h + proof_element")
            h = keccak256(h + proof_element)
        else:
            print("h > proof_element, concatenating proof_element + h")
            h = keccak256(proof_element + h)
        print(f"New hash: {h.hex()}")
    print(f"\nFinal hash: {h.hex()}")
    print(f"Expected root: {root.hex()}")
    return h == root



# First create and store the tree
# in reality this predictions are the ones from the ML rather than random
predictions = pd.DataFrame({
    'index': range(10000),
    'pred': np.random.rand(10000)
})
tree_id = store_merkle_leaves(predictions)

PUNK_ID = 1234
root, proof = get_merkle_proof_for_leaf(tree_id, PUNK_ID)


timestamp = store_merkle_root(int(time.time()), root)


verify_leaf(timestamp, PUNK_ID, proof, tree_id)