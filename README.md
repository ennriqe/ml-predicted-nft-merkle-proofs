# Onchain verifiable ML performance metrics for NFT valuations using merkle Proofs by PunkPredictor

A Python toolkit and on-chain smart contract for building, storing, and verifying sparse Merkle-tree proofs over machine-learning–generated NFT valuation predictions to prove predictive accuracy metrics trustlessly.

## 📦 Features

- Create Merkle leaves from a DataFrame of ML-predicted NFT valuations
- Store leaves, salts, predictions & root in a local SQLite database
- On-demand proof generation (O(log N) siblings) without keeping the full tree in memory
- Publish Merkle root on Base Sepolia via a PunkPredictor Solidity contract
- Verify leaf inclusion both off-chain (Python) and on-chain

## 🏗 Architecture

```
+--------------------+       +----------------------+       +---------------------+
|  predictions       | ──▶   |   Python scripts     | ──▶   |   SQLite database   |
| (index, pred value)|       | - store_leaves.py    |       | - merkle_leaves     |
+--------------------+       | - proofgen.py        |       | - merkle_roots      |
                             +----------------------+       +---------------------+
                                                                  │
                                                                  ▼
                                                     +---------------------------+
                                                     |   Base Sepolia (EVM)      |
                                                     |  PunkPredictor.sol        |
                                                     +---------------------------+
                                                                  │
                                                                  ▼
                                                     +---------------------------+
                                                     |   On-chain verifyLeaf()   |
                                                     +---------------------------+
```

## 🔧 Prerequisites

- Python ≥ 3.8
- solcx for Solidity compilation
- A Base Sepolia RPC URL & private key (via .env)
- SQLite (bundled with Python)

## ⚙️ Installation

1. Clone the repo
```bash
git clone https://github.com/your-org/ml-nft-merkle-proofs.git
cd ml-nft-merkle-proofs
```

2. Create & activate a virtualenv
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install Python dependencies
```bash
pip install requirements.txt
```

4. Create a `.env` in project root:
```ini
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE
```

## 🚀 Usage

### 1. Store ML NFT valuations as a Merkle tree

```python
# Example: using an in-memory DataFrame of 10 000 random predictions
python - <<EOF
import numpy as np, pandas as pd
from store_leaves import store_merkle_leaves

df = pd.DataFrame({
  'index': range(10_000),
  'pred': np.random.rand(10_000)
})
tree_id = store_merkle_leaves(df, db_path='merkle_tree.db')
print("Tree ID:", tree_id)
EOF
```

This will:
- Salt & hash each prediction (keccak256(struct.pack('!d', pred) ∥ salt))
- Persist merkle_leaves and a generated merkle_roots entry in SQLite
- Return a tree_id UUID for later proof lookups

### 2. Generate & verify a proof locally

```python
from proofgen import get_merkle_proof_for_leaf, verify_merkle_proof

tree_id = "<YOUR-TREE-ID>"
punk_id  = 1234

# Fetch root & proof from SQLite
root, proof = get_merkle_proof_for_leaf(tree_id, punk_id, db_path='merkle_tree.db')

# Off-chain verify
leaf_hash = ...  # load from DB or recompute
is_valid = verify_merkle_proof(leaf_hash, punk_id, proof, root)
print("Proof valid?", is_valid)
```

### 3. Publish root on-chain

```python
from store_root import store_merkle_root
import time

# current UNIX timestamp
ts = int(time.time())
# `root` from proof generation step
tx_ts = store_merkle_root(ts, root)
print("Published at timestamp:", tx_ts)
```

This sends `setMerkleRoot(timestamp, bytes32 root)` to the deployed PunkPredictor contract.

### 4. Deploy (or re-deploy) the Solidity contract

```bash
python deploy_contract.py
```

This will:
- Compile PunkPredictor.sol with solc 0.8.20
- Save punk_predictor_abi.json
- Deploy to Base Sepolia
- Print the new contract address

## 📁 Repository Layout

```
.
├── store_leaves.py        # Create & store Merkle leaves + salts + SQL schema
├── proofgen.py            # On-demand proof generation & off-chain verify
├── store_root.py          # Push Merkle root to on-chain contract
├── deploy_contract.py     # Compile & deploy PunkPredictor.sol
├── punk_predictor_abi.json# Generated ABI file
├── .env                   # RPC_URL & PRIVATE_KEY (gitignored)
└── merkle_tree.db         # SQLite database (gitignored)
```

## 📚 References

- [Web3.py docs](https://web3py.readthedocs.io/)
- [pycryptodome Keccak](https://pycryptodome.readthedocs.io/)
- [Ethereum Solidity docs](https://docs.soliditylang.org/)

Enjoy provable, verifiable accuracy metrics NFT-valuation proofs! By PunkPredictor
