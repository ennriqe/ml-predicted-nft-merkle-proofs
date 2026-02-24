# On-Chain Verifiable ML Metrics for NFT Valuations (Merkle Proofs)

Python + Solidity prototype for proving ML-generated NFT valuation predictions and derived metrics using sparse Merkle trees, local SQLite storage, and on-chain verification on Base Sepolia.

## What This Repo Demonstrates

- Generate salted Merkle leaves from model predictions
- Persist leaf hashes, salts, predictions, and roots in SQLite
- Build inclusion proofs on demand (without keeping a full tree in memory permanently)
- Deploy a simple verifier contract on Base Sepolia
- Publish Merkle roots and verify leaf inclusion off-chain and on-chain

## Repository Contents

- `prediction_merkle_tree.py` - Merkle leaf creation, proof generation, SQLite storage, root publishing helpers
- `create_contract.py` - compiles and deploys a `PunkPredictor` verifier contract to Base Sepolia
- `punk_predictor_abi.json` - ABI artifact for the verifier contract

## Architecture

```text
Predictions (index, pred)
        |
        v
prediction_merkle_tree.py
  - hash leaves (prediction + salt)
  - compute tree / proofs
  - store leaves + roots in SQLite
        |
        v
merkle_tree.db (local SQLite)
        |
        +--> off-chain proof verification
        |
        +--> root publication (Base Sepolia)
                    |
                    v
              PunkPredictor.sol
              verifyLeaf(...)
```

## Prerequisites

- Python 3.8+
- Base Sepolia RPC URL
- Private key with testnet ETH (for deploy/root publication)
- `solcx` / Solidity compiler toolchain (installed by the script)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install web3 pycryptodome python-dotenv pandas numpy py-solc-x
```

Create `.env` in the repo root:

```ini
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```

## Quick Example (Local Merkle Tree + Proof)

```python
import pandas as pd
from prediction_merkle_tree import store_merkle_leaves, get_merkle_proof_for_leaf

# toy prediction set
preds = pd.DataFrame({"pred": [12.3, 10.8, 9.9, 15.1]})

tree_id = store_merkle_leaves(preds, db_path="merkle_tree.db")
root, proof = get_merkle_proof_for_leaf(tree_id, leaf_index=0, db_path="merkle_tree.db")
print(tree_id, root.hex(), len(proof))
```

## Deploy the Verifier Contract (Base Sepolia)

```bash
python create_contract.py
```

The script will:
- compile the Solidity contract
- save/update `punk_predictor_abi.json`
- deploy the verifier contract to Base Sepolia
- print the deployed contract address

## Notes / Limitations

- This is a prototype intended to demonstrate verifiable metric publishing, not a hardened production contract system
- The Solidity contract shown here is intentionally simple (no access control on `setMerkleRoot`)
- For production use, add authorization, versioning, and event logging policies
