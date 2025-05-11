import os
import sys
import time
import subprocess
import sqlite3
from web3 import Web3
import solcx
from dotenv import load_dotenv

load_dotenv()
# Configuration and inputs

RPC_URL = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")  # Base Sepolia RPC endpoint
PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Private key for deploying and sending transactions
CHAIN_ID = 84532     # Chain ID for Base Sepolia testnet


# Part 3: Deploy the PunkPredictor smart contract to Base Sepolia and verify the leaf inclusion
# Connect to the Base Sepolia network via Web3
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise Exception("Failed to connect to Base Sepolia network. Check your RPC URL.")

# Compile the PunkPredictor Solidity contract
solidity_source = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract PunkPredictor {
    // Store Merkle roots by timestamp
    mapping(uint256 => bytes32) public merkleRoots;

    // Store a new Merkle root for a given timestamp
    function setMerkleRoot(uint256 timestamp, bytes32 root) public {
        merkleRoots[timestamp] = root;
    }

    // Verify if a given leaf is in the Merkle tree with root at the given timestamp
    function verifyLeaf(uint256 timestamp, uint256 punkId, bytes32 leaf, bytes32[] memory proof) public view returns (bool) {
        bytes32 root = merkleRoots[timestamp];
        bytes32 computedHash = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 proofElement = proof[i];
            if (computedHash <= proofElement) {
                // Hash current computed hash with the proof element (sorted order)
                computedHash = keccak256(abi.encodePacked(computedHash, proofElement));
            } else {
                computedHash = keccak256(abi.encodePacked(proofElement, computedHash));
            }
        }
        return computedHash == root;
    }
}
"""

solcx.install_solc("0.8.20")
solcx.set_solc_version("0.8.20")
compiled = solcx.compile_source(solidity_source, output_values=["abi", "bin"])
contract_id = [key for key in compiled.keys() if key.endswith(":PunkPredictor")][0]
contract_interface = compiled[contract_id]
abi = contract_interface["abi"]
bytecode = contract_interface["bin"]

# Save the ABI to disk
import json
with open('punk_predictor_abi.json', 'w') as f:
    json.dump(abi, f)
print("ABI saved to punk_predictor_abi.json")

# Prepare account and transaction parameters
account = w3.eth.account.from_key(PRIVATE_KEY)
deploy_nonce = w3.eth.get_transaction_count(account.address)
# Determine if network uses EIP-1559 (baseFee present) for fee fields
latest_block = w3.eth.get_block("latest")
base_fee = latest_block.get("baseFeePerGas")
if base_fee is not None:
    # EIP-1559 fee structure
    max_priority_fee = w3.to_wei(1, "gwei")
    max_fee = base_fee + w3.to_wei(2, "gwei")
    fee_kwargs = {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": max_priority_fee}
else:
    # Legacy gas price
    gas_price = w3.eth.gas_price or w3.to_wei(5, "gwei")
    fee_kwargs = {"gasPrice": gas_price}

# Deploy the contract
PunkPredictor = w3.eth.contract(abi=abi, bytecode=bytecode)
deploy_tx = PunkPredictor.constructor().build_transaction({
    "from": account.address,
    "nonce": deploy_nonce,
    "chainId": CHAIN_ID,
    **fee_kwargs,
    "gas": 0  # placeholder gas; will estimate below
})
# Estimate gas for deployment
try:
    deploy_gas_estimate = w3.eth.estimate_gas({**deploy_tx, "gas": None})
except Exception:
    deploy_gas_estimate = 1000000  # fallback to 1,000,000 if estimate fails
deploy_tx["gas"] = int(deploy_gas_estimate * 1.2)  # add 20% buffer to gas estimate
signed_deploy_tx = account.sign_transaction(deploy_tx)
# Fix: Use raw_transaction instead of rawTransaction
tx_hash = w3.eth.send_raw_transaction(signed_deploy_tx.raw_transaction)
print(f"Deploying PunkPredictor contract... (tx hash: {tx_hash.hex()})")
deploy_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
contract_address = deploy_receipt.contractAddress
print(f"Contract deployed at {contract_address}")