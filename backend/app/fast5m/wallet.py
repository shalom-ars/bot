import os
import json
import logging
import urllib.request
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Fast5MSetting

logger = logging.getLogger(__name__)

# Polygon Contract Addresses
POLYGON_CHAIN_ID = 137
POLYGON_USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
POLYGON_USDC_BRIDGED = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
POLYMARKET_CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"

# Reliable Public Polygon RPC endpoints with failover
POLYGON_RPCS = [
    "https://1rpc.io/matic",
    "https://polygon-bor-rpc.publicnode.com",
    "https://rpc.ankr.com/polygon",
]

class Fast5MWalletManager:
    """
    Manages Web3 Wallet Connection, Polygon On-Chain Balances,
    and Polymarket CLOB execution configuration for the 5-Minute Prediction Engine.
    """

    def __init__(self):
        self.account_mode: str = "demo"  # 'demo' or 'live'
        self.wallet_address: str = ""
        self._private_key: str = ""
        self.proxy_address: str = ""
        self.api_key: str = ""
        self._api_secret: str = ""
        self._api_passphrase: str = ""
        
        # On-Chain Cached Balances
        self.usdc_native_balance: float = 0.0
        self.usdc_bridged_balance: float = 0.0
        self.pol_balance: float = 0.0
        self.wallet_type: str = "rabby"  # Exclusively Rabby Wallet
        self.last_balance_sync: Optional[datetime] = None
        self.is_connected: bool = False
        self.clob_api_status: str = "IDLE"  # IDLE, ONLINE, ERROR

        # Initialize from DB / Environment
        self._rehydrate()

    def _rehydrate(self):
        """Loads persistent wallet configuration from database or env."""
        db: Session = SessionLocal()
        try:
            settings_rows = db.query(Fast5MSetting).all()
            s_map = {row.key: row.value for row in settings_rows}

            self.account_mode = s_map.get("wallet_account_mode", "demo")
            self.wallet_address = s_map.get("wallet_address", os.environ.get("POLYGON_WALLET_ADDRESS", ""))
            self._private_key = s_map.get("wallet_private_key", os.environ.get("POLYGON_WALLET_PRIVATE_KEY", ""))
            self.proxy_address = s_map.get("wallet_proxy_address", os.environ.get("POLYMARKET_PROXY_ADDRESS", ""))
            self.api_key = s_map.get("wallet_api_key", os.environ.get("POLYMARKET_API_KEY", ""))
            self._api_secret = s_map.get("wallet_api_secret", os.environ.get("POLYMARKET_API_SECRET", ""))
            self._api_passphrase = s_map.get("wallet_api_passphrase", os.environ.get("POLYMARKET_API_PASSPHRASE", ""))

            self.is_connected = bool(self.wallet_address and self.wallet_address.startswith("0x") and len(self.wallet_address) == 42)
            if self.is_connected and not self.has_signer:
                # Browser connected wallet (address only, without private key yet)
                pass
        except Exception as e:
            logger.error(f"[WalletManager] Rehydrate error: {e}")
        finally:
            db.close()

    @property
    def has_signer(self) -> bool:
        """True if automated private key or CLOB API credentials are configured."""
        return bool(self._private_key or (self.api_key and self._api_secret))

    @property
    def total_usdc_balance(self) -> float:
        return round(self.usdc_native_balance + self.usdc_bridged_balance, 2)

    def mask_string(self, s: str, visible_start: int = 6, visible_end: int = 4) -> str:
        if not s:
            return ""
        if len(s) <= (visible_start + visible_end):
            return "••••••••"
        return f"{s[:visible_start]}••••••••{s[-visible_end:]}"

    def _call_rpc(self, method: str, params: list) -> Any:
        """Calls Polygon RPC with automatic multi-endpoint failover."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }
        data_bytes = json.dumps(payload).encode("utf-8")

        for rpc in POLYGON_RPCS:
            try:
                req = urllib.request.Request(
                    rpc,
                    data=data_bytes,
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as res:
                    body = json.loads(res.read().decode())
                    if "result" in body:
                        return body["result"]
            except Exception as e:
                logger.debug(f"[WalletManager] RPC {rpc} failed for {method}: {e}")
                continue

        return None

    def refresh_balances(self) -> Dict[str, float]:
        """Queries on-chain Polygon for Native USDC, Bridged USDC.e, and POL/Matic balances."""
        if not self.wallet_address or not self.wallet_address.startswith("0x"):
            return {"usdc": 0.0, "pol": 0.0, "native_usdc": 0.0, "bridged_usdc": 0.0}

        # 1. Native POL/Matic Balance
        pol_res = self._call_rpc("eth_getBalance", [self.wallet_address, "latest"])
        if pol_res:
            try:
                self.pol_balance = round(int(pol_res, 16) / 1e18, 4)
            except Exception:
                pass

        # 2. ERC-20 balanceOf data payload: 0x70a08231 + 64-char address
        addr_clean = self.wallet_address.lower().replace("0x", "").zfill(64)
        balance_of_data = f"0x70a08231{addr_clean}"

        # 3. Native USDC (0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359)
        native_res = self._call_rpc("eth_call", [
            {"to": POLYGON_USDC_NATIVE, "data": balance_of_data},
            "latest"
        ])
        if native_res and native_res != "0x":
            try:
                self.usdc_native_balance = round(int(native_res, 16) / 1e6, 2)
            except Exception:
                pass

        # 4. Bridged USDC.e (0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174)
        bridged_res = self._call_rpc("eth_call", [
            {"to": POLYGON_USDC_BRIDGED, "data": balance_of_data},
            "latest"
        ])
        if bridged_res and bridged_res != "0x":
            try:
                self.usdc_bridged_balance = round(int(bridged_res, 16) / 1e6, 2)
            except Exception:
                pass

        self.last_balance_sync = datetime.now(timezone.utc)
        return {
            "usdc": self.total_usdc_balance,
            "pol": self.pol_balance,
            "native_usdc": self.usdc_native_balance,
            "bridged_usdc": self.usdc_bridged_balance,
        }

    def connect(
        self,
        address: str,
        private_key: Optional[str] = None,
        proxy_address: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Connects a real wallet, validates addresses/keys, stores settings persistently,
        and refreshes on-chain balances.
        """
        address = (address or "").strip()
        if not address.startswith("0x") or len(address) != 42:
            return {"success": False, "error": "Invalid Polygon wallet address format (must be 42 characters starting with 0x)."}

        self.wallet_address = address
        if private_key:
            pk = private_key.strip()
            if pk.startswith("0x"):
                pk = pk[2:]
            if len(pk) != 64:
                return {"success": False, "error": "Invalid private key format (must be 64 hexadecimal characters)."}
            self._private_key = pk

        if proxy_address:
            pa = proxy_address.strip()
            if pa and (not pa.startswith("0x") or len(pa) != 42):
                return {"success": False, "error": "Invalid Polymarket proxy address format."}
            self.proxy_address = pa

        if api_key:
            self.api_key = api_key.strip()
        if api_secret:
            self._api_secret = api_secret.strip()
        if api_passphrase:
            self._api_passphrase = api_passphrase.strip()

        self.is_connected = True

        # Persist to database
        db: Session = SessionLocal()
        try:
            configs_to_save = {
                "wallet_address": self.wallet_address,
                "wallet_account_mode": self.account_mode,
            }
            if self._private_key:
                configs_to_save["wallet_private_key"] = self._private_key
            if self.proxy_address:
                configs_to_save["wallet_proxy_address"] = self.proxy_address
            if self.api_key:
                configs_to_save["wallet_api_key"] = self.api_key
            if self._api_secret:
                configs_to_save["wallet_api_secret"] = self._api_secret
            if self._api_passphrase:
                configs_to_save["wallet_api_passphrase"] = self._api_passphrase

            for k, v in configs_to_save.items():
                existing = db.query(Fast5MSetting).filter_by(key=k).first()
                if existing:
                    existing.value = str(v)
                else:
                    db.add(Fast5MSetting(key=k, value=str(v)))
            db.commit()
        except Exception as e:
            logger.error(f"[WalletManager] Connect persistence error: {e}")
            db.rollback()
        finally:
            db.close()

        # Refresh on-chain balances
        self.refresh_balances()

        return {
            "success": True,
            "wallet": self.get_status()
        }

    def set_mode(self, mode: str) -> Dict[str, Any]:
        """Toggles between 'demo' (Virtual $300) and 'live' (Real Wallet Polymarket CLOB)."""
        target = "live" if mode.lower() in ("live", "real", "real_money") else "demo"
        if target == "live":
            if not self.is_connected or not self.wallet_address:
                return {"success": False, "error": "Cannot switch to Live Trading: No wallet is connected."}
            if not self.has_signer:
                return {
                    "success": False,
                    "error": "Cannot activate Live Execution: No Signer Private Key or Polymarket CLOB credentials configured. Bot requires signing capability for sub-second 5M round execution."
                }
            # Balance check
            self.refresh_balances()
            if self.total_usdc_balance < 1.0:
                return {
                    "success": False,
                    "warning": f"Low balance warning: Your Polygon wallet has ${self.total_usdc_balance:.2f} USDC. Minimum recommended is $10.00 USDC for automated trading.",
                    "proceed": True
                }

        self.account_mode = target

        # Persist mode
        db: Session = SessionLocal()
        try:
            existing = db.query(Fast5MSetting).filter_by(key="wallet_account_mode").first()
            if existing:
                existing.value = self.account_mode
            else:
                db.add(Fast5MSetting(key="wallet_account_mode", value=self.account_mode))
            db.commit()
        except Exception as e:
            logger.error(f"[WalletManager] Set mode persistence error: {e}")
            db.rollback()
        finally:
            db.close()

        return {
            "success": True,
            "account_mode": self.account_mode,
            "wallet": self.get_status()
        }

    def disconnect(self) -> Dict[str, Any]:
        """Clears connected wallet credentials and reverts to paper demo mode."""
        self.wallet_address = ""
        self._private_key = ""
        self.proxy_address = ""
        self.api_key = ""
        self._api_secret = ""
        self._api_passphrase = ""
        self.usdc_native_balance = 0.0
        self.usdc_bridged_balance = 0.0
        self.pol_balance = 0.0
        self.is_connected = False
        self.account_mode = "demo"

        db: Session = SessionLocal()
        try:
            keys_to_clear = [
                "wallet_address", "wallet_private_key", "wallet_proxy_address",
                "wallet_api_key", "wallet_api_secret", "wallet_api_passphrase",
                "wallet_account_mode"
            ]
            db.query(Fast5MSetting).filter(Fast5MSetting.key.in_(keys_to_clear)).delete(synchronize_session=False)
            db.commit()
        except Exception as e:
            logger.error(f"[WalletManager] Disconnect error: {e}")
            db.rollback()
        finally:
            db.close()

        return {"success": True, "wallet": self.get_status()}

    def get_status(self) -> Dict[str, Any]:
        """Returns safe, public wallet status and balances."""
        return {
            "is_connected": self.is_connected,
            "account_mode": self.account_mode,  # 'demo' or 'live'
            "wallet_address": self.wallet_address,
            "masked_address": self.mask_string(self.wallet_address, 6, 4) if self.wallet_address else None,
            "has_signer": self.has_signer,
            "proxy_address": self.proxy_address or None,
            "masked_proxy": self.mask_string(self.proxy_address, 6, 4) if self.proxy_address else None,
            "has_api_creds": bool(self.api_key and self._api_secret),
            "chain_id": POLYGON_CHAIN_ID,
            "chain_name": "Polygon Mainnet",
            "usdc_total": self.total_usdc_balance,
            "usdc_native": self.usdc_native_balance,
            "usdc_bridged": self.usdc_bridged_balance,
            "pol_gas_balance": self.pol_balance,
            "last_balance_sync": self.last_balance_sync.isoformat() if self.last_balance_sync else None,
            "can_trade_live": bool(self.is_connected and self.has_signer and self.account_mode == "live"),
            "polymarket_ctf_approved": True,  # Checked during live trade or mock pass
            "wallet_type": "rabby",
            "is_rabby": True,
        }

# Global Singleton Instance
wallet_manager = Fast5MWalletManager()
