from app.db.session import SessionLocal
from app.btc5m.settings_manager import update_btc5m_settings

db = SessionLocal()
updates = {
    "min_p2b_diff": 10.0,
    "min_order_book_imbalance": 0.02,
    "min_entry_score": 50.0,
    "min_entry_probability": 0.50,
    "min_net_edge": -0.005,
    "min_time_remaining": 45.0,
    "max_time_remaining": 285.0
}
res = update_btc5m_settings(db, updates, user_info="USER_REQUEST")
db.close()
print("Updated settings successfully:", res)
